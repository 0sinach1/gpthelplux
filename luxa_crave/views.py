from django.utils import timezone
import traceback
from django_hosts.resolvers import reverse as hosts_reverse
import logging

from django.utils.timezone import localtime
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from .models import Campus_Location, Campus_Pack_Preset, Campus_Pack_Preset_Item, Location_Building, Pack_Size_Config, University_Profile, Crave_Student_Profile, University_Outlet, User_Venture_Profile_Settings, University_Outlet_Section, Section_Product, University_Order, Order_Pack, Order_Pack_Item, Default_Proxy_Settings, Campus_Engine_Order,VerificationPing, VerificationPingItem
import json
from decimal import Decimal
from django.http import JsonResponse
from django.urls import reverse
from escrow.models import Wallet
from escrow.services import lock_university_order_funds
from couriers.models import Courier, DeliveryBatch
from django_hosts.resolvers import reverse as hosts_reverse
from django.db.models import Sum



# --- AUTHENTICATION VIEWS ---
def crave_login(request):
    """Standalone login page exclusively for Luxa Crave."""
    # If they are already logged in, send them straight to the entry gate
    if request.user.is_authenticated:
        return redirect('crave_entry')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Ensure they are a customer before letting them into Crave
            if not hasattr(user, 'customer_profile'):
                logout(request)
                messages.error(request, "Only registered customers can access Luxa Crave.")
                return redirect('crave_login')
                
            return redirect('crave_entry')
        else:
            messages.error(request, "Invalid email or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'luxa_crave/authentication/crave_login.html', {'form': form})

def crave_logout(request):
    """Logs the user out and shows the Crave-branded exit screen."""
    logout(request)
    return render(request, 'luxa_crave/authentication/crave_logout.html')

# --- MAIN CRAVE VIEWS ---
@login_required(login_url='crave_login')
def crave_entry(request):
    """
    The Gatekeeper: Routes the user based on their default university status.
    """
    # 1. Ensure the user is a Customer
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, "Only registered customers can access Luxa Crave.")
        return redirect(hosts_reverse('index', host='default')) # Redirect to your main site home

    customer = request.user.customer_profile

    # 2. Get or Create the Crave Profile
    crave_profile, created = Crave_Student_Profile.objects.get_or_create(customer=customer)

    # 3. Check for Default University
    if request.method == 'POST':
        # User is submitting their university choice
        uni_id = request.POST.get('university_id')
        if uni_id:
            selected_uni = get_object_or_404(University_Profile, id=uni_id)
            crave_profile.default_university = selected_uni
            crave_profile.save()
            return redirect('crave_dashboard')

    # THE FIX: Check if the user explicitly wants to change their campus
    changing_campus = request.GET.get('change') == 'true'

    # If they have a default AND they aren't trying to change it -> Dashboard
    if crave_profile.default_university and not changing_campus:
        return redirect('crave_dashboard')
    
    # Otherwise, show the selection page
    universities = University_Profile.objects.all()
    return render(request, 'luxa_crave/authentication/select_university.html', {'universities': universities})

@login_required(login_url='crave_login')
def crave_outlet_sections(request):
    # Ensure user has a student crave profile and selected university.
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, "Only registered customers can access Luxa Crave.")
        return redirect(hosts_reverse('index', host='default'))

    crave_profile = getattr(request.user.customer_profile, 'crave_profile', None)
    if not crave_profile or not crave_profile.default_university:
        return redirect('crave_entry')

    university = crave_profile.default_university
    outlets = University_Outlet.objects.filter(university=university).order_by('name')

    context = {
        'university': university,
        'outlets': outlets,
        'current_outlet': None,
    }
    return render(request, 'luxa_crave/outlet_sections.html', context)

@login_required(login_url='crave_login')
def crave_dashboard(request):
    """Placeholder for the Dashboard Page"""
    crave_profile = getattr(request.user.customer_profile, 'crave_profile', None)
    
    if not crave_profile or not crave_profile.default_university:
        return redirect('crave_entry')
        
    context = {
        'university': crave_profile.default_university,
    }
    return render(request, 'luxa_crave/crave_intro.html', context)

@login_required(login_url='crave_login')
def outlet_terminal(request, outlet_id):
    """Placeholder for the Caf Terminal Page"""
    outlet = get_object_or_404(University_Outlet, id=outlet_id)
    crave_profile = getattr(request.user.customer_profile, 'crave_profile', None)

    # Fetch only the presets for THIS specific outlet that belong to THIS user
    user_presets = Campus_Pack_Preset.objects.filter(
        customer=crave_profile, 
        outlet=outlet
    ).order_by('-created_at')
    context = {
        'outlet': outlet,
        'sections': outlet.sections.all(),
        'university': outlet.university,
        # NEW: Pass the pack configurations
        'pack_configs': Pack_Size_Config.objects.all().order_by('base_price'), 
        'user_presets': user_presets,
    }
    return render(request, 'luxa_crave/outlet_terminal.html', context)

# API endpoint to fetch a preset's exact JSON structure for the cart, including real-time pricing and pack details
@login_required(login_url='crave_login')
def get_pack_preset(request, preset_id):
    """API endpoint to fetch a preset's exact JSON structure for the cart."""
    if request.method == "GET":
        try:
            crave_profile = request.user.customer_profile.crave_profile
            preset = get_object_or_404(Campus_Pack_Preset, id=preset_id, customer=crave_profile)

            # --- 1. CALCULATE TRUE INFLUENCE VALUE (COURIONS) ---
            # We must recreate the exact logic from validate_pack_integrity
            STRANGE_FACTORS = {
                "large_bread": 2,
                "medium_bread": 1,
                "small_bread": 1,
                "bread_egg": 1, 
            }
            strange_sum = 0
            has_strange = False
            
            for p_item in preset.items.all():
                product = p_item.product
                if getattr(product, 'is_strange', False):
                    has_strange = True
                    factor = STRANGE_FACTORS.get(getattr(product, 'strange_value', ''), 1)
                    strange_sum += (p_item.quantity * factor)

            # Grab the multiplier (fallback to 1 if missing)
            multiplier = getattr(preset, 'pack_multiplier', 1)
            
            # The final accurate Courion value for this saved preset
            calculated_iv = multiplier * (strange_sum if has_strange else 1)
            
            # Pack the data exactly how your Javascript expects it
            pack_data = {
                'preset_id': preset.id,
                'preset_name': preset.preset_name,
                'selectedPackConfigId': preset.pack_size.id if preset.pack_size else None,
                'packContainerCost': float(preset.pack_size.base_price) if preset.pack_size else 0.0,
                'packContainerName': preset.pack_size.get_size_name_display() if preset.pack_size else "No Pack",
                'packContainerImage': preset.pack_size.pack_image.url if (preset.pack_size and preset.pack_size.pack_image) else "placeholder",
                'maxCapacity': float(preset.pack_size.max_capacity) if preset.pack_size else 0.0,
                'maxOverflow': float(preset.pack_size.max_overflow) if preset.pack_size else 0.0,
                'pack_multiplier': preset.pack_multiplier,
                # --- ADDED: BASELINE INFLUENCE VALUE ---
                'influence_value': float(calculated_iv), 
                'items': []
            }

            # Loop through the items and grab current pricing/specs
            for p_item in preset.items.all():
                product = p_item.product
                pack_data['items'].append({
                    'id': product.id,
                    'name': product.product_name,
                    'qty': p_item.quantity,
                    'price': float(product.unit_price),
                    'fillingValue': float(product.filling_value),
                    'needsPack': product.requires_pack,
                    'image': product.product_image.url if product.product_image else "placeholder",
                    'is_a_soup': product.is_a_soup,
                    'need_soup': product.need_soup,
                    'not_ordered_alone': product.not_ordered_alone,
                    # --- CART FLAGS FOR LOGIC & SURCHARGES ---
                    'is_strange': getattr(product, 'is_strange', False),
                    'strange_value': getattr(product, 'strange_value', None),
                    'sectionId': product.section.id if hasattr(product, 'section') and product.section else None,
                    'sectionName': product.section.name if hasattr(product, 'section') and product.section else "Unknown",
                    'notOrderedAlone': product.not_ordered_alone # camelCase match for JS consistency
                })

            return JsonResponse({'status': 'success', 'pack_data': pack_data})
        except Exception as e:
            print(f"Preset Fetch Error: {str(e)}") # Console debug help
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'invalid method'}, status=400)


# API to save pack presets
@login_required(login_url='crave_login')
def save_pack_preset(request):
    """API Endpoint to save a custom pack as a preset."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            preset_name = data.get('preset_name')
            outlet_id = data.get('outlet_id')
            pack_config_id = data.get('pack_config_id')
            items = data.get('items', [])

            if not preset_name or not items:
                return JsonResponse({'status': 'error', 'message': 'Preset name and items are required.'})

            crave_profile = request.user.customer_profile.crave_profile
            outlet = get_object_or_404(University_Outlet, id=outlet_id)
            pack_config = Pack_Size_Config.objects.filter(id=pack_config_id).first() if pack_config_id else None
            pack_multiplier = data.get('pack_multiplier', 1)

            # 1. Create the Master Preset
            preset = Campus_Pack_Preset.objects.create(
                customer=crave_profile,
                outlet=outlet,
                preset_name=preset_name,
                pack_size=pack_config,
                pack_multiplier=pack_multiplier
            )

            # 2. Attach the Items to the Preset
            for item in items:
                product = get_object_or_404(Section_Product, id=item['id'])
                Campus_Pack_Preset_Item.objects.create(
                    preset=preset,
                    product=product,
                    quantity=int(item['qty'])
                )

            return JsonResponse({'status': 'success'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'invalid method'}, status=400)

@login_required(login_url='crave_login')
def delete_pack_preset(request, preset_id):
    """API Endpoint to delete a saved preset."""
    if request.method == "POST":
        try:
            # Securely fetch only the preset belonging to THIS specific user
            crave_profile = request.user.customer_profile.crave_profile
            preset = get_object_or_404(Campus_Pack_Preset, id=preset_id, customer=crave_profile)
            
            preset.delete()
            return JsonResponse({'status': 'success'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'invalid method'}, status=400)

# Crave Checkout View: Handles both the AJAX POST to save the cart and the GET to load the checkout page
@login_required(login_url='crave_login')
def crave_checkout(request):
    # 1. Handle the AJAX POST request from the Terminal to save the cart
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Securely store the cart payload in the user's Django session
            request.session['crave_cart'] = data.get('cart', [])
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # 2. Handle the standard GET request to load the page
    cart_data = request.session.get('crave_cart', [])

    # KYC Check 
    try:
        kyc_status = request.user.customer_profile.kyc_profile.status
    except:
        kyc_status = 'NONE'
    
    if not cart_data:
        return redirect('crave_dashboard') # Redirect back if no cart data is found
        
    crave_profile = request.user.customer_profile.crave_profile
    customer = request.user.customer_profile
    university = crave_profile.default_university
    
    # --- NEW: THE LAZY RESET & PROMO CALCULATION ---
    today = timezone.localdate()
    if customer.last_promo_date != today:
        customer.promo_daily_counter = 0
        customer.last_promo_date = today
        customer.save(update_fields=['promo_daily_counter', 'last_promo_date'])
        
    available_promo_courions = max(0, customer.promo_daily_total - customer.promo_daily_counter)
    # -----------------------------------------------
    
    # Fetch locations and buildings for this specific university
    locations = Campus_Location.objects.filter(university=university)
    buildings = Location_Building.objects.filter(parent_location__university=university)
    
    # --- NEW: Check if the customer has a delivery PIN ---
    has_pin = bool(getattr(request.user.customer_profile, 'delivery_pin', False))
    
    # --- NEW: Check if this is a "Cafeteria" order to enable Engine testing ---
    is_cafeteria_order = False
    target_outlet_name = ""

    if cart_data:
        for pack in cart_data:
            items = pack.get('items', [])
            if items:
                first_item_id = items[0].get('id')
                first_prod = Section_Product.objects.filter(id=first_item_id).first()
                if first_prod and hasattr(first_prod, 'section') and first_prod.section and first_prod.section.outlet:

                    target_outlet_name = first_prod.section.outlet.name

                    # Check if the name matches 'cafeteria' (case-insensitive)
                    if target_outlet_name.strip().lower() == 'cafeteria':
                        is_cafeteria_order = True
                break # All items in a cart share the same outlet, so we only need to check the first one
    
    context = {
        'university': university,
        'crave_profile': crave_profile, 
        'customer': customer,
        'available_promo_courions': available_promo_courions,
        'locations': locations,         
        'buildings': buildings,         
        'kyc_status': kyc_status,       
        'cart_data_json': json.dumps(cart_data), 
        'has_pin': has_pin, # --- NEW: Pass flag to template --- 
        'is_cafeteria_order': is_cafeteria_order,
        'target_outlet_name': target_outlet_name,
    }
    return render(request, 'luxa_crave/crave_checkout.html', context)

# Api endpoint to check wallet balance before checkout proceedings
@login_required(login_url='crave_login')
@require_POST
def check_wallet_balance_api(request):
    """
    Pre-flight check to ensure the customer has enough money 
    before initiating the PIN/Terminal sequence.
    """
    try:
        data = json.loads(request.body)
        required_amount = Decimal(str(data.get('required_amount', 0)))
        
        # Fetch the customer's personal wallet
        wallet = Wallet.objects.filter(user=request.user, wallet_type=Wallet.WalletType.CUSTOMER).first()
        
        # NOTE: Replace 'fund_wallet_view_name' with your actual URL name for the wallet page
        wallet_url = hosts_reverse('wallet_dashboard', host='default') if wallet else '#'
        
        if not wallet or wallet.available_balance < required_amount:
            return JsonResponse({
                'has_balance': False, 
                'wallet_url': wallet_url
            })

        return JsonResponse({'has_balance': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# This is the critical endpoint that processes the checkout form submission, creates the order, checks stock, locks funds, and returns success or specific errors back to the frontend
@require_POST
@login_required(login_url='crave_login')
def create_campus_order(request):
    """
    The final checkout execution. 
    Verifies PIN, updates profiles, checks wallet, deducts stock, and locks escrow.
    """
    try:
        user = request.user
        customer = user.customer_profile
        crave_profile = customer.crave_profile
        
        # --- 1. PIN VERIFICATION ---
        pin = request.POST.get('delivery_pin')
        if not pin:
            return JsonResponse({'success': False, 'error': 'Delivery PIN is required.'})
            
        # THE FIX: Check if the PIN actually exists in the database first!
        # If the user never set a PIN, Django's check_password throws a len(None) error.
        if not getattr(customer, 'delivery_pin', None):
            return JsonResponse({
                'success': False, 
                'error': 'You have not set up a Delivery PIN yet. Please click the link below the pin input to create one.'
            })
            
        # If they do have a PIN, proceed to verify it normally
        if not hasattr(customer, 'check_delivery_pin') or not customer.check_delivery_pin(pin):
            return JsonResponse({'success': False, 'error': 'Invalid Delivery PIN.'})
            
        # --- 2. PROFILE UPDATES (For Unverified KYC Flow) ---
        if request.POST.get('update_profile') == 'true':
            user.first_name = request.POST.get('kyc_first_name', user.first_name)
            user.last_name = request.POST.get('kyc_last_name', user.last_name)
            user.save()
            
            customer.phone_number = request.POST.get('kyc_phone', customer.phone_number)
            customer.gender = request.POST.get('kyc_gender', customer.gender)
            customer.social_media_platform = request.POST.get('kyc_social_platform', customer.social_media_platform)
            customer.social_media_handle = request.POST.get('kyc_social_handle', customer.social_media_handle)

            if 'kyc_profile_picture' in request.FILES:
                customer.profile_picture = request.FILES['kyc_profile_picture']
            customer.save()
            
        # --- 3. PARSE CART DATA ---
        cart_data_str = request.POST.get('cart_data')
        if not cart_data_str:
            return JsonResponse({'success': False, 'error': 'Your bag is empty.'})
        cart = json.loads(cart_data_str)

        # --- 3.5. OUTLET AVAILABILITY & TIME CHECK ---
        # Since validation ensures all items in a bag belong to one outlet, 
        # we just need to grab the very first valid item to find the anchor outlet.
        target_outlet = None
        for pack_data in cart:
            items = pack_data.get('items', [])
            if items:
                first_item_id = items[0].get('id')
                first_product = Section_Product.objects.filter(id=first_item_id).first()
                print(f"DEBUG >>> Target Outlet Identified: {first_product.section.outlet.name} (Section: {first_product.section.name})")
                if first_product and first_product.section and first_product.section.outlet:
                    target_outlet = first_product.section.outlet
                    break
        
        if target_outlet:
            # 1. Check if an admin manually turned the outlet off
            if not target_outlet.availability_status:
                return JsonResponse({
                    'success': False, 
                    'error': f"Sorry, {target_outlet.name} is currently offline and not receiving orders at this time."
                })
            
            # 2. Check if it is past their operating hours
            if not target_outlet.is_currently_open:
                return JsonResponse({
                    'success': False, 
                    'error': f"Sorry, {target_outlet.name} is currently closed. Please check their operating hours."
                })

            # --- NEW: SECURE SERVER TIME CHECK FOR WAIT FEE ---
            is_wait_fee_active = False
            if 'backyard' in target_outlet.name.lower():
                now_local = timezone.localtime()
                hour = now_local.hour
                
                # Check if server time is between 17:00 and 18:59
                if (hour == 17) or (hour == 18):
                    is_wait_fee_active = True

            # --- GATE 2: THE 4-STATE CONFIDENCE CHECK ---  
            is_safe_mode = request.POST.get('safe_mode') == 'true'
            
            # Note: We dropped 'and target_outlet' here because we are already safely inside the target_outlet block!
            if is_safe_mode:
                
                low_confidence_items = []
                hard_blocked_items = []
                
                three_minutes_ago = timezone.now() - timedelta(minutes=3)
                forty_five_minutes_ago = timezone.now() - timedelta(minutes=45)

                # 1. Loop through the cart and check timestamps AND availability
                for pack_data in cart:
                    for item_data in pack_data.get('items', []):
                        prod_id = item_data.get('id')
                        prod = Section_Product.objects.filter(id=prod_id).first()
                        
                        if prod:
                            # --- THE NULL CHECK ---
                            if not prod.last_updated_availability:
                                low_confidence_items.append(prod)
                                continue 
                                
                            if not prod.availability_status:
                                # MARKED AS SOLD OUT
                                if prod.last_updated_availability > forty_five_minutes_ago:
                                    hard_blocked_items.append(prod)
                                else:
                                    low_confidence_items.append(prod)
                            else:
                                # MARKED AS AVAILABLE
                                if prod.last_updated_availability > three_minutes_ago:
                                    pass 
                                else:
                                    low_confidence_items.append(prod)

                # 2. Handle Hard Blocks FIRST (Instant Rebuild)
                if hard_blocked_items:
                    alternatives_payload = {}
                    for prod in set(hard_blocked_items):
                        if prod.section:
                            alts = Section_Product.objects.filter(section=prod.section, availability_status=True).exclude(id=prod.id)
                            alt_list = []
                            for alt in alts:
                                alt_list.append({
                                    'id': alt.id,
                                    'name': alt.product_name,
                                    'price': float(alt.unit_price),
                                    'image': alt.product_image.url if alt.product_image else '/static/images/placeholder.png',
                                    'needsPack': getattr(alt, 'requires_pack', False),
                                    'fillingValue': float(alt.filling_value),
                                    'sectionId': prod.section.id,
                                    'sectionName': prod.section.name,
                                    'notOrderedAlone': getattr(alt, 'not_ordered_alone', False),
                                    'is_a_soup': getattr(alt, 'is_a_soup', False),
                                    'need_soup': getattr(alt, 'need_soup', False),
                                    'is_strange': getattr(alt, 'is_strange', False),
                                    'strange_value': getattr(alt, 'strange_value', ''),
                                    'has_charge': getattr(alt, 'has_charge', False)
                                })
                            alternatives_payload[str(prod.id)] = alt_list

                    return JsonResponse({
                        'success': False, 
                        'status': 'instant_rebuild',
                        'message': 'Some items in your bag are currently out of stock.',
                        'sold_out_ids': [str(prod.id) for prod in set(hard_blocked_items)],
                        'alternatives': alternatives_payload
                    })

                # 3. Handle Low Confidence (Ping the Kitchen)
                if low_confidence_items:
                    ping = VerificationPing.objects.create(outlet=target_outlet)
                    for prod in set(low_confidence_items):
                        VerificationPingItem.objects.create(ping=ping, product=prod)

                    return JsonResponse({
                        'success': False, 
                        'status': 'ping_initiated',
                        'ping_id': ping.id,
                        'message': 'Engine verifying stock with kitchen...'
                    })
                    
        else:
            # THIS is the correct else block! It only triggers if the outlet genuinely couldn't be found.
            return JsonResponse({
                'success': False, 
                'error': 'Could not verify the outlet for these items. Please clear your bag and try again.'
            })
        
        # --- 4. RESOLVE DELIVERY LOCATION (Proxy vs Direct) ---
        use_proxy = request.POST.get('use_proxy') == 'on'
        
        if use_proxy and crave_profile.proxy_enabled and hasattr(crave_profile, 'default_proxy'):
            proxy = crave_profile.default_proxy
            loc_id = proxy.proxy_location_id
            bldg_id = proxy.proxy_building_id
            room = proxy.proxy_address
            extra = f"DELIVER TO PROXY: {proxy.proxy_name}. " + request.POST.get('extra_instructions', '')
        else:
            loc_id = request.POST.get('campus_address')
            bldg_id = request.POST.get('campus_building')
            room = request.POST.get('room_number')
            extra = request.POST.get('extra_instructions', '')

        if not loc_id or not bldg_id or not room:
             return JsonResponse({'success': False, 'error': 'A complete delivery address is required.'})

        # --- 5. THE DATABASE TRANSACTION ---
        required_amount = 0
        try:
            # Atomic block ensures that if wallet lock fails, NO database records are saved!
            with transaction.atomic():
                
                # A. Create the Order Shell
                order = University_Order.objects.create(
                    customer=customer,
                    location_category_id=loc_id,
                    building_id=bldg_id,
                    room_number=room,
                    extra_info=extra,
                    status='pending',
                    terminal_payload=cart, # Retain exact snapshot for records
                    wait_fee=is_wait_fee_active
                )
                
                # B. Build Packs, Items, and Deduct Stock
                for pack_data in cart:
                    # --- NEW: Safely determine if this is a physical pack or a loose bundle ---
                    raw_pack_id = pack_data.get('selectedPackConfigId')
                    requires_pack = pack_data.get('requiresPackFlag', True)
                    
                    # If it doesn't need a pack, or the JS sent 'loose', force it to None
                    if not requires_pack or raw_pack_id in ['loose', '', None]:
                        pack_config_id = None
                    else:
                        pack_config_id = raw_pack_id
                    
                    pack = Order_Pack.objects.create(
                        order=order,
                        pack_size_id=pack_config_id,
                        multiplier=int(pack_data.get('multiplier', 1)),
                        status='Closed'
                    )
                    
                    if pack:
                        print(f"DEBUG >>> FOUND Order_Pack! Original IV: {pack.influence_value}")
                        
                        pack.influence_value = pack_data.get('influence_value', 0)
                        pack.save()
                        
                        # Double check by fetching it again from the DB
                        print(f"DEBUG >>> SAVE SUCCESS! New DB Value: {pack.influence_value}")
                    else:
                        print(f"DEBUG >>> SAVE FAILED: No Order_Pack found with ID {pack.id}")
                    
                    for item_data in pack_data.get('items', []):
                        # select_for_update() locks the product row to prevent race conditions (over-ordering)
                        product = Section_Product.objects.select_for_update().get(id=item_data.get('id'))
                        qty = int(item_data.get('qty', 1))
                        
                        if product.stock_quantity < qty:
                            raise ValueError(f"Sorry, {product.product_name} is out of stock.")
                            
                        product.stock_quantity -= qty
                        product.save(update_fields=['stock_quantity'])
                        
                        Order_Pack_Item.objects.create(
                            pack=pack,
                            product=product,
                            quantity=qty
                        )

                # --- NEW: C. LOYALTY PROMO VALIDATION ---
                order.total_physical_packs_db = order.total_physical_packs
                
                apply_promo = request.POST.get('apply_loyalty_promo') == 'true'
                today = timezone.localdate()
                
                # Lazy reset double-check (Safety net)
                if customer.last_promo_date != today:
                    customer.promo_daily_counter = 0
                    customer.last_promo_date = today
                    customer.save(update_fields=['promo_daily_counter', 'last_promo_date'])
                
                if apply_promo and customer.promo_percentage > 0:
                    remaining_allowance = customer.promo_daily_total - customer.promo_daily_counter
                    
                    if order.total_physical_packs_db <= remaining_allowance:
                        order.used_daily_promo = True
                        # Deduct from allowance
                        customer.promo_daily_counter += order.total_physical_packs_db
                        customer.save(update_fields=['promo_daily_counter'])
                    else:
                        order.used_daily_promo = False # Tamper detection: Fallback to standard
                else:
                    order.used_daily_promo = False

                order.save(update_fields=['total_physical_packs_db', 'used_daily_promo'])

                # D. Evaluate final cost (Property will automatically apply discount if used_daily_promo is True)
                required_amount = order.total_order_cost
                
                # D. Trigger Escrow Lock (Will raise ValueError if insufficient funds)
                lock_university_order_funds(user, order)
                
                # E. Generate the Layer 3 Engine View for the Courier App
                engine_order = Campus_Engine_Order.objects.create(raw_order=order)

                # # --- NEW: VIP BYPASS LANE TRIGGER ---
                # preferred_courier = request.POST.get('preferred_courier_username')
                # if preferred_courier:
                #     # 1. Flag the order as a custom assignment
                #     order.custom_assigned = True
                #     order.save(update_fields=['custom_assigned'])
                    
                #     # 2. Execute the Bypass instantly (while still inside the atomic lock!)
                #     from decision_engine.special_campus_routing.campus_engine_bypass_lane import execute_bypass_lane_assignment
                #     execute_bypass_lane_assignment(engine_order.id, preferred_courier)
                
        except ValueError as e:
            if "Insufficient funds" in str(e):
                # Send the specific error code back to trigger the frontend Wallet Top-Up UI
                return JsonResponse({
                    'success': False, 
                    'error_code': 'insufficient_funds',
                    'required_amount': str(required_amount),
                    # NOTE: Adjust this reverse string if your wallet top-up page has a different name
                    'wallet_url': hosts_reverse('wallet_dashboard', host='default')
                })
            # This catches out-of-stock or generic value errors
            return JsonResponse({'success': False, 'error': str(e)})

        # --- 6. SUCCESS & CLEANUP ---
        
        # Clear the cart from the session safely
        request.session.pop('crave_cart', None)
        request.session.modified = True
        
        # Bounce the user to their Settings Order History
        university_id = order.location_category.university.id
        redirect_url = f"{reverse('profile_settings', args=[university_id])}#orders-section"
        
        return JsonResponse({'success': True, 'redirect_url': redirect_url})

    except Exception as e:
        print("--- CHECKOUT CRASH TRACEBACK ---")
        traceback.print_exc() # This will print the exact file and line number to your terminal!
        print("--------------------------------")
        return JsonResponse({'success': False, 'error': f'Server Error: {str(e)}'})

#profile settings page
def profile_settings_page(request, profile_id):
    profile = get_object_or_404(University_Profile, id=profile_id)
    customer = request.user.customer_profile
    
    hub, created = User_Venture_Profile_Settings.objects.get_or_create(
        user=customer,
        profile=profile
    )
    
    # Statistics
    past_orders = University_Order.objects.filter(
        customer=customer,
        status__in=['pending', 'processing', 'assigned', 'delivered']
    ).order_by('-order_date')
    
    total_orders = past_orders.count()
    total_spent = sum((order.total_order_cost for order in past_orders), Decimal('0.00'))

    # NEW: Fetch ALL orders for the list (including cancelled, excluding 'ordering_mode' carts)
    all_orders = University_Order.objects.filter(
        customer=customer
    ).exclude(status='ordering_mode').order_by('-order_date')

    # Fetch Presets & Locations
    user_presets = Campus_Pack_Preset.objects.filter(customer=customer.crave_profile, outlet__university=profile).order_by('-created_at')
    locations = Campus_Location.objects.filter(university=profile)
    buildings = Location_Building.objects.filter(parent_location__university=profile)
    
    context = {
        'settings_hub': hub,
        'university': profile,
        'customer': customer,
        'locations': locations,
        'buildings': buildings,
        'total_orders': total_orders,
        'total_spent': total_spent,
        'user_presets': user_presets,
        'all_orders': all_orders, # Passed to template
    }
    return render(request, 'luxa_crave/settings.html', context)

# --- 2. NEW API ENDPOINT FOR HANDLING ORDER DETAILS ---
@login_required(login_url='crave_login')
def get_order_details(request, order_id):
    """Fetches the comprehensive breakdown of a specific order."""
    try:
        # Securely fetch only if it belongs to this user
        order = get_object_or_404(University_Order, order_id=order_id, customer=request.user.customer_profile)
        
        order_data = {
            'order_number': order.order_number,
            'date': localtime(order.order_date).strftime("%b %d, %Y, %I:%M %p"),
            'status': order.get_status_display(),
            'raw_status': order.status,
            'delivery_fee': float(order.delivery_fee),
            'total_cost': float(order.total_order_cost),
            'address': f"{order.location_category.value if order.location_category else 'Unknown'}, {order.building.value if order.building else 'Unknown'}, Room {order.room_number or '-'}",
            'packs': []
        }
        
        # Breakdown the packs
        for pack in order.packs.all():
            pack_data = {
                'pack_name': pack.pack_size.get_size_name_display() if pack.pack_size else "No Pack",
                'pack_cost': float(pack.pack_size.base_price) if pack.pack_size else 0.00,
                'multiplier': pack.multiplier,
                'pack_total': float(pack.total_pack_cost),
                'items': []
            }
            # Breakdown the items in the pack
            for item in pack.items.all():
                pack_data['items'].append({
                    'name': item.product.product_name,
                    'qty': item.quantity,
                    'subtotal': float(item.subtotal)
                })
            order_data['packs'].append(pack_data)

        return JsonResponse({'status': 'success', 'order_data': order_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# API To update active orders in settings page
@login_required(login_url='crave_login')
def get_active_orders_status(request):
    """
    Lightweight polling endpoint. Only fetches orders that are actively moving.
    Returns a dictionary of { order_id: { raw_status, display_status } }
    """
    try:
        # We exclude 'delivered', 'cancelled', and 'refunded' because those statuses are final and don't need polling.
        active_orders = University_Order.objects.filter(
            customer=request.user.customer_profile,
            status__in=['pending', 'processing', 'assigned', 'in_transit'] 
        ).values('order_id', 'status')

        # Map raw status strings to their human-readable display versions
        status_map = dict(University_Order.ORDER_STATUS_CHOICES)
        
        data = {
            str(order['order_id']): {
                'raw': order['status'],
                'display': status_map.get(order['status'], order['status'])
            } for order in active_orders
        }
        
        return JsonResponse({'status': 'success', 'orders': data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# API endpoint to update the customer's primary campus delivery address from the settings page
@login_required(login_url='crave_login')
def update_customer_address(request):
    """Updates the user's primary campus delivery address."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            crave_profile = request.user.customer_profile.crave_profile
            
            loc_id = data.get('location_id')
            bldg_id = data.get('building_id')
            room_number = data.get('room_number', '')
            
            # Update the profile (using _id to directly assign the ForeignKey IDs)
            crave_profile.campus_address_id = loc_id if loc_id else None
            crave_profile.campus_building_id = bldg_id if bldg_id else None
            crave_profile.room_number = room_number
            
            crave_profile.save()

            return JsonResponse({'status': 'success', 'message': 'Address updated successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'invalid method'}, status=400)

# API endpoint to update proxy settings from the frontend
@login_required(login_url='crave_login')
def update_proxy(request):
    if request.method == "POST":
        try:
            # 1. Get the user's Crave profile
            crave_profile = request.user.customer_profile.crave_profile

            # 2. Get or create the proxy settings
            proxy, created = Default_Proxy_Settings.objects.get_or_create(
                customer=crave_profile
            )
            
            # 3. Read text fields from request.POST
            proxy.proxy_name = request.POST.get('proxy_name', '')
            proxy.proxy_address = request.POST.get('proxy_address', '')
            proxy.proxy_seed_phrase_hash = request.POST.get('proxy_seed_phrase_hash', '')
            
            # --- NEW: Capture and save the gender ---
            proxy.proxy_gender = request.POST.get('proxy_gender', 'male')
            
            loc_id = request.POST.get('proxy_location_id')
            bldg_id = request.POST.get('proxy_building_id')
            
            proxy.proxy_location_id = loc_id if loc_id else None
            proxy.proxy_building_id = bldg_id if bldg_id else None
            
            # 4. Handle the Image File
            if 'proxy_photo' in request.FILES:
                proxy.proxy_photo = request.FILES['proxy_photo']
            
            proxy.save()

            return JsonResponse({'status': 'success', 'message': 'Proxy updated successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'invalid method'}, status=400)

@login_required(login_url='crave_login')
def toggle_proxy_status(request):
    """Activates or deactivates the user's proxy status globally."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            is_enabled = data.get('proxy_enabled', False)
            
            # Update the profile
            crave_profile = request.user.customer_profile.crave_profile
            crave_profile.proxy_enabled = is_enabled
            crave_profile.save()

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'invalid method'}, status=400)

#settings update
def update_settings(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            field = data.get('field')
            value = data.get('value')
            profile_id = data.get('profile_id')

            # FIX: We need request.user.customer_profile to match your model
            hub = User_Venture_Profile_Settings.objects.get(
                user=request.user.customer_profile, 
                profile_id=profile_id
            )
            
            # Dynamically update (e.g., hub.selected_theme = 'lmu-arena')
            if hasattr(hub, field):
                setattr(hub, field, value)
                hub.save()
                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'error', 'message': f'Field {field} not found'}, status=400)

        except User_Venture_Profile_Settings.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Settings Hub not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'invalid method'}, status=400)

# This is the endpoint that the Terminal calls to validate the pack before allowing the user to proceed to checkout
@login_required(login_url='crave_login')
def validate_pack_integrity(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])
            pack_size_id = data.get('pack_size_id')
            multiplier = int(data.get('multiplier', 1))
            current_cart = data.get('current_cart', [])




            # --- LOGISTICAL CONSTANTS ---
            STRANGE_FACTORS = {
                "large_bread": 2,
                "medium_bread": 1,
                "small_bread": 1, 
                "bread_egg": 1,
            }
            LOOSE_ITEM_PACK_LIMIT = 10
            GLOBAL_MAX_ITEM_QTY = 30
            MAX_COURIONS = 10

            # --- NEW: 1. ESTABLISH THE "ANCHOR OUTLET" FOR THIS TRANSACTION ---
            anchor_outlet_id = None
            anchor_outlet_name = ""

            # Step A: Check existing bag (current_cart)
            for pack in current_cart:
                cart_items = pack.get('items', [])
                if cart_items:
                    first_cart_id = int(cart_items[0].get('id'))
                    anchor_prod = Section_Product.objects.filter(id=first_cart_id).first()
                    if anchor_prod:
                        anchor_outlet_id = anchor_prod.section.outlet.id
                        anchor_outlet_name = anchor_prod.section.outlet.name
                        break 

            # Step B: SELF-CONSISTENCY CHECK (For the new items being added)
            # Even if the bag is empty, we must ensure the new items all match each other
            new_items_outlet_id = None
            new_items_outlet_name = ""

            for item in items:
                p_id = int(item.get('id'))
                p_obj = Section_Product.objects.filter(id=p_id).first()
                
                if p_obj:
                    # If this is the first valid item in the loop, it sets the rule for this pack
                    if new_items_outlet_id is None:
                        new_items_outlet_id = p_obj.section.outlet.id
                        new_items_outlet_name = p_obj.section.outlet.name
                    
                    # If a subsequent item in the same pack doesn't match the first item
                    elif p_obj.section.outlet.id != new_items_outlet_id:
                        return JsonResponse({
                            'valid': False,
                            'reason': f"Transaction Blocked! You are trying to add items from {p_obj.section.outlet.name} and {new_items_outlet_name} in the same pack. A bag can only contain items from one outlet. Please clear your selection!"
                        })

            # Step C: CROSS-CHECK (Compare New Items vs Existing Bag)
            if anchor_outlet_id and new_items_outlet_id:
                if new_items_outlet_id != anchor_outlet_id:
                    return JsonResponse({
                        'valid': False,
                        'reason': f"Conflict! Your bag is already tied to {anchor_outlet_name}. You cannot add items from {new_items_outlet_name}. Clear your bag first or place a separate order!"
                    })

            # --- 2. CALCULATE NEW PACK INFLUENCE ---
            strange_sum = 0
            has_strange = False

            print(f"\nDEBUG >>> --- New Pack Calculation Start ---")

            for item in items:
                try:
                    # Force integer conversion
                    p_id = int(item.get('id'))
                    print(f"DEBUG >>> Attempting direct fetch for ID: {p_id}")
                    
                    # DIRECT FETCH instead of map lookup
                    p_obj = Section_Product.objects.filter(id=p_id).first()
                    
                    if p_obj:
                        print(f"DEBUG >>> Found in DB: {p_obj.product_name} | Strange: {p_obj.is_strange}")
                        if p_obj.is_strange:
                            has_strange = True
                            factor = STRANGE_FACTORS.get(p_obj.strange_value, 1)
                            qty = int(item.get('qty', 0))
                            strange_sum += (qty * factor)
                            print(f"DEBUG >>> Calculation: {qty} x {factor}")
                    else:
                        print(f"DEBUG >>> ERROR: Database returned NONE for ID {p_id}")
                        
                except Exception as loop_e:
                    print(f"DEBUG >>> Loop Error: {str(loop_e)}")

            new_pack_iv = multiplier * (strange_sum if has_strange else 1)
            print(f"DEBUG >>> Final new_pack_iv: {new_pack_iv}")

            print(f"DEBUG >>> Multiplier: {multiplier}")
            print(f"DEBUG >>> Final Influence Value (IV) for this pack: {new_pack_iv}")

            # --- 2. VALIDATE TOTAL COURIONS IN BAG (Limit: 20) ---
            # We sum the 'influence_value' already calculated for items in the bag
            existing_influence = sum(int(p.get('influence_value', 1)) for p in current_cart)
            total_after_adding = existing_influence + new_pack_iv

            print(f"DEBUG >>> Existing Courions in Bag: {existing_influence}")
            print(f"DEBUG >>> Projected Total Courions: {total_after_adding}")
            print(f"DEBUG >>> --- Calculation End ---\n")
            
            if (existing_influence + new_pack_iv) > MAX_COURIONS:
                available_space = MAX_COURIONS - existing_influence
                return JsonResponse({
                    'valid': False, 
                    'reason': f"Courier bag capacity reached! This order has {new_pack_iv} Courions. You only have {max(0, available_space)} space left."
                })



            # --- 3. CHECK INDIVIDUAL LIMITS (using GLOBAL_MAX_ITEM_QTY) & BREAD EGG LIMIT ---
            total_bread_egg_qty = 0
            
            for item in items:
                qty = int(item.get('qty', 0))
                p_id = int(item.get('id', 0))
                
                if qty > GLOBAL_MAX_ITEM_QTY:
                    return JsonResponse({
                        'valid': False, 
                        'reason': f"Limit exceeded: You cannot add more than {GLOBAL_MAX_ITEM_QTY} units of an item."
                    })
                
                # Fetch product to verify if it's a bread_egg
                p_obj = Section_Product.objects.filter(id=p_id).first()
                if p_obj and p_obj.strange_value == 'bread_egg':
                    total_bread_egg_qty += qty

            # The Ultimate Backend Bouncer for Bread Eggs
            # if total_bread_egg_qty > 1:
            #     return JsonResponse({
            #         'valid': False,
            #         'reason': "You can only have 1 Bread Egg per pack. Please modify your selection."
            #     })
                


            # --- 4. SOUP & SWALLOW LOGIC ---
            # Using .get() ensures the code doesn't crash if the key is missing
            soups = [i for i in items if i.get('is_a_soup') == True]
            items_needing_soup = [i for i in items if i.get('need_soup') == True]

            # Rule A: Item needs a soup but none is included
            if items_needing_soup and not soups:
                return JsonResponse({
                    'valid': False, 
                    'reason': "Items like swallows must be paired with a soup base!"
                })

            # Rule B: Soup is included but no item requires it
            if soups and not items_needing_soup:
                return JsonResponse({
                    'valid': False, 
                    'reason': "A soup base requires a main item (like a swallow) to be valid in this pack."
                })

            # Rule C: Only one soup allowed per pack
            # We check len(soups) because the list contains the individual soup items
            if len(soups) > 1:
                return JsonResponse({
                    'valid': False, 
                    'reason': "Only one base soup is allowed per pack."
                })


            # --- 5. NOT ORDERED ALONE VALIDATION ---
            # Checking both camelCase and snake_case to safely catch the JS payload
            items_not_ordered_alone = [
                i for i in items 
                if i.get('notOrderedAlone') is True or i.get('not_ordered_alone') is True
            ]

            if items_not_ordered_alone:
                # If these items exist, we MUST ensure there is at least ONE item in the 
                # pack that CAN be ordered alone (a main meal/item).
                valid_main_item_exists = any(
                    not (i.get('notOrderedAlone') is True or i.get('not_ordered_alone') is True) 
                    for i in items
                )
                
                if not valid_main_item_exists:
                    # Grab the names of the dependent items to give a helpful error message
                    item_names = ", ".join(list(set(i.get('name', 'This item') for i in items_not_ordered_alone)))
                    return JsonResponse({
                        'valid': False, 
                        'reason': f"Items like {item_names} cannot be ordered by themselves. Please add a main item to this pack."
                    })

             # --- 6. LOOSE-ONLY LOOPHOLE PROTECTION ---
            # Determine if this pack contains ONLY loose items (needsPack == False)
            is_loose_only = all(i.get('needsPack') == False for i in items)
            
            if is_loose_only:
                total_qty = sum(int(i.get('qty', 0)) for i in items)
                if total_qty > LOOSE_ITEM_PACK_LIMIT:
                    return JsonResponse({
                        'valid': False, 
                        'reason': f"A pack of loose items cannot exceed {LOOSE_ITEM_PACK_LIMIT} total units."
                    })
                # If it's loose-only and under the limit, we skip the box capacity checks below.
                # Since Rule 5 is already verified, it's now completely safe to return True!
                return JsonResponse({'valid': True, 'influence_value': new_pack_iv})

            # CAPACITY & OVERFLOW CHECKS (Only for items requiring a pack)
            config = Pack_Size_Config.objects.filter(id=pack_size_id).first()
            if config:
                total_box_fill = 0
                total_payload = 0
                for item in items:
                    qty = int(item.get('qty', 0))
                    fill_contribution = float(item.get('fillingValue', 0)) * qty
                    total_payload += fill_contribution
                    
                    # Only add to box fill if the item actually goes INSIDE the box
                    if item.get('needsPack') == True:
                        total_box_fill += fill_contribution

                if total_box_fill > config.max_capacity:
                    return JsonResponse({
                        'valid': False, 
                        'reason': f"The Lid Wont close! These items exceed the capacity of a {config.get_size_name_display()}."
                    })

                if total_payload > config.max_overflow:
                    return JsonResponse({
                        'valid': False, 
                        'reason': f"The total volume/weight exceeds the Overflow limit of a {config.get_size_name_display()} pack."
                    })

            # 4. Success!
            return JsonResponse({
                'valid': True, 
                'influence_value': new_pack_iv
            })

        except Exception as e:
            print(f"DEBUG >>> SERVER ERROR: {str(e)}")
            return JsonResponse({'valid': False, 'reason': f"Server Error: {str(e)}"})

    return JsonResponse({'valid': False, 'reason': "Invalid Request Method"}, status=400)

# This is the endpoint that the Terminal calls to validate the entire bag before allowing the user to proceed to checkout PAGE
@login_required(login_url='crave_login')
def checkout_bag_validation(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            full_bag = data.get('bag', [])

            request.session['crave_cart'] = full_bag
            request.session.modified = True
            
            availability_errors_map = {} # Using a dictionary to group by ID
            integrity_errors = []

            customer = request.user.customer_profile

            # --- NEW: CATCH AND SAVE TERMINAL GENDER ---
            forced_gender = data.get('forced_gender')
            if forced_gender:
                safe_gender = forced_gender.lower()
                customer.gender = safe_gender
                customer.save()
                
                # Force database update to bypass memory caching
                type(customer).objects.filter(id=customer.id).update(gender=safe_gender)
                customer.refresh_from_db()

            # --- 0. CRITICAL: THE GENDER GATEKEEPER ---
            if not customer.gender or str(customer.gender).strip().lower() == 'none' or customer.gender.strip() == '':
                # Return the specific 400 status to trigger the modal in the JS!
                return JsonResponse({
                    'status': 'missing_gender',
                    'message': 'Gender is required for campus delivery routing.'
                }, status=400)

            # --- 1. THE BRAIN: GLOBAL STOCK CHECK ---
            # Step A: Calculate total demand for every unique item in the WHOLE bag
            global_demand = {}
            for pack in full_bag:
                for item in pack.get('items', []):
                    item_id = str(item.get('id'))
                    qty = int(item.get('qty', 0))
                    global_demand[item_id] = global_demand.get(item_id, 0) + qty

            # Step B: Validate that total demand against the database
            for item_id, total_requested in global_demand.items():
                product = Section_Product.objects.filter(id=item_id).first()
                
                # Helper to get the name from the payload if product check fails
                item_name = "Unknown Item"
                for p in full_bag:
                    for i in p.get('items', []):
                        if str(i.get('id')) == item_id:
                            item_name = i.get('name')
                            break

                if not product or not product.availability_status:
                    availability_errors_map[item_id] = {
                        'id': item_id,
                        'name': item_name,
                        'reason': "Currently Unavailable"
                    }
                elif product.stock_quantity < total_requested:
                    availability_errors_map[item_id] = {
                        'id': item_id,
                        'name': item_name,
                        'reason': f"Low Stock: You need {total_requested} total, but we only have {product.stock_quantity} left."
                    }

            # --- 2. ORIGINAL PACK INTEGRITY (Keep Per-Pack) ---
            for index, pack in enumerate(full_bag):
                items = pack.get('items', [])
                pack_size_id = pack.get('pack_size_id')
                
                is_loose_only = all(i.get('needsPack') == False for i in items)
                if not is_loose_only:
                    config = Pack_Size_Config.objects.filter(id=pack_size_id).first()
                    if config:
                        total_box_fill = sum(float(i.get('fillingValue', 0)) * int(i.get('qty', 0)) for i in items if i.get('needsPack'))
                        if total_box_fill > config.max_capacity:
                            integrity_errors.append(f"Pack {index + 1}: The lid won't close anymore!")

            # --- RESPONSE LOGIC ---
            if availability_errors_map:
                # Convert dict values to a list so the frontend gets one unique error per item
                return JsonResponse({
                    'status': 'availability_failed',
                    'errors': list(availability_errors_map.values())
                }, status=400)

            if integrity_errors:
                return JsonResponse({
                    'status': 'integrity_failed',
                    'message': integrity_errors[0]
                }, status=400)
            
            request.session['active_bag'] = full_bag

            return JsonResponse({'status': 'success', 'redirect': reverse('crave_checkout')})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'invalid_method'}, status=405)

# CAMPUS ORDER BYPASS VIEW (For Testing & Support)
@require_POST
@login_required(login_url='crave_login')
def validate_preferred_courier(request):
    """
    Checks if a requested VIP courier is valid, online, matches gender, 
    and has enough physical space (up to the +3 margin limit).
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        cart_volume = int(data.get('cart_volume', 0))
        target_gender = data.get('target_gender')

        if not username:
            return JsonResponse({'valid': False, 'error': 'Please enter a courier username.'})

        # 1. Identity Check
        courier = Courier.objects.filter(user_account__username=username, courier_category='CAMPUS').first()
        if not courier:
            return JsonResponse({'valid': False, 'error': 'Courier not found. Please check the username.'})

        # 2. Active Check
        if not courier.is_online:
            return JsonResponse({'valid': False, 'error': f'{username} is currently offline.'})

        # 3. Gender Check
        # If they are NOT the special override courier ("favour_"), enforce strict gender rules.
        is_vip_override = (courier.user_account.username == "favour_")
        
        if not is_vip_override and courier.gender.lower() != target_gender.lower():
            return JsonResponse({'valid': False, 'error': 'Courier gender does not match the delivery recipient.'})

        # 4. VIP Capacity Check (+3 Margin = 13 Max)
        active_batch = DeliveryBatch.objects.filter(
            courier=courier,
            status__in=['forming', 'assigned', 'in_transit']
        ).first()

        # If they survived the gender check, evaluate their bag space
        if active_batch:
            # Calculate current volume
            agg = University_Order.objects.filter(batch=active_batch).aggregate(current_sum=Sum('total_physical_packs_db'))
            current_volume = agg['current_sum'] or 0
            
            if (current_volume + cart_volume) > 13:
                excess = (current_volume + cart_volume) - 13
                return JsonResponse({
                    'valid': False, 
                    'error': f'Sorry, this courier is already full. Please reduce your order by {excess} Courion(s) so it will fit in their bag.'
                })

        return JsonResponse({'valid': True})
    
    except Exception as e:
        return JsonResponse({'valid': False, 'error': str(e)})

@login_required(login_url='crave_login')
def check_ping_status(request, ping_id):
    """
    The frontend calls this every 2 seconds to see if the kitchen staff has answered.
    """
    try:
        ping = get_object_or_404(VerificationPing, id=ping_id)
        
        if ping.status == 'pending':
            return JsonResponse({'status': 'pending'})
            
        sold_out_items = ping.flagged_items.filter(is_available=False)
        has_sold_out = sold_out_items.exists()
        sold_out_ids = list(sold_out_items.values_list('product_id', flat=True))
        
        # --- THE UPGRADE: Fetch Alternatives for the Mini Builder ---
        alternatives_payload = {}
        if has_sold_out:
            for ping_item in sold_out_items:
                prod = ping_item.product
                if prod.section:
                    # Get available items in the exact same section
                    alts = Section_Product.objects.filter(
                        section=prod.section, 
                        availability_status=True
                    ).exclude(id=prod.id)
                    
                    alt_list = []
                    for alt in alts:
                        # THE FIX: Using the correct DB fields (unit_price and filling_value)
                        alt_list.append({
                            'id': alt.id,
                            'name': alt.product_name,
                            'price': float(alt.unit_price), 
                            'image': alt.product_image.url if alt.product_image else '/static/images/placeholder.png',
                            'needsPack': getattr(alt, 'requires_pack', False),
                            'fillingValue': float(alt.filling_value), 
                            'sectionId': prod.section.id,
                            'sectionName': prod.section.name,
                            'notOrderedAlone': getattr(alt, 'not_ordered_alone', False),
                            'is_a_soup': getattr(alt, 'is_a_soup', False),
                            'need_soup': getattr(alt, 'need_soup', False),
                            'is_strange': getattr(alt, 'is_strange', False),
                            'strange_value': getattr(alt, 'strange_value', ''),
                            'has_charge': getattr(alt, 'has_charge', False)
                        })
                    alternatives_payload[str(prod.id)] = alt_list
        
        return JsonResponse({
            'status': 'resolved',
            'needs_rebuild': has_sold_out,
            'message': ping.interceptor_message if has_sold_out else "All items available!",
            'sold_out_ids': sold_out_ids,
            'alternatives': alternatives_payload
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
