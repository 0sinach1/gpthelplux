from os import link

from django.contrib.sessions.models import Session
import json
import uuid
import logging
import datetime
import random
from django.urls import reverse
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout, login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from MAIN.models import MasterOrder
from django.db.models import Prefetch, Q
from .network_providers import BaseNetworkProvider, NetworkOrderResolver, StandardNetworkProvider, CampusNetworkProvider
from .models import Courier, CourierAccessLog, CourierEngine, DeliveryBatch
from .forms import courierRegForm, CourierUpgradeForm
from MAIN.models import Customer, Vendor, Product, LUXAOrder
from luxa_crave.models import Campus_Engine_Order, University_Outlet, Pack_Size_Config, Section_Product, University_Order, VerificationPing
from escrow.models import Wallet, WalletTransaction
from .services import execute_order_restore
from allauth.account.signals import user_logged_in
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal
from datetime import timedelta


# Imports to handle mails
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.models import User
from allauth.account.models import EmailAddress # Important since you use django-allauth

logger = logging.getLogger(__name__)

# ------------------- 1. REGISTRATION & LOGIN -------------------

def register(request):
    # --- NEW INTERCEPTION LOGIC ---
    if request.user.is_authenticated:
        # If they are already a courier, send to dashboard
        if hasattr(request.user, 'courier_profile'):
            messages.info(request, "You are already registered as a courier.")
            return redirect('courier_dashboard')
        # If they are a customer without a courier profile, redirect to upgrade
        else:
            messages.info(request, "You already have an account! Please complete these extra details to become a courier.")
            return redirect('courier_upgrade')
    
    if request.method == "POST": 
        email_input = request.POST.get('email')
        if email_input and User.objects.filter(email=email_input).exists():
            if Courier.objects.filter(user_account__email=email_input).exists():
                messages.info(request, "You are already registered as a courier. Please log in.")
                return redirect('courierlogin') 
            
            form = courierRegForm(request.POST, request.FILES)
            form.add_error('email', "This email is already in use by a customer or vendor account.")
            return render(request, 'register/courier_reg.html', {"form": form})

        form = courierRegForm(request.POST, request.FILES)
        if form.is_valid():
            dob = form.cleaned_data.get('date_of_birth')
            profile_photo = form.cleaned_data.get('photo')
            gender = form.cleaned_data.get('gender')
            social_media_platform = form.cleaned_data.get('social_media_platform')
            social_media_handle = form.cleaned_data.get('social_media_handle')
            selected_university = form.cleaned_data.get('university_profile')
            try:
                with transaction.atomic():
                    user = form.save()
                    
                    EmailAddress.objects.get_or_create(user=user, email=user.email, defaults={'primary': True, 'verified': False})
                    
                    courier, created = Courier.objects.get_or_create(
                        user_account=user,
                        defaults={'date_of_birth': dob, 'photo': profile_photo, 'gender': gender, 'courier_student_profile_choices': selected_university, 'social_media_platform': social_media_platform, 'social_media_handle': social_media_handle}
                    )
                    if not created:
                        courier.date_of_birth = dob
                        courier.photo = profile_photo
                        courier.gender = gender
                        courier.courier_student_profile_choices = selected_university
                        courier.social_media_platform = social_media_platform
                        courier.social_media_handle = social_media_handle
                        courier.save()

                    # Generate token and send email
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    token = default_token_generator.make_token(user)
                    
                    verify_link = request.build_absolute_uri(
                        reverse('verify_courier_email', kwargs={'uidb64': uid, 'token': token})
                    )
                    
                    send_mail(
                        subject="Verify your Luxa Courier Account",
                        message=f"Welcome to the Luxa Fleet!\n\nTo ensure account security, please click the link below to verify your email address:\n\n{verify_link}",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )

                    messages.success(request, "Account created successfully! Please check your email to verify your account before logging in.")
                    return render(request, 'register/courier_reg.html', {"form": courierRegForm()})
                
            except IntegrityError:
                form.add_error(None, "An account with this email or username already exists.")
            except ValidationError as e:
                form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Registration error: {e}", exc_info=True)
                form.add_error(None, "An error occurred during registration.")
    else:
        form = courierRegForm()
    return render(request, 'register/courier_reg.html', {"form": form})

@login_required(login_url='login') # Replace 'login' with your customer login URL name
def courier_upgrade(request):
    # 1. If they already have a courier profile, send them straight to the dashboard
    if hasattr(request.user, 'courier_profile'):
        messages.info(request, "You are already a courier!")
        return redirect('courier_dashboard')

    if request.method == "POST":
        form = CourierUpgradeForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Extract the selected university
                    selected_university = form.cleaned_data.get('university_profile')
                    
                    # Create the courier profile linked to the existing user
                    courier = form.save(commit=False)
                    courier.user_account = request.user
                    courier.courier_student_profile_choices = selected_university
                    courier.is_verified = True
                    courier.save()

                    messages.success(request, "Welcome to the Fleet! Your courier profile has been created.")
                    return redirect('courierlogin')
            except Exception as e:
                logger.error(f"Courier Upgrade Error: {e}", exc_info=True)
                form.add_error(None, "An error occurred while upgrading your account.")
    else:
        form = CourierUpgradeForm()

    return render(request, 'register/courier_upgrade.html', {"form": form})

# VIEW FOR VERIFYING COURIER EMAIL
def verify_courier_email(request, uidb64, token):
    """ Verifies the emailed token and redirects to Login """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        # 1. Mark email as verified
        from allauth.account.models import EmailAddress
        EmailAddress.objects.filter(user=user, email=user.email).update(verified=True)
        
        # 2. Mark the Courier Profile as verified!
        if hasattr(user, 'courier_profile'):
            user.courier_profile.is_verified = True
            user.courier_profile.save()
        
        # 3. Redirect to Login (DO NOT auto-login)
        messages.success(request, "Email verified successfully! You can now log in.")
        return redirect('courierlogin') # Ensure this matches your urls.py name
        
    else:
        messages.error(request, "The verification link is invalid or has expired.")
        return redirect('courier_registration')

def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            try:
                courier = user.courier_profile
            except (AttributeError, Courier.DoesNotExist):
                messages.error(request, "Access Denied. You do not have a courier profile.")
                return redirect('courierlogin')

            # --- NEW 1: CHECK IF EMAIL IS VERIFIED --- # Redacted. Automatically verifies through gmail
            from allauth.account.models import EmailAddress
            email_is_verified = EmailAddress.objects.filter(user=user, verified=True).exists() 

            # --- NEW 2: CHECK ADMIN APPROVAL (Optional) ---
            # If you want admins to manually approve couriers before they can work:
            if not courier.is_verified:
                messages.error(request, "Your email is not verfied. Contact admin.")
                return redirect('courierlogin')

            # --- THE FIX: SEARCH FOR THE MASTER FINGERPRINT ---
            device_token = request.get_signed_cookie('trusted_device', default=None)

            is_recognized_device = CourierAccessLog.objects.filter(
                courier=courier, 
                authorized_device_id=device_token
            ).exists() if device_token else False

            # --- THE PRECISION KICK ---
            if not is_recognized_device:
                user_id = str(user.id)
                current_session_key = request.session.session_key 

                active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
                for s in active_sessions:
                    try:
                        data = s.get_decoded()
                        if str(data.get('_auth_user_id')) == user_id:
                            if s.session_key != current_session_key:
                                s.delete() 
                    except Exception:
                        continue

            login(request, user)

            # This overrides the global settings.py ONLY for this specific courier's session. UNDO THE COMMENTING AFTERWARDS
            # 600 seconds = 10 minutes.

            # request.session.set_expiry(60000)

            # --- TRIPLE-CHECK HANDSHAKE ---
            has_active_key = CourierAccessLog.is_access_granted(courier)

            if not is_recognized_device or not has_active_key:
                # NEW DEVICE or EXPIRED SHIFT: Trigger a new Master Key
                # BECAUSE we removed key generation from registration, a new user will trigger this perfectly!
                new_key_record = CourierAccessLog.regenerate_key(courier)

                # --- NEW: SEND THE ACCESS KEY VIA EMAIL ---
                try:
                    send_mail(
                        subject="Your Luxa Courier Daily Access Key",
                        message=(
                            f"Hello {user.first_name},\n\n"
                            f"Your new Daily Access Key for today's shift is: \n\n{new_key_record.daily_access_key}\n\n"
                            f"Please enter this key on the verification page to access your dashboard.\n\n"
                            f"Proceed cooly and calmly,\nThe Luxa Team."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False, 
                    )
                    messages.success(request, "Security check passed. Your Daily Key has been sent to your email.")
                except Exception as e:
                    logger.error(f"Failed to send daily key email to {user.email}: {e}")
                    messages.error(request, "Security check passed, but we had trouble emailing your key. Please contact admin.")
                
                request.session['pocket_key'] = None 
                request.session['daily_key_verified'] = False
                messages.success(request, "Security check passed. Please enter your Daily Key.")
                return redirect('verify_daily_key')

            # RECOGNIZED DEVICE + ACTIVE SHIFT:
            master_log = CourierAccessLog.objects.filter(courier=courier).latest('issued_at')
            
            request.session['pocket_key'] = master_log.daily_access_key
            request.session['daily_key_verified'] = True
            
            return redirect('courier_dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'register/courier_login.html', {'form': form})


@receiver(user_logged_in)
def secure_courier_google_login(sender, request, user, **kwargs):
    """
    INTERCEPTOR: Catches couriers who bypass login_view using Google OAuth.
    Enforces the 10-minute expiry, device fingerprint, and emails the daily key.
    """
    # We only care if the person logging in via Google is a Courier
    if hasattr(user, 'courier_profile'):
        courier = user.courier_profile
        
        # 1. Force the 10-minute session limit
        request.session.set_expiry(600)
        
        # 2. Search for the Master Fingerprint
        device_token = request.get_signed_cookie('trusted_device', default=None)
        is_recognized_device = CourierAccessLog.objects.filter(
            courier=courier, 
            authorized_device_id=device_token
        ).exists() if device_token else False
        
        has_active_key = CourierAccessLog.is_access_granted(courier)
        
        # 3. Apply the Tripwire logic exactly like login_view
        if not is_recognized_device or not has_active_key:
            new_key_record = CourierAccessLog.regenerate_key(courier)
            
            try:
                send_mail(
                    subject="Your Luxa Courier Daily Access Key",
                    message=(
                        f"Hello {user.first_name},\n\n"
                        f"Your new Daily Access Key for today's shift is: \n\n{new_key_record.daily_access_key}\n\n"
                        f"Please enter this key on the verification page to access your dashboard.\n\n"
                        f"Proceed cooly and calmly,\nThe Luxa Team."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False, 
                )
                messages.success(request, "Google Login successful. Your Daily Key has been sent to your email.")
            except Exception as e:
                logger.error(f"Failed to send daily key email to {user.email}: {e}")
                messages.error(request, "Google Login successful, but we had trouble emailing your key. Please contact admin.")
            
            # Lock the session so the dashboard tripwire kicks them to the verification page
            request.session['pocket_key'] = None 
            request.session['daily_key_verified'] = False
        else:
            # Recognized device + Active Shift -> Grant instant access
            master_log = CourierAccessLog.objects.filter(courier=courier).latest('issued_at')
            request.session['pocket_key'] = master_log.daily_access_key
            request.session['daily_key_verified'] = True


# ------------------- 2. DAILY KEY VERIFICATION & COURIER DASHBOARD -------------------

# COURIER IS ONLINE/OFFLINE TOGGLE
@login_required(login_url='courierlogin')
@require_POST
def toggle_courier_status(request):
    try:
        # Access the Courier profile directly
        courier = request.user.courier_profile
        
        # Simple Boolean Toggle
        courier.is_online = not courier.is_online
        courier.save(update_fields=['is_online'])
        
        return JsonResponse({'success': True, 'is_online': courier.is_online})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required(login_url='courierlogin')
def verify_daily_key(request):
    if request.method == "POST":
        input_key = request.POST.get('daily_key')
        courier = request.user.courier_profile
        
        latest_log = CourierAccessLog.objects.filter(
            courier=courier
        ).order_by('-issued_at').first()

        if latest_log and input_key == latest_log.daily_access_key:

            # >>> INJECTED DUAL GATE START <<<
            if not (courier.is_verified and courier.is_active):
                messages.warning(request, "Your account is successfully registered, but it is currently awaiting approval from the admin.")
                return redirect('verify_daily_key') 
            # >>> INJECTED DUAL GATE END <<<



            # --- THE FIX: GENERATE A UNIQUE HARDWARE-LEVEL TOKEN ---
            # This is unique to THIS browser session only.
            unique_device_token = str(uuid.uuid4()) 

            # Bind THIS specific token to the Database Master Record
            latest_log.authorized_device_id = unique_device_token
            latest_log.save(update_fields=['authorized_device_id'])

            # Seed the pocket with the key and the token
            request.session['daily_key_verified'] = True
            request.session['pocket_key'] = input_key
            
            response = redirect('courier_dashboard')
            
            # --- THE FIX: SET THE TOKEN IN THE SIGNED COOKIE ---
            # Now the browser carries this unique ID. 
            # If you open a different browser, it won't have this UUID.
            response.set_signed_cookie('trusted_device', unique_device_token, max_age=86400)
            
            messages.success(request, "Access Granted. Device fingerprint recorded.")
            return response
            
        else:
            messages.error(request, "Invalid Key.")
            
    return render(request, 'couriers/enter_daily_key.html')

@login_required(login_url='courierlogin')
def courier_base(request):
    # 1. Fetch the latest Master Record from DB
    try:
        courier = request.user.courier_profile
        engine = courier.engine

        # --- NEW: 8 PM AUTO-LOGOUT & OFFLINE ENFORCEMENT ---
        now = timezone.localtime(timezone.now())
        # If time is 8:00 PM (20:00) or later, OR before 5:00 AM
        if now.hour >= 20 or now.hour < 5: 
            if courier.user_account.username == "favour_":
                return
            courier.is_online = False
            courier.save(update_fields=['is_online'])
            engine.status = 'offline'
            engine.save(update_fields=['status'])
            
            logout(request)
            messages.warning(request, "Shift Ended: The system automatically logs out all couriers at 8:00 PM.")
            return redirect('courierlogin')

        # --- AUTO-REGENERATE IF EXPIRED ---
        # If the shift clock (11:21 AM) has passed, generate the NEW key 
        # BEFORE we do anything else.
        if not CourierAccessLog.is_access_granted(courier):
            CourierAccessLog.regenerate_key(courier)
            request.session['daily_key_verified'] = False
            request.session['pocket_key'] = None
            messages.info(request, "New shift started. A new key has been generated.")
            return redirect('verify_daily_key')
        # ---------------------------------------


        latest_log = CourierAccessLog.objects.filter(courier=courier).latest('issued_at')
    except (AttributeError, Courier.DoesNotExist, CourierAccessLog.DoesNotExist):
        return HttpResponse("Unauthorized", status=403)

    # --- THE NUCLEAR TRIPWIRE (PER-CLICK CHECK) ---
    
    # Grab the "Pocket Key" (replica) and the "Cookie ID" from the device
    pocket_key = request.session.get('pocket_key')
    device_cookie_id = request.get_signed_cookie('trusted_device', default=None)

    # CHECK A: Does the Pocket Key match the Master Key?
    # CHECK B: Does this Device Cookie match the Authorized Master Cookie?
    is_key_valid = (pocket_key == latest_log.daily_access_key)
    is_device_authorized = (device_cookie_id == latest_log.authorized_device_id)

    if not is_key_valid or not is_device_authorized:
        # IF KEY IS CORRECT BUT COOKIE IS WRONG = BREACH DETECTED
        if is_key_valid and not is_device_authorized:
            # TRIGGER NUCLEAR RESET: Destroy the key for everyone
            CourierAccessLog.regenerate_key(courier)
            messages.error(request, "Security Alert: Unauthorized device detected. Key has been reset.")
        else:
            # Shift likely reset or session expired
            messages.info(request, "Session expired or shift reset. Please re-verify.")

        # Wipe the session clean and kick to verification
        request.session['daily_key_verified'] = False
        request.session['pocket_key'] = None
        return redirect('verify_daily_key')
    
    # --- END TRIPWIRE ---

    # Your original 11:21 AM check (as a backup safety layer)
    if not engine.has_active_session:
        request.session['daily_key_verified'] = False
        messages.info(request, "Shift reset. Please enter the new daily key.")
        return redirect('verify_daily_key')

    engine.refresh_load()
    context = {
        "courier": courier,
        "engine": engine,
        "max_stops": engine.max_stop_limit,
        "current_load": engine.current_stop_load,
    }
    return render(request, 'couriers/courierbase.html', context)

@login_required(login_url='courierlogin')
def courier_dashboard(request):
    if not hasattr(request.user, 'courier_profile'):
        # If they don't have a courier profile, redirect them away
        return redirect('index')

    if request.user.courier_profile.courier_category == "EXTERNAL_UPDATER":
        return redirect('campus_availability_manager')

    # --- THE FIX: THE BOUNCER ---
    # Because Google Login can't redirect them to the verify page directly, 
    # the dashboard must catch them and bounce them there.
    if not request.session.get('daily_key_verified', False):
        return redirect('verify_daily_key')

    courier = request.user.courier_profile
    engine = courier.engine
    user_id = request.user.id

    # --- 1. SECURITY & WALLET ---
    # ... (Keep your existing security/tripwire checks) ...

    courier_wallet, _ = Wallet.objects.get_or_create(
        user=request.user,
        wallet_type=Wallet.WalletType.COURIER,
        defaults={'currency': 'NGN'}
    )

    advance_wallet, _ = Wallet.objects.get_or_create(
        user=request.user,
        wallet_type=Wallet.WalletType.COURIER_ADVANCE,
        defaults={'currency': 'NGN'}
    )

    recent_transactions = courier_wallet.transactions.all().order_by('-timestamp')[:15]

    ## --- 2. MODULAR NETWORK FETCHING ---
    providers = [
        StandardNetworkProvider(),
        CampusNetworkProvider()
    ]

    assignments = {
        'new': [],
        'transit': [],
        'history': [],
        'returns': [],
        'forming': [],
        'completed_orders': []
    }

    # --- DEDUPLICATION TRACKER ---
    seen_batch_ids = {
        'new': set(),
        'transit': set(),
        'history': set(),
        'forming': set()
    }

    for provider in providers:
        data = provider.get_data(courier)
        for key in assignments.keys():
            provider_data = data.get(key, [])
            
            for item in provider_data:
                # If this bucket holds batches, deduplicate them by their Primary Key
                if key in seen_batch_ids:
                    if item.pk not in seen_batch_ids[key]:
                        seen_batch_ids[key].add(item.pk)
                        assignments[key].append(item)
                else:
                    # For 'returns' (which are individual orders), just append them
                    assignments[key].append(item)

    # --- 3. LOGISTICS & CALCULATIONS ---
    assignments['history'].sort(key=lambda x: getattr(x, 'created_at', None) or getattr(x, 'pk', 0), reverse=True)

    # Refresh Engine State
    engine.refresh_load()

    forming_batch = len(assignments.get('forming', [])) > 0

    # --- NEW: FETCH ACTUAL SCAVENGER ORDERS FOR UI ---
    scavenger_orders = []
    active_batch = DeliveryBatch.objects.filter(courier=courier, status__in=['assigned', 'in_transit']).first()
    
    if active_batch:
        current_volume = active_batch.total_volume or 0
        available_space = 15 - current_volume
        
        if available_space > 0:
            dump_username = "Dumped_Campus_Female_Orders" if courier.gender.lower() == 'female' else "Dumped_Campus_Male_Orders"
            
            scavenger_orders = Campus_Engine_Order.objects.filter(
                status='dumped',
                assigned_campus_courier__user_account__username=dump_username,
                raw_order__total_physical_packs_db__lte=available_space,
            ).order_by('raw_order__order_date')[:5] 


    # --- 4. COUNT THE ACTUAL ORDERS FOR THE BADGES ---
    badge_counts = {
        'new': 0,
        'transit': 0
    }

    for key in ['new', 'transit']:
        for batch in assignments[key]:
            # Safely get the length of the prefetched standard and campus orders
            standard_count = len(batch.orders.all()) if hasattr(batch, 'orders') else 0
            campus_count = len(batch.campus_orders.all()) if hasattr(batch, 'campus_orders') else 0
            
            badge_counts[key] += (standard_count + campus_count)

    all_outlets = University_Outlet.objects.all()

    context = {
        "courier": courier,
        "wallet": courier_wallet,
        "advance_wallet": advance_wallet,
        "recent_transactions": recent_transactions,
        "current_load": engine.current_stop_load,
        
        "assignments": assignments, 
        "badge_counts": badge_counts, # <-- Passed down to your template!
        'forming_batch': forming_batch,   
        "scavenger_orders": scavenger_orders,
        "available_scavenger_space": 15 - (active_batch.total_volume or 0) if active_batch else 0,
        "user_id": user_id, 
        "all_outlets": all_outlets,
    }

    return render(request, 'couriers/courier_dashboard.html', context)

def get_new_batches_fragment(request):
    courier = request.user.courier_profile 
    
    # 1. List of active networks
    providers = [StandardNetworkProvider(), CampusNetworkProvider()]

    # 2. Collect 'Instructions' from all networks
    combined_prefetches = []
    for provider in providers:
        combined_prefetches.extend(provider.get_prefetch_requirements())

    # 3. One single optimized database hit for ALL networks
    all_batches = DeliveryBatch.objects.filter(
        courier=courier
    ).prefetch_related(*combined_prefetches).order_by('-created_at')

    # 4. Filter into buckets for the HTML
    return render(request, 'couriers/partials/batch_list.html', {
            'assignments': {
                'new': all_batches.filter(status='assigned'),
                'transit': all_batches.filter(status='in_transit'),
                'forming': all_batches.filter(status='forming'),
            }
        })

def get_active_batch_fragment(request):
    # This powers the specific "Active Trip" sidebar/section
    courier = request.user.courier_profile 
    providers = [StandardNetworkProvider(), CampusNetworkProvider()]
    
    combined_prefetches = []
    for provider in providers:
        combined_prefetches.extend(provider.get_prefetch_requirements())

    active_batches = DeliveryBatch.objects.filter(
        courier=courier, 
        status='in_transit'
    ).prefetch_related(*combined_prefetches).order_by('-created_at')

    return render(request, 'couriers/partials/active-batch-list.html', {
        'active_batches': active_batches,
    })

@login_required(login_url='courierlogin')
def get_order_details_snippet(request, order_id):
    order, network_type = NetworkOrderResolver.get_order_by_id(order_id)
    
    if not order:
        return HttpResponse("Order not found", status=404)

    # Modular Provider Selection
    providers = {
        'standard': StandardNetworkProvider(),
        'campus': CampusNetworkProvider(),
    }
    
    provider = providers.get(network_type, BaseNetworkProvider())
    context = provider.get_manifest_context(order)
    
    # Render using the template path provided by the Network Provider
    return render(request, context['template'], context)

# Get returned/cancelled orders
@login_required(login_url='courierlogin')
def get_returns_fragment(request):
    """HTMX endpoint to refresh the Returns & Cancellations panel."""
    if not hasattr(request.user, 'courier_profile'):
        return HttpResponse("Unauthorized", status=401)
        
    courier = request.user.courier_profile 
    providers = [StandardNetworkProvider(), CampusNetworkProvider()]
    
    assignments = {'returns': []}
    
    for provider in providers:
        data = provider.get_data(courier)
        assignments['returns'].extend(list(data.get('returns', [])))

    # Sort them by date to keep the most recent issues at the top
    assignments['returns'].sort(
        key=lambda x: getattr(x, 'created_at', None) or getattr(x, 'pk', 0), 
        reverse=True
    )

    return render(request, 'couriers/partials/returns_list.html', {
        'assignments': assignments,
    })

@login_required
def get_advance_courier_wallet_balance(request):
    advance_wallet = Wallet.objects.get(user=request.user, wallet_type=Wallet.WalletType.COURIER_ADVANCE)
    # Return JUST the inner HTML of the balance box
    return render(request, 'couriers/partials/advance_wallet_balance.html', {'advance_wallet': advance_wallet})


# =================================================================
# INTERCEPTOR DASHBOARD APIs (UPGRADED WITH DATA-DRIVEN ALTERNATIVES)
# =================================================================
from django.utils.timesince import timesince

@login_required(login_url='courierlogin')
def api_get_interceptor_pings(request):
    """Fetches pending stock verifications AND their section alternatives."""
    courier = getattr(request.user, 'courier_profile', None)
    
    # --- NEW: FILTER BY ASSIGNED OUTLET ---
    if courier and getattr(courier, 'interceptor_outlet', None):
        pings = VerificationPing.objects.filter(
            status='pending', 
            outlet=courier.interceptor_outlet
        ).order_by('created_at')
    else:
        # If they haven't picked an outlet from the dropdown yet, return nothing.
        pings = VerificationPing.objects.none()
    
    data = []
    for ping in pings:
        items = []
        for ping_item in ping.flagged_items.all():
            prod = ping_item.product
            
            # THE UPGRADE: Fetch other products in the EXACT same section
            alts_data = []
            if prod.section:
                alternatives = Section_Product.objects.filter(section=prod.section).exclude(id=prod.id)
                for alt in alternatives:
                    alts_data.append({
                        'id': alt.id,
                        'name': alt.product_name,
                        'image': alt.product_image.url if alt.product_image else '/static/images/placeholder.png',
                        'is_available': alt.availability_status
                    })
                    
            items.append({
                'id': prod.id,
                'name': prod.product_name,
                'image': prod.product_image.url if prod.product_image else '/static/images/placeholder.png',
                'section_name': prod.section.name if prod.section else 'General',
                'alternatives': alts_data
            })
            
        data.append({
            'ping_id': ping.id,
            'outlet_name': ping.outlet.name,
            'time_ago': timesince(ping.created_at).split(',')[0] + " ago",
            'items': items,
            'raw_ping': ping.id # Just in case we need it
        })
        
    return JsonResponse({'success': True, 'pings': data})

@require_POST
@login_required(login_url='courierlogin')
def api_resolve_ping(request):
    """
    Submits the verification for BOTH the flagged items and the alternatives.
    Auto-generates the customer message based on the data.
    """
    try:
        data = json.loads(request.body)
        ping_id = data.get('ping_id')
        products_status = data.get('products', {}) # Includes primary items AND alternatives
        
        ping = get_object_or_404(VerificationPing, id=ping_id)

        with transaction.atomic():
            # 1. Update the original ping item records
            for ping_item in ping.flagged_items.all():
                prod_id_str = str(ping_item.product.id)
                if prod_id_str in products_status:
                    ping_item.is_available = products_status[prod_id_str]
                    ping_item.save(update_fields=['is_available'])

            # 2. Update the ACTUAL database for EVERY item toggled (Primary + Alternatives)
            sold_out_names = []
            for prod_id_str, is_available in products_status.items():
                product = Section_Product.objects.filter(id=int(prod_id_str)).first()
                if product:
                    product.availability_status = is_available
                    product.last_updated_availability = timezone.now() # Resets the 45-min timer!
                    product.save(update_fields=['availability_status', 'last_updated_availability'])
                    
                    if not is_available:
                        sold_out_names.append(product.product_name)

            # 3. THE UPGRADE: Auto-Generate the message instead of forcing them to type it
            if sold_out_names:
                ping.interceptor_message = f"Kitchen Update: {', '.join(sold_out_names)} is currently sold out. Please select from the available alternatives in the menu."
            else:
                ping.interceptor_message = "All items available!"

            ping.status = 'resolved'
            ping.resolved_at = timezone.now()
            ping.save()

        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# Updates the campus outlet from the courier dashboard page
@require_POST
@login_required(login_url='courierlogin')
def update_interceptor_outlet(request):
    """Updates the courier's assigned interceptor outlet on the fly."""
    try:
        data = json.loads(request.body)
        outlet_id = data.get('outlet_id')
        courier = request.user.courier_profile
        
        if outlet_id:
            # Assuming you imported University_Outlet
            outlet = get_object_or_404(University_Outlet, id=outlet_id)
            courier.interceptor_outlet = outlet
        else:
            courier.interceptor_outlet = None
            
        courier.save(update_fields=['interceptor_outlet'])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ------------------- 3. LOGOUT & ADMIN TOOLS -------------------

def logout_view(request):
    if hasattr(request.user, 'courier_profile'):
        courier = request.user.courier_profile
        engine = courier.engine
        
        # Logic: Prevent logout if work is still in progress
        engine.refresh_load() 
        if engine.current_stop_load > 0:
            messages.error(request, f"Logout Denied! You have {engine.current_stop_load} pending stops.")
            return redirect('courier_dashboard')
        
        # --- Turn courier offline on manual logout ---
        courier.is_online = False
        courier.save(update_fields=['is_online'])

        engine.status = 'offline'
        engine.save()

    logout(request) 
    messages.info(request, "You have been logged out.")
    return redirect('courierlogin')

def admin_key_monitor_login(request):
    """ Fixed login view for Axes compatibility """
    # If already staff and logged in, skip login
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('key_monitor')

    error_message = None
    if request.method == "POST":
        # 1. AuthenticationForm automatically calls authenticate() internally,
        # passing the request object (which keeps django-axes perfectly happy).
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            # 2. Grab the securely authenticated user directly from the form!
            # This prevents double-authenticating and bypasses backend parameter mismatches.
            user = form.get_user()

            if user.is_staff:
                auth_login(request, user)
                return redirect('key_monitor')
            else:
                error_message = "Access Denied: Staff status required to view this monitor."
        else:
            # 3. If Axes locks the account or the password is wrong, the form catches it.
            # We extract the exact error message so you actually know WHY it failed!
            if form.non_field_errors():
                error_message = form.non_field_errors()[0]
            else:
                error_message = "Invalid username or password."

    # Highlight: Ensure this matches your file name monitor_auth.html
    return render(request, 'couriers/monitor_auth.html', {
        'error_message': error_message
    })

def admin_key_monitor(request):

    # THE SECURITY GATE: Redirects back to your custom login if they aren't staff
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('monitor_login')
    # --- HIGHLIGHTED CHANGES START HERE ---
    
    # 1. Use LOCALTIME instead of UTC
    # This ensures "11:21" matches your actual clock time
    now = timezone.localtime(timezone.now())
    
    # 2. Calculate the LOCAL shift start
    shift_start = now.replace(hour=5, minute=0, second=0, microsecond=0)
    
    if now < shift_start:
        shift_start -= datetime.timedelta(days=1)

    # 3. FETCH THE LOGS
    # We remove .distinct('courier') here to prevent database errors 
    # and handle it in Python to ensure visibility.
    all_active_logs = CourierAccessLog.objects.filter(
        issued_at__gte=shift_start
    ).select_related(
        'courier__user_account'
    ).order_by('-issued_at') # Newest keys first

    # 4. MANUAL UNIQUE FILTER (Ensures you only see the LATEST key per courier)
    seen_couriers = set()
    active_logs = []
    for log in all_active_logs:
        if log.courier_id not in seen_couriers:
            active_logs.append(log)
            seen_couriers.add(log.courier_id)
            
    # --- HIGHLIGHTED CHANGES END HERE ---

    context = {
        'active_logs': active_logs,
        'current_time': now,
        'shift_start_debug': shift_start, # Useful for testing
    }
    return render(request, 'couriers/key_monitor.html', context)

def admin_key_monitor_logout(request):
    """Logs out the staff member and sends them back to the monitor login gate."""
    auth_logout(request)
    return redirect('monitor_login')

# --- SECURITY HELPER ---
def _is_escrow_admin(user):
    """Returns True ONLY if the user is a Courier with active Escrow Admin clearance."""
    if not hasattr(user, 'courier_profile'): 
        return False
    courier = user.courier_profile
    if not hasattr(courier, 'admin_profile'): 
        return False
    return courier.admin_profile.can_manage_escrow



# =================================================================
# ADMIN ESCROW MANAGEMENT DASHBOARD & APIs
# =================================================================

# --- 1. MAIN DASHBOARD VIEW ---
@login_required(login_url='courierlogin')
def admin_escrow_manager(request):
    if not _is_escrow_admin(request.user):
        messages.error(request, "Access Denied: You do not have Escrow Administrator clearance.")
        return redirect('courier_dashboard')

    return render(request, 'dashboards/wallet_manager.html', {
        'admin_profile': request.user.courier_profile.admin_profile,
        'courier': request.user.courier_profile
    })


# --- 2. THE SEARCH API (HTMX) ---
@login_required(login_url='courierlogin')
def escrow_search_user(request):
    """Fetches user wallets and transactions for the Ledger."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("<div class='alert error'>Unauthorized</div>", status=403)

    query = request.GET.get('q', '').strip()
    if not query:
        return HttpResponse("<div style='text-align: center; padding: 30px; color: #64748b;'>Please enter a search term.</div>")

    # 1. Search for the user (Exact Email, Exact Username, or matching First/Last Name)
    target_user = User.objects.filter(
        Q(email__iexact=query) | 
        Q(username__iexact=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).first()

    if not target_user:
        return HttpResponse(f"<div style='text-align: center; padding: 30px; color: #ef4444;'><i class='bi bi-exclamation-circle' style='font-size: 2rem; display: block; margin-bottom: 10px;'></i>No user found matching '{query}'.</div>")

    # 2. Fetch all possible wallets
    customer_wallet = Wallet.objects.filter(user=target_user, wallet_type='CUSTOMER').first()
    courier_wallet = Wallet.objects.filter(user=target_user, wallet_type='COURIER').first()
    advance_wallet = Wallet.objects.filter(user=target_user, wallet_type='COURIER_ADVANCE').first()

    # 3. Identify Profile Type & Info
    profile_type = "Customer"
    phone_number = "-"
    if hasattr(target_user, 'courier_profile'):
        profile_type = "Courier"
        # Assuming phone is stored on the customer profile which is linked to the user
        if hasattr(target_user, 'customer_profile'):
            phone_number = target_user.customer_profile.phone_number
    elif hasattr(target_user, 'customer_profile'):
        profile_type = "Customer"
        phone_number = target_user.customer_profile.phone_number

    # 4. Fetch the last 100 transactions for this user across all wallets
    transactions = WalletTransaction.objects.filter(wallet__user=target_user).order_by('-timestamp')[:100]

    context = {
        'target_user': target_user,
        'profile_type': profile_type,
        'phone_number': phone_number,
        'customer_wallet': customer_wallet,
        'courier_wallet': courier_wallet,
        'advance_wallet': advance_wallet,
        'transactions': transactions,
    }
    
    return render(request, 'dashboards/partials/escrow_user_result.html', context)

# --- 3. THE GLOBAL TRANSACTION FEED (HTMX) ---
@login_required(login_url='courierlogin')
def escrow_global_transactions(request):
    """Fetches the global transaction feed with optional filtering."""
    # Ensure you are using the _is_escrow_admin helper we created earlier!
    if not _is_escrow_admin(request.user):
        return HttpResponse("<div class='alert error'>Unauthorized</div>", status=403)

    wallet_type = request.GET.get('wallet_type', 'all')
    txn_type = request.GET.get('txn_type', 'all')

    # Base query: Get latest 100 transactions, joining the user table for speed
    transactions = WalletTransaction.objects.all().select_related('wallet__user').order_by('-timestamp')

    # 1. Apply Wallet Filter
    if wallet_type != 'all':
        transactions = transactions.filter(wallet__wallet_type=wallet_type)

    # 2. Apply Transaction Type Filter
    if txn_type != 'all':
        if txn_type == 'credits':
            transactions = transactions.filter(transaction_type__in=['CREDIT', 'DEPOSIT', 'PURCHASE_RELEASE'])
        elif txn_type == 'debits':
            transactions = transactions.filter(transaction_type__in=['DEBIT', 'WITHDRAWAL'])
        elif txn_type == 'locks':
            transactions = transactions.filter(transaction_type='PURCHASE_LOCK')

    # Limit to latest 100 to keep the page lightning fast
    transactions = transactions[:100]

    return render(request, 'dashboards/partials/global_txn_rows.html', {'transactions': transactions})

# --- 4. THE MANUAL TRANSACTION API ---
@login_required(login_url='courierlogin')
@require_POST
def escrow_manual_transaction(request):
    """API Endpoint for Admins to manually move funds and generate receipts."""
    
    # 1. SECURITY GATE: Ensure they are an active Escrow Admin
    if not hasattr(request.user, 'courier_profile') or not hasattr(request.user.courier_profile, 'admin_profile') or not request.user.courier_profile.admin_profile.can_manage_escrow:
        return JsonResponse({'error': 'Unauthorized. Admin badge required.'}, status=403)

    try:
        # 2. PARSE THE DATA
        data = json.loads(request.body)
        target_identifier = data.get('target_user', '').strip()
        wallet_type = data.get('wallet_type')
        action_type = data.get('action_type') # 'CREDIT' or 'DEBIT'
        amount = Decimal(data.get('amount', '0'))
        admin_note = data.get('admin_note', '').strip()

        if amount <= 0:
            return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)

        # 3. FIND TARGET USER (By exact email or exact username)
        target_user = User.objects.filter(
            Q(email__iexact=target_identifier) | Q(username__iexact=target_identifier)
        ).first()

        if not target_user:
            return JsonResponse({'error': f'No user found with email or username: {target_identifier}'}, status=404)

        # 4. EXECUTE ATOMIC TRANSACTION
        with transaction.atomic():
            # Get or create the wallet, and lock the row for safety
            wallet, _ = Wallet.objects.get_or_create(user=target_user, wallet_type=wallet_type)
            wallet = Wallet.objects.select_for_update().get(id=wallet.id)

            # Prevent overdrafts
            if action_type == 'DEBIT' and wallet.available_balance < amount:
                return JsonResponse({'error': f"Insufficient funds. {target_user.username}'s wallet only has ₦{wallet.available_balance}."}, status=400)

            # Apply the Math
            if action_type == 'CREDIT':
                wallet.available_balance += amount
                tx_amount = amount
            else: # DEBIT
                wallet.available_balance -= amount
                tx_amount = -amount

            wallet.save()

            # 5. GENERATE THE PERMANENT RECEIPT
            ref = f"ADMIN-{uuid.uuid4().hex[:8].upper()}"

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=action_type,
                amount=tx_amount,
                running_balance=wallet.available_balance,
                reference=ref,
                description=f"{admin_note} (By Admin: {request.user.username})"
            )

        return JsonResponse({
            'success': True,
            'message': f"Successfully {action_type.lower()}ed ₦{amount} for {target_user.username}."
        })

    except Exception as e:
        print(f"Fund Mover Error: {e}")
        return JsonResponse({'error': "An internal server error occurred."}, status=500)


# --- 5. THE EMERGENCY ORDER CANCELLATION & ESCROW REFUND TOOL ---
@login_required(login_url='courierlogin')
@require_POST
def escrow_order_medic(request):
    """Emergency Order Cancellation and Escrow Refund Tool"""
    
    # Security Gate
    if not _is_escrow_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        order_number = data.get('order_number', '').strip()
        
        # Clean the input in case the admin pastes the "#" symbol
        if order_number.startswith('#'):
            order_number = order_number[1:]

        # 1. FIND THE ORDER
        from luxa_crave.models import University_Order
        order = University_Order.objects.filter(order_number__iexact=order_number).first()
        
        if not order:
            return JsonResponse({'error': f'Could not find Campus Order: {order_number}'}, status=404)

        # 2. STATUS CHECK (Prevent tampering with finished orders)
        if order.status in ['delivered', 'completed', 'cancelled', 'refunded']:
            return JsonResponse({'error': f'Order is already {order.status} and cannot be modified.'}, status=400)

        with transaction.atomic():
            # 3. CANCEL THE ORDER
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            
            # 4. REFUND THE CUSTOMER
            # THE FIX: Safely pass the Primary Key (.pk) instead of the hardcoded .id!
            from escrow.services import refund_university_order
            refund_university_order(order.pk)

            # 5. BULLETPROOF CLAWBACK COURIER ADVANCE
            # Search globally for the exact payout receipt, regardless of current batch status
            payout_receipts = WalletTransaction.objects.filter(
                transaction_type='CREDIT',
                reference__startswith=f"ORDER-ADV-{order.pk}-B-"
            )

            # Loop through every time this order was paid out
            for receipt in payout_receipts:
                adv_wallet = receipt.wallet 
                
                # Make the clawback reference totally unique by appending the receipt ID
                clawback_ref = f"CLAWBACK-{order.pk}-FROM-{receipt.idempotency_key}"
                
                # Idempotency check to prevent double-clawbacks
                if not WalletTransaction.objects.filter(reference=clawback_ref).exists():
                    clawback_amount = receipt.amount
                    
                    # 1. Remove the funds from the courier
                    adv_wallet.available_balance -= clawback_amount
                    adv_wallet.save(update_fields=['available_balance'])
                    
                    # 2. Generate the permanent clawback receipt
                    WalletTransaction.objects.create(
                        wallet=adv_wallet,
                        transaction_type='DEBIT',
                        amount=-clawback_amount,
                        running_balance=adv_wallet.available_balance,
                        reference=clawback_ref,
                        description=f"Clawback: Order #{order.order_number} Cancelled"
                    )

            # 6. ENGINE CLEANUP
            if hasattr(order, 'engine_view') and order.engine_view:
                engine_order = order.engine_view
                engine_order.status = 'failed' 
                engine_order.save(update_fields=['status'])
                
            # Check if cancelling this order makes the courier's batch empty/finished
            if getattr(order, 'batch', None):
                order.batch.check_batch_burn()

        return JsonResponse({
            'success': True, 
            'message': f'Order {order.order_number} successfully cancelled, refunded, and advance clawed back.'
        })

    except Exception as e:
        print(f"Order Medic Error: {e}")
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)
    

# --- 6. THE CAMPUS ORDERS API & DETAILS VIEW ---
@login_required(login_url='courierlogin')
def escrow_campus_orders_api(request):
    """Fetches the list of all Campus Orders for the Audit Ledger."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("<div class='alert error'>Unauthorized</div>", status=403)

    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')
    
    # Base query: Fetch latest 100 orders, joining the customer for speed
    orders = University_Order.objects.select_related('customer__user_account').order_by('-order_date')
    
    # --- NEW: APPLY STATUS FILTER ---
    if status_filter != 'all':
        orders = orders.filter(status=status_filter)
    
    # APPLY SEARCH FILTER
    if query:
        orders = orders.filter(
            Q(order_number__icontains=query) | 
            Q(customer__user_account__username__icontains=query) |
            Q(customer__user_account__email__icontains=query)
        )
        
    orders = orders[:100] # Limit to keep it lightning fast

    return render(request, 'dashboards/partials/campus_order_rows.html', {'orders': orders})

@login_required(login_url='courierlogin')
def escrow_campus_order_details(request, order_id):
    """Fetches the deep-dive details of a specific order for the Modal."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("Unauthorized", status=403)
        
    # We prefetch the packs, items, and products so the template doesn't hammer the database
    order = get_object_or_404(
        University_Order.objects.prefetch_related('packs__items__product', 'engine_view', 'building'), 
        pk=order_id
    )
    
    return render(request, 'dashboards/partials/campus_order_details.html', {'order': order})

@login_required(login_url='courierlogin')
def escrow_user_autocomplete(request):
    """Provides instant dropdown suggestions as the admin types a username."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("")

    query = request.GET.get('q', '').strip()
    
    # Don't search if the query is too short (saves database load)
    if len(query) < 2:
        return HttpResponse("")

    # Find top 5 matches
    users = User.objects.filter(
        Q(username__icontains=query) | 
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    )[:5]

    return render(request, 'dashboards/partials/user_autocomplete_dropdown.html', {'users': users})

from couriers.models import Courier

@login_required(login_url='courierlogin')
def escrow_delivery_batches_api(request):
    """Fetches the list of Batches for the Admin Table."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("<div class='alert error'>Unauthorized</div>", status=403)

    try:
        query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', 'all')
        
        # 1. Select Related is kept, but we remove the aggressive prefetch just in case it was crashing
        batches = DeliveryBatch.objects.select_related('courier', 'courier__user_account').order_by('-created_at')
        
        # 2. THE FIX: If 'all' is selected, we ACTUALLY show all! No more excluding completed batches.
        if status_filter != 'all':
            batches = batches.filter(status=status_filter)
            
        if query:
            batches = batches.filter(
                Q(batch_id__icontains=query) | 
                Q(courier__user_account__username__icontains=query)
            )
            
        batches = batches[:50]
        
        return render(request, 'dashboards/partials/delivery_batch_rows.html', {'batches': batches})
        
    except Exception as e:
        # THE FAIL-SAFE: If the database query crashes, print the error directly inside the table!
        print(f"Batch Fetch Error: {e}")
        return HttpResponse(f"<tr><td colspan='7' style='text-align: center; color: #ef4444; padding: 20px; background: #fef2f2;'><strong>Backend Error:</strong> {str(e)}</td></tr>")

@login_required(login_url='courierlogin')
def escrow_batch_details_api(request, batch_id):
    """Renders the Details and the Reassignment Tool inside the Modal."""
    if not _is_escrow_admin(request.user): 
        return HttpResponse("Unauthorized", status=403)
    
    # We prefetch the orders so the template can list them efficiently
    batch = get_object_or_404(DeliveryBatch.objects.prefetch_related('campus_orders__customer__user_account'), id=batch_id)
    
    # Find active couriers who don't already have this batch
    available_couriers = Courier.objects.filter(
        is_online=True, 
        courier_category='CAMPUS'
    ).exclude(id=batch.courier.id).select_related('user_account')

    # NEW: Render the template instead of building a string
    context = {
        'batch': batch,
        'available_couriers': available_couriers
    }
    return render(request, 'dashboards/partials/delivery_batch_details.html', context)

@login_required(login_url='courierlogin')
@require_POST
def escrow_reassign_batch_api(request):
    """The Safe 4-Step Escrow Swap and Sync"""
    if not _is_escrow_admin(request.user): return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        batch_id = data.get('batch_id')
        new_courier_id = data.get('new_courier_id')

        with transaction.atomic():
            batch = DeliveryBatch.objects.select_for_update().get(id=batch_id)
            old_courier = batch.courier
            new_courier = Courier.objects.get(id=new_courier_id)

            if batch.status in ['completed', 'cancelled']:
                return JsonResponse({'error': 'Cannot reassign a finished batch.'}, status=400)

            # STEP 1: CLAWBACK FROM OLD COURIER
            from escrow.services import get_wallet # Import the helper
            old_c_wallet = get_wallet(old_courier.user_account, Wallet.WalletType.COURIER_ADVANCE)
            
            for order in batch.campus_orders.all():
                old_payout_ref = f"ORDER-ADV-{order.pk}-B-{batch.pk}"
                payout_receipt = WalletTransaction.objects.filter(
                    wallet=old_c_wallet, reference=old_payout_ref, transaction_type='CREDIT'
                ).first()

                if payout_receipt:
                    clawback_ref = f"REASSIGN-CLAWBACK-{order.pk}-FROM-{batch.pk}"
                    if not WalletTransaction.objects.filter(reference=clawback_ref).exists():
                        clawback_amt = payout_receipt.amount
                        old_c_wallet.available_balance -= clawback_amt
                        old_c_wallet.save(update_fields=['available_balance'])

                        WalletTransaction.objects.create(
                            wallet=old_c_wallet, transaction_type='DEBIT', amount=-clawback_amt,
                            running_balance=old_c_wallet.available_balance, reference=clawback_ref,
                            description=f"Batch Reassignment Clawback: Order #{order.order_number}"
                        )

            # STEP 2 & 3: SWAP COURIER AND SYNC ENGINE
            batch.courier = new_courier
            batch.status = 'assigned' # Force to assigned so they can 'Start Trip' again
            batch.assigned_at = timezone.now()
            batch.save(update_fields=['courier', 'status', 'assigned_at'])

            for order in batch.campus_orders.all():
                order.status = 'processing'
                order.save(update_fields=['status'])
                if hasattr(order, 'engine_view') and order.engine_view:
                    engine = order.engine_view
                    engine.assigned_campus_courier = new_courier
                    engine.status = 'assigned'
                    engine.save(update_fields=['assigned_campus_courier', 'status'])

            # STEP 4: CUSTOM PAYOUT FOR NEW COURIER
            # We append '-C-{new_courier.id}' to bypass the old receipt block
            new_c_wallet = get_wallet(new_courier.user_account, Wallet.WalletType.COURIER_ADVANCE)
            
            for order in batch.campus_orders.exclude(status__in=['cancelled', 'pending_cancellation']):
                new_payout_ref = f"ORDER-ADV-{order.pk}-B-{batch.pk}-C-{new_courier.id}"
                
                if not WalletTransaction.objects.filter(reference=new_payout_ref).exists():
                    food_cost = Decimal(str(order.total_order_cost)) - Decimal(str(order.delivery_fee))
                    if food_cost > 0:
                        new_c_wallet.available_balance += food_cost
                        new_c_wallet.save(update_fields=['available_balance'])
                        
                        WalletTransaction.objects.create(
                            wallet=new_c_wallet, transaction_type='CREDIT', amount=food_cost,
                            running_balance=new_c_wallet.available_balance, reference=new_payout_ref,
                            description=f"Advance payout for Reassigned Order {order.order_number[-8:]}"
                        )

        return JsonResponse({'success': True, 'message': f'Batch reassigned to {new_courier.user_account.username}'})

    except Exception as e:
        print(f"Reassign Error: {e}")
        return JsonResponse({'error': 'Internal server error.'}, status=500)

# View to manually reassign single orders without going through the batch reassignment process.
@login_required(login_url='courierlogin')
@require_POST
def escrow_reassign_single_order_api(request):
    """
    Surgically reassigns a single University Order to a new courier or dump,
    managing volume, engine states, and escrow clawbacks/payouts atomically.
    """

    if not _is_escrow_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        target_id = data.get('target_id') # Can be a Courier ID or 'DUMP'

        with transaction.atomic():
            # 1. LOCK THE ORDER & ENGINE VIEW
            order = University_Order.objects.select_for_update().get(pk=order_id)
            engine_order = Campus_Engine_Order.objects.select_for_update().get(raw_order=order)
            
            # 2. TERMINAL STATUS CHECK
            terminal_statuses = ['delivered', 'completed', 'cancelled', 'refunded', 'pending_cancellation']
            if order.status in terminal_statuses:
                return JsonResponse({'error': f'Order is currently {order.status} and cannot be reassigned.'}, status=400)

            old_batch = order.batch
            old_courier = engine_order.assigned_campus_courier
            order_volume = order.total_physical_packs_db or 0

            # ---------------------------------------------------------
            # PHASE 1: EXTRACTION & CLAWBACK (FROM OLD COURIER)
            # ---------------------------------------------------------
            if old_courier and old_batch and old_batch.status in ['assigned', 'in_transit']:
                # The old courier was already paid. We must claw it back.
                from escrow.services import get_wallet
                old_c_wallet = get_wallet(old_courier.user_account, Wallet.WalletType.COURIER_ADVANCE)
                
                # Hunt down any previous payout for this order
                payout_receipt = WalletTransaction.objects.filter(
                    wallet=old_c_wallet, 
                    reference__startswith=f"ORDER-ADV-{order.pk}", 
                    transaction_type='CREDIT'
                ).first()

                if payout_receipt:
                    clawback_ref = f"SINGLE-REASSIGN-CLAWBACK-{order.pk}-FROM-{payout_receipt.id}"
                    if not WalletTransaction.objects.filter(reference=clawback_ref).exists():
                        clawback_amt = payout_receipt.amount
                        old_c_wallet.available_balance -= clawback_amt
                        old_c_wallet.save(update_fields=['available_balance'])

                        WalletTransaction.objects.create(
                            wallet=old_c_wallet, transaction_type='DEBIT', amount=-clawback_amt,
                            running_balance=old_c_wallet.available_balance, reference=clawback_ref,
                            description=f"Admin Order Reassignment Clawback: #{order.order_number}"
                        )

            # Detach from Old Batch and Recalculate Old Volume
            if old_batch:
                order.batch = None
                order.save(update_fields=['batch'])
                
                old_batch.total_volume = sum(o.total_physical_packs_db for o in old_batch.campus_orders.all()) or 0
                # If removing this order empties the batch, close it out
                if old_batch.total_volume == 0:
                    old_batch.status = 'completed'
                old_batch.save(update_fields=['total_volume', 'status'])

            # ---------------------------------------------------------
            # PHASE 2 & 3 & 4: INJECTION & PAYOUT
            # ---------------------------------------------------------
            if target_id == 'DUMP':
                # Route to appropriate gender dump
                customer_gender = engine_order.engine_payload.get('customer_data', {}).get('gender', 'male')
                dump_username = "Dumped_Campus_Female_Orders" if customer_gender.lower() == 'female' else "Dumped_Campus_Male_Orders"
                dump_courier = Courier.objects.get(user_account__username=dump_username)

                order.status = 'pending'
                order.save(update_fields=['status'])
                
                engine_order.status = 'dumped'
                engine_order.assigned_campus_courier = dump_courier
                engine_order.save(update_fields=['status', 'assigned_campus_courier'])

                old_courier.is_online = False # Force them offline to reset their engine state
                old_courier.save(update_fields=['is_online']) # Optional: You could even set them offline if you want to force a reset

                return JsonResponse({'success': True, 'message': 'Order successfully returned to the Dump.'})

            else:
                # Target is a Specific Courier
                new_courier = Courier.objects.get(id=target_id)
                
                # Check New Courier's Active Batch Space
                new_batch = DeliveryBatch.objects.select_for_update().filter(
                    courier=new_courier, status__in=['forming', 'assigned', 'in_transit']
                ).first()

                current_new_volume = new_batch.total_volume if new_batch else 0
                if (current_new_volume + order_volume) > 15:
                    # Rolling back transaction via exception
                    return JsonResponse({'error': f'Target courier only has space for {15 - current_new_volume} more courions. This order is {order_volume}.'}, status=400)

                if not new_batch:
                    payload = engine_order.engine_payload
                    delivery_point = payload.get('delivery_point', {})
                    new_batch = DeliveryBatch.objects.create(
                        courier=new_courier,
                        status="forming",
                        batch_id=f"BCH-CMP-{uuid.uuid4().hex[:8].upper()}",
                        bag_location_tag=delivery_point,
                        total_volume=0
                    )

                # Inject Order
                order.batch = new_batch
                if new_batch.status in ['forming', 'assigned']:
                    order.status = 'processing'
                    engine_order.status = 'assigned'
                elif new_batch.status == 'in_transit':
                    order.status = 'in_transit'
                    engine_order.status = 'shipped'
                
                order.save(update_fields=['batch', 'status'])
                
                engine_order.assigned_campus_courier = new_courier
                engine_order.save(update_fields=['status', 'assigned_campus_courier'])

                # Recalculate New Batch Volume
                new_batch.total_volume = sum(o.total_physical_packs_db for o in new_batch.campus_orders.all()) or 0
                new_batch.save(update_fields=['total_volume'])

                # ESCROW INJECTION (Only if new batch is already locked)
                if new_batch.status in ['assigned', 'in_transit']:
                    from escrow.services import get_wallet
                    new_c_wallet = get_wallet(new_courier.user_account, Wallet.WalletType.COURIER_ADVANCE)
                    
                    unique_tail = uuid.uuid4().hex[:6].upper()
                    new_payout_ref = f"ORDER-ADV-{order.pk}-B-{new_batch.pk}-C-{new_courier.id}-R-{unique_tail}"
                    
                    if not WalletTransaction.objects.filter(reference=new_payout_ref).exists():
                        food_cost = Decimal(str(order.total_order_cost)) - Decimal(str(order.delivery_fee))
                        if food_cost > 0:
                            new_c_wallet.available_balance += food_cost
                            new_c_wallet.save(update_fields=['available_balance'])
                            
                            WalletTransaction.objects.create(
                                wallet=new_c_wallet, transaction_type='CREDIT', amount=food_cost,
                                running_balance=new_c_wallet.available_balance, reference=new_payout_ref,
                                description=f"Reassignment Payout: Order {order.order_number[-8:]}"
                            )

                return JsonResponse({'success': True, 'message': f'Order reassigned to {new_courier.user_account.username}'})

    except Exception as e:
        print(f"Single Order Reassign Error: {e}")
        return JsonResponse({'error': 'Internal server error processing reassignment.'}, status=500)

# --- 7. THE ESCROW WALLET DIRECTORY & AGGREGATES ---
@login_required(login_url='courierlogin')
def escrow_wallet_directory_api(request):
    """Fetches the global list of wallets and calculates aggregates for the Directory Panel."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("<div class='alert error'>Unauthorized</div>", status=403)

    try:
        query = request.GET.get('q', '').strip()
        wallet_type = request.GET.get('wallet_type', 'all')
        
        wallets = Wallet.objects.select_related('user').order_by('-available_balance').exclude(wallet_type='ADMIN') # Admin wallet is excluded from the directory view
        
        if wallet_type != 'all':
            wallets = wallets.filter(wallet_type=wallet_type)
            
        if query:
            wallets = wallets.filter(
                Q(user__username__icontains=query) | 
                Q(user__email__icontains=query)
            )
        
        # Calculate aggregates for the summary cards
        from django.db.models import Sum
        aggregates = wallets.aggregate(
            total_available=Sum('available_balance'),
            total_locked=Sum('locked_escrow'),
            total_pending=Sum('pending_clearing')
        )
        
        # Limit to top 100 to prevent crashing the browser on massive databases
        wallets = wallets[:100]
        
        context = {
            'wallets': wallets,
            'aggregates': aggregates,
        }
        return render(request, 'dashboards/partials/wallet_directory_rows.html', context)
        
    except Exception as e:
        print(f"Directory Fetch Error: {e}")
        return HttpResponse(f"<tr><td colspan='7' style='text-align: center; color: #ef4444; padding: 20px;'><strong>Backend Error:</strong> {str(e)}</td></tr>")

from django.db.models.functions import TruncDate

# --- 8. THE PLATFORM EARNINGS & ADMIN WALLET FEED ---
@login_required(login_url='courierlogin')
def escrow_platform_earnings_api(request):
    """Fetches Admin wallet balances, applies filters, and returns chart data."""
    if not _is_escrow_admin(request.user):
        return HttpResponse("<div class='alert error'>Unauthorized</div>", status=403)

    try:
        admin_wallet = Wallet.objects.filter(wallet_type='ADMIN').first()
        
        if not admin_wallet:
            return HttpResponse("<tr><td colspan='5' style='text-align: center; padding: 40px; color: #ef4444;'>No ADMIN wallet exists in the database yet.</td></tr>")
            
        # --- 1. CAPTURE THE FILTERS ---
        time_filter = request.GET.get('time', 'all')
        source_filter = request.GET.get('source', 'all')
        
        transactions = WalletTransaction.objects.filter(wallet=admin_wallet)

        # --- 2. APPLY TIME FILTER ---
        today = timezone.localtime().date()
        if time_filter == 'today':
            transactions = transactions.filter(timestamp__date=today)
        elif time_filter == 'week':
            start_date = today - timedelta(days=7)
            transactions = transactions.filter(timestamp__date__gte=start_date)
        elif time_filter == 'month':
            start_date = today - timedelta(days=30)
            transactions = transactions.filter(timestamp__date__gte=start_date)

        # --- 3. APPLY SOURCE FILTER ---
        # Note: General withdrawal fees (FEE-wdr) will only show under "All Platforms"
        # unless they explicitly contain CRAVE or MAIN in the reference.
        if source_filter == 'crave':
            transactions = transactions.filter(reference__icontains='CRAVE')
        elif source_filter == 'main':
            transactions = transactions.filter(reference__icontains='MAIN')

        # --- 4. THE HEAVY LIFTING (Database Aggregation) ---
        # Group all POSITIVE earnings (credits) by day and sum them up.
        chart_qs = transactions.filter(amount__gt=0).annotate(
            date=TruncDate('timestamp')
        ).values('date').annotate(
            daily_total=Sum('amount')
        ).order_by('date')

        labels = []
        data_points = []
        period_total = Decimal('0.00')

        for entry in chart_qs:
            labels.append(entry['date'].strftime('%b %d')) # e.g., "Apr 13"
            data_points.append(float(entry['daily_total']))
            period_total += entry['daily_total']

        # --- 5. RENDER THE HTML TABLE ROWS ---
        table_transactions = transactions.order_by('-timestamp')[:100]
        context = {
            'admin_wallet': admin_wallet,
            'transactions': table_transactions
        }
        response = render(request, 'dashboards/partials/platform_earnings_rows.html', context)
        
        # --- 6. THE MAGIC TRICK (HTMX Trigger) ---
        # We attach the chart JSON to the response header. HTMX will catch this and trigger our Javascript!
        trigger_data = {
            "updateEarningsChart": {
                "labels": labels,
                "data": data_points,
                "total": float(period_total)
            }
        }
        response['HX-Trigger'] = json.dumps(trigger_data)
        
        return response
        
    except Exception as e:
        print(f"Platform Earnings Fetch Error: {e}")
        return HttpResponse(f"<tr><td colspan='5' style='text-align: center; color: #ef4444; padding: 20px;'><strong>Backend Error:</strong> {str(e)}</td></tr>")




# ------------------- 4. AJAX HANDLERS FOR BATCH & ORDER ACTIONS -------------------
@csrf_exempt
@login_required(login_url='courierlogin')
def courier_batch_action(request):
    try:
        data = json.loads(request.body)
        batch_id = data.get('batch_id')
        action = data.get('action')
        user_id = request.user.id
        courier_profile = request.user.courier_profile
        
        # Security: Ensure this batch belongs to the logged-in courier
        batch = get_object_or_404(DeliveryBatch, batch_id=batch_id, courier=courier_profile)

        if action == 'start_batch':
            # 1. Update Unified Batch Status
            batch.status = 'in_transit'
            batch.save()
            
            # 2. Trigger Network Providers (Modular Logic)
            StandardNetworkProvider.activate_transit(batch)
            CampusNetworkProvider.activate_transit(courier_profile)


            # --- 2.5 SLA SHIELD CLEANUP ---
            # If they were scouting, kill the shield now that they are moving.
            if courier_profile.is_scouting:
                courier_profile.is_scouting = False
                courier_profile.scouting_started_at = None
                courier_profile.save(update_fields=['is_scouting', 'scouting_started_at'])
                
            # 3. Response with HTMX Triggers
            response = JsonResponse({'success': True, 'message': 'Batch Started!'})
            
            triggers = {
                f"refreshNew_User{user_id}": "",
                f"refreshTransit_User{user_id}": ""
            }
            response['HX-Trigger'] = json.dumps(triggers)
            return response

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def courier_order_action_view(request, order_id):
    if request.method != 'POST':
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
        # .strip() removes any accidental hidden spaces sent by Javascript
        action = str(data.get('action', '')).strip()

        print(f"🎯 DEBUG: Action received from JS -> '{action}'")

        # STEP 1: RESOLVE
        link, network_type = NetworkOrderResolver.get_order_by_id(order_id)
        if not link:
            return JsonResponse({"error": "Order ID not found in any network"}, status=404)

        print(f"📦 DEBUG: Found object type: {type(link)} | Network: {network_type}")
        
        # STEP 2: DYNAMIC SOURCE DISCOVERY
        # FIX: For Campus, the link (University_Order) IS the source.
        # For Standard, we grab the .order_source property.
        source = link if network_type == 'campus' else getattr(link, 'order_source', None)
        
        if not source:
             return JsonResponse({"error": "Internal Mapping Error: No Source found"}, status=500)

        # --- DYNAMIC ACTION: RESTORE ORDER (The 3-Way Hierarchy) ---
        if action == "restore_order":
            print("🔄 DEBUG: Executing 3-Way Restore...")
            result = execute_order_restore(order_id, request.user.courier_profile)
            if result.get('status') == 'success':
                return JsonResponse(result)
            else:
                return JsonResponse(result, status=400)

        # --- DYNAMIC ACTION: CONFIRM RETURN TO HUB ---
        elif action == "confirm_return":
            print("🛑 DEBUG: Executing Confirm Return to Hub...")

            # The goal is to detach the cancelled order from the courier's bag 
            # so it disappears from their dashboard.

            if network_type == 'campus':
                # 1. Remove from the physical bag
                link.batch = None 
                link.save(update_fields=['batch'])

                # 2. Detach from the Engine View
                if hasattr(link, 'engine_view'):
                    link.engine_view.assigned_campus_courier = None
                    # 'dumped' or 'failed' are your valid engine choices for dead orders
                    link.engine_view.status = 'dumped' 
                    link.engine_view.save(update_fields=['assigned_campus_courier', 'status'])

            elif network_type == 'standard':
                # Standard orders track the courier directly on the model
                link.batch = None
                link.assigned_courier = None
                link.save(update_fields=['batch', 'assigned_courier'])

            return JsonResponse({"status": "success", "message": "Item successfully logged as returned. Bag cleared."})

        # --- DYNAMIC ACTION: MARK DELIVERED ---
        elif action == 'mark_delivered':
            can_use_seed = False
            if getattr(link, 'supports_proxy', False):
                can_use_seed = source.get_customer_interface.is_auth_ready

            return JsonResponse({
                "status": "requires_verification",
                "redirect_url": reverse('courier_verify_pin', args=[order_id]),
                "ui_config": {
                    "show_pin": True,
                    "show_seed_phrase": can_use_seed
                }
            })

        # --- DYNAMIC ACTION: REQUEST CANCELLATION ---
        elif action == 'request_cancellation':
            link.status = 'pending_cancellation'
            source.status = getattr(link, 'cancel_status_map', 'pending_cancellation')

            link.save()
            source.save()

            if hasattr(link, 'engine_view') and link.engine_view:
                link.engine_view.status = 'pending_cancellation'
                link.engine_view.save(update_fields=['status'])

            if hasattr(link, 'batch') and link.batch:
                link.batch.check_batch_burn()

            return JsonResponse({
                "status": "success",
                "message": "Manifest updated successfully.",
                "network_processed": network_type
            })

        # --- THE TRAP: UNKNOWN ACTION ---
        print(f"⚠️ DEBUG: Fell through to Unknown Action! The string was exactly: '{action}'")
        return JsonResponse({"error": f"Unknown Action: {action}"}, status=400)

    except Exception as e:
        print(f"🔥 DEBUG: Exception -> {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

    except Exception as e:
        print(f"🔥 DEBUG: Exception -> {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)    

def check_batch_burn(self):
    # Get all orders (Standard LUXAOrders or Campus Engine Orders)
    all_items = self.items.all() 
    
    # Define every way an order can be "finished"
    terminal_statuses = ['delivered', 'completed', 'pending_cancellation', 'cancelled']
    
    # Check if every item in the bag is done
    is_batch_done = all(item.status in terminal_statuses for item in all_items)

    if is_batch_done:
        # Close the batch
        self.status = 'completed'
        self.completed_at = timezone.now() # Use the imported utility
        self.save()

        # Update the courier's 'Resting' timer
        courier = self.courier
        courier.last_delivery_at = timezone.now()
        courier.save()
        
        # Trigger the creation of a new 'forming' batch 
        # to keep the Gate OPEN for future orders.
        self.create_next_forming_batch(courier)

# ------------------- 5. PIN FUNCTIONALITY FOR CUSTOMERS DELIVERY COMPLETION -------------------
def courier_verify_pin(request, order_id):
    """
    PLUG-AND-PLAY VIEW: 
    Works with any model added to the NetworkOrderResolver.
    """
    # 1. Fetch from resolver
    result = NetworkOrderResolver.get_order_by_id(order_id)
    
    # 2. DEFINE 'link' immediately by unpacking the result
    # If it's a tuple, take the first element. If not, take result itself.
    link = result[0] if isinstance(result, (tuple, list)) else result

    # 3. NOW you can safely check if it exists
    if not link:
        raise Http404("Order not found in any active network.")

    # 4. Get the source for data access
    source = getattr(link, 'source_order', link)

    # 3. Prevent re-verifying
    if source.status == 'delivered' or source.status == 'completed':
        messages.info(request, "This order has already been delivered.")
        return redirect('courier_dashboard')

    if request.method == 'POST':
        entered_code = request.POST.get('pin')
        
        # 4. MODULAR AUTHENTICATION
        # We ask the source's interface if it's ready for a Seed Phrase or a PIN
        interface = getattr(source, 'get_customer_interface', source)
        
        success = False
        if getattr(interface, 'is_auth_ready', False):
            # If the network supports Proxy/Seed Phrase (Campus Layer)
            profile = source.customer.crave_profile
            success = profile.default_proxy.check_seed_phrase(entered_code) | source.customer.check_delivery_pin(entered_code)
        else:
            # Standard PIN Verification (Main App Layer)
            success = source.customer.check_delivery_pin(entered_code)

        if success:
            # 5. UNIFIED COMPLETION
            source.status = 'delivered'
            source.save()
            
            # 6. AUTO-LINK SYNC (LUXA Side)
            # If this is a MasterOrder, sync the synchronized_order (LUXA)
            if hasattr(source, 'synchronized_order'):
                luxa = source.synchronized_order.first()
                if luxa:
                    luxa.status = 'completed'
                    luxa.save()
                    if getattr(luxa, 'batch', None):
                        luxa.batch.check_batch_burn()

            if hasattr(source, 'engine_view'):
                source.engine_view.status = 'completed'
                source.engine_view.save(update_fields=['status'])

            # 7. AUTO-LINK SYNC (Campus Side)
            # If the link itself has a batch (Campus_Engine_Order)
            if hasattr(link, 'batch') and link.batch:
                link.batch.check_batch_burn()

            return redirect('courier_dashboard')
        else:
            messages.error(request, "Incorrect Verification Code.")

    return render(request, 'couriers/courier_verify_pin.html', {
        'order': source,
        'link': link,
        'is_proxy_ready': getattr(source, 'is_auth_ready', False)
    })

# ------------------- 6. DASHBOARD FOR UPDATINGG SECTION PRODUCTS -------------------
@login_required(login_url='courierlogin')
def campus_availability_manager(request):
    courier = getattr(request.user, 'courier_profile', None)
    
    # 1. Security Gate
    if not courier or courier.courier_category in ["SAME_DAY", "STANDARD"]:
        messages.error(request, "Access Denied.")
        return redirect('courier_dashboard')

    # 2. DEFINE THE SCOPE
    if courier.courier_category == 'EXTERNAL_UPDATER':
        if not courier.interceptor_outlet:
            messages.error(request, "No outlet assigned to your profile. Please contact admin.")
            return redirect('courier_dashboard')
            
        allowed_outlets = University_Outlet.objects.filter(id=courier.interceptor_outlet.id)
        allowed_products = Section_Product.objects.filter(section__outlet=courier.interceptor_outlet)
        can_manage_packs = False
    else:
        # Standard Campus Admins see everything
        allowed_outlets = University_Outlet.objects.all()
        allowed_products = Section_Product.objects.all()
        can_manage_packs = True

    # 3. BULK SAVE LOGIC
    if request.method == "POST":
        
        # --- FIX #1: ANTI-SWEEP SHIELD ---
        # By submitting this form, they are actively working. We explicitly 
        # set them online and bump their last_active timestamp so the 
        # background check_courier_state sweep doesn't accidentally turn them offline.
        if courier:
            courier.is_online = True
            courier.last_active = timezone.now()
            courier.save(update_fields=['is_online', 'last_active'])

        with transaction.atomic():
            
            # --- A. UPDATE PACKS ---
            if can_manage_packs:
                for pack in Pack_Size_Config.objects.all():
                    key = f'pack_{pack.id}'
                    # FIX BUG #2: If the key is missing from POST, it was UNCHECKED (False)
                    is_active = key in request.POST
                    if pack.availability != is_active:
                        pack.availability = is_active
                        pack.save(update_fields=['availability'])
            
            # --- B. OUTLETS ARE SAFE ---
            # We completely skip updating outlets here because you removed the 
            # outlet toggles from the UI. This prevents them from ever shutting down.
            
            # --- C. UPDATE PRODUCTS ---
            for product in allowed_products:
                key = f'product_{product.id}'
                # FIX BUG #2: If the key is missing from POST, it was UNCHECKED (False)
                is_active = key in request.POST
                if product.availability_status != is_active:
                    product.availability_status = is_active
                    product.save(update_fields=['availability_status'])
        
        messages.success(request, "Availability updated successfully!")
        if courier.courier_category == 'EXTERNAL_UPDATER':
            return redirect('campus_availability_manager')
        else:
            return redirect('courier_dashboard')

    # 4. RENDER DATA
    outlets_to_render = allowed_outlets.prefetch_related(
        'sections',
        'sections__products'
    ).order_by('name')

    context = {
        'courier': courier,
        'outlets': outlets_to_render,
        'pack_sizes': Pack_Size_Config.objects.all() if can_manage_packs else [],
    }
    return render(request, 'couriers/campus_availability.html', context)

# @csrf_exempt
# @login_required(login_url='courierlogin')
# def claim_scavenger_order_view(request):
#     if request.method == "POST":
#         import json
#         from decision_engine.special_campus_routing.scavenger_routing import execute_scavenger_claim
#         try:
#             data = json.loads(request.body)
#             order_id = data.get('engine_order_id')
#             courier_username = request.user.username
            
#             result = execute_scavenger_claim(order_id, courier_username)
#             if result['status'] == 'success':
#                 return JsonResponse({'success': True, 'message': result['message']})
#             else:
#                 return JsonResponse({'success': False, 'error': result['message']}, status=400)
#         except Exception as e:
#             return JsonResponse({'success': False, 'error': str(e)}, status=500)

def check_courier_state(request):
    import datetime
    from django.utils import timezone
    
    # --- 1. THE AUTO-SWEEP (Fixes the 10-minute ghost online issue) ---
    cutoff_time = timezone.now() - datetime.timedelta(minutes=360)
    
    # THE FIX: Find all couriers who are currently busy with active batches
    busy_courier_ids = DeliveryBatch.objects.filter(
        status__in=['forming', 'assigned', 'in_transit']
    ).values_list('courier_id', flat=True)

    # Exclude the busy couriers from the sweep!
    stale_couriers = Courier.objects.filter(
        is_online=True, 
        last_active__lt=cutoff_time
    ).exclude(id__in=busy_courier_ids, user_account__username="favour_") # The favour_ account is our eternal sunshine of the spotless online
    
    if stale_couriers.exists():
        stale_couriers.update(is_online=False)
        # Ensure their engine routing is also turned off
        CourierEngine.objects.filter(courier__in=stale_couriers).update(status='offline')

    # --- 2. THE SESSION EXPIRY CATCHER ---
    # If the auto-logout hit THIS specific user, their session is gone.
    if not request.user.is_authenticated or not hasattr(request.user, 'courier_profile'):
        # Send HTMX a special header to force the browser to redirect to the login page
        response = HttpResponse()
        response['HX-Redirect'] = reverse('courierlogin')
        return response

    # --- 3. NORMAL HEARTBEAT & POLLING LOGIC ---
    courier = request.user.courier_profile

    # Update their 'last seen' time instantly without triggering a heavy save()
    Courier.objects.filter(id=courier.id).update(last_active=timezone.now())

    forming_count = DeliveryBatch.objects.filter(courier=courier, status='forming').count()
    assigned_count = DeliveryBatch.objects.filter(courier=courier, status='assigned').count()

    # --- NEW: SCAVENGER DISCOVERY LOGIC ---
    scavenger_count = 0
    active_batch = DeliveryBatch.objects.filter(courier=courier, status__in=['assigned', 'in_transit']).first()
    
    if active_batch:
        current_volume = active_batch.total_volume or 0
        available_space = 15 - current_volume # Extended 15-courion limit
        
        if available_space > 0:
            dump_username = "Dumped_Campus_Female_Orders" if courier.gender.lower() == 'female' else "Dumped_Campus_Male_Orders"
            
            # Find dumped orders matching gender where volume <= available_space
            scavenger_count = Campus_Engine_Order.objects.filter(
                status='dumped',
                assigned_campus_courier__user_account__username=dump_username,
                raw_order__total_physical_packs_db__lte=available_space
            ).count()
    
    # Create the 3-part state hash
    current_state = f"{forming_count}-{assigned_count}-{scavenger_count}"
    last_state = request.session.get('courier_state_hash')
    
    # If the hash changed (e.g., a new dumped order fits their bag!), trigger reload
    if last_state is not None and last_state != current_state:
        request.session['courier_state_hash'] = current_state
        response = HttpResponse()
        response['HX-Location'] = reverse('courier_dashboard') + "#new"
        return response
    
    request.session['courier_state_hash'] = current_state
    return HttpResponse()

    