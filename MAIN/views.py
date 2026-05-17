import json

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q, Max
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib import messages
from django.conf import settings
from decimal import Decimal
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
import logging
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

from MAIN.utils import manage_draft_stock
from escrow.models import Wallet
from .models import (
    Product, Vendor, Category, Customer, Order, OrderItem,
    Cart, CartItem, Wishlist, WishlistItem, Notification, ProductVariant,
    LUXAOrder, DraftOrder, DraftOrderItem, EligibilityStagingArea, MasterOrder, 
    KYCVerification
)
from .constants import DEFAULT_CURRENCY_CODE, DEFAULT_CURRENCY_SYMBOL
from .forms import CustomerProfileForm, ProductListingForm, ProductImageForm, KYCSubmissionForm
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from escrow.services import calculate_and_apply_order_fees, step_2_start_delivery, step_3_complete_delivery, lock_master_order_funds
from escrow.fee_calculator import BASE_DELIVERY_FEE
import uuid

# Create your views here.

def get_or_create_customer_profile(user):
    """Helper function to get or create a customer profile for a user.
    
    Args:
        user: The User instance to create/get customer profile for.
    
    Returns:
        Customer: The customer profile instance.
    """
    customer, created = Customer.objects.get_or_create(
        user_account=user,
        defaults={
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'username': user.username,
            'email': user.email or '',
        }
    )
    return customer

# json converter for cms product structure
def get_product_structure_for_json(product):
    """
    Adapter: Converts Main App's 'ProductVariant' models into 
    the simple dictionary format required by the Draft/Courier frontend.
    """
    grouped_variants = {}
    
    # 1. Group variants by type (e.g., "Handle", "Body")
    # This matches the logic you already use in 'product_detail'
    for v in product.variants.filter(is_available=True):
        if v.variant_type not in grouped_variants:
            grouped_variants[v.variant_type] = []
        
        grouped_variants[v.variant_type].append(v.variant_value)

    # 2. Format for the frontend template
    # Output: [{'name': 'Handle', 'values': ['Red', 'Blue']}, ...]
    attributes_list = []
    for type_name, values in grouped_variants.items():
        attributes_list.append({
            'name': type_name,
            'values': list(set(values)) # remove duplicates
        })
            
    return attributes_list

# TEMPORARY VIEW FOR COUNTDOWN PAGE
def crave_countdown(request):
    """Renders the hype/advertisement page for the upcoming Crave launch."""
    return render(request, 'MAIN/crave_countdown.html') # Adjust the path if it's inside a subfolder like 'luxa_crave/crave_countdown.html'

def index(request):
    # Fetch featured products and vendors
    # We add .order_by('?') before slicing [:20]
    category_slug = request.GET.get('category')  # get from URL

    product_count = Product.objects.all().count
    vendor_count = Vendor.objects.filter(is_active=True).count
    featured_products = Product.objects.filter(
        is_featured=True,
        is_available=True
    )
    if category_slug and category_slug != "all":
        featured_products = featured_products.filter(
            category__slug=category_slug
        )
    # randomize + limit
    featured_products = Product.objects.filter(is_featured=True).order_by('?')[:8]
    hero_products = Product.objects.filter(
    is_featured=True
    ).order_by("?")[:6]
    featured_vendors = Vendor.objects.filter(is_active=True,
    is_verified=True).annotate(product_count=Count("products"))
    categories = Category.objects.filter(is_active=True, parent__isnull=True)
    
    context = {
        'featured_products': featured_products,
        'featured_vendors': featured_vendors,
        "hero_products": hero_products,
        'categories': categories,
        "product_count": product_count,
        "vendor_count": vendor_count,
        'currency_symbol': DEFAULT_CURRENCY_SYMBOL,
    }
    return render(request, "MAIN/index.html", context)

def productpage(request):
    return render(request, "MAIN/product_view.html")

def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related('vendor', 'category').prefetch_related(
            'images', 'variants', 'variant_images__variant'
        ),
        slug=slug,
        is_active=True,
        is_available=True
    )
    categories = Category.objects.filter(is_active=True, parent__isnull=True)

    # Currency setup
    if product.vendor:
        currency_info = product.vendor.get_currency_display_info()
        currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    else:
        currency_symbol = DEFAULT_CURRENCY_SYMBOL
    
    # Related products
    related_products = Product.objects.filter(
        category=product.category,
        is_active=True,
        is_available=True
    ).exclude(id=product.id).select_related('vendor', 'category')[:4]
    
    # --- NEW LOGIC: Group Variants by Type ---
    # Output structure: {'Handle': [v1, v2], 'Body': [v3, v4]}
    grouped_variants = {}
    if product.has_variants:
        for variant in product.variants.filter(is_available=True):
            v_type = variant.variant_type  # e.g. "Handle"
            if v_type not in grouped_variants:
                grouped_variants[v_type] = []
            grouped_variants[v_type].append(variant)

    # --- NEW LOGIC: JSON for Image Switching ---
    import json
    variant_images_dict = {}
    for variant_image in product.variant_images.all():
        # Key format: "Type_Value" (e.g., "Handle_Red")
        variant_key = f"{variant_image.variant.variant_type}_{variant_image.variant.variant_value}"
        all_images = variant_image.get_all_images()
        variant_images_dict[variant_key] = {
            'main_image': variant_image.main_image.url if variant_image.main_image else None,
            'thumbnails': [img.url for img in all_images if img]
        }

    in_wishlist = False
    if request.user.is_authenticated:
        try:
            customer = request.user.customer_profile # or get_or_create_customer_profile(request.user)
            # Efficient query to check existence
            in_wishlist = WishlistItem.objects.filter(
                wishlist__customer=customer, 
                product=product
            ).exists()
        except:
            pass
    
    context = {
        'product': product,
        'categories': categories,
        'currency_symbol': currency_symbol,
        'in_wishlist': in_wishlist,
        'related_products': related_products,
        'grouped_variants': grouped_variants, # <--- Pass the grouped dict
        'variant_images_json': json.dumps(variant_images_dict),
    }
    return render(request, "MAIN/product_view.html", context)

def base(request):
    return render(request, "MAIN/base.html")

def categories(request):
    all_categories = Category.objects.filter(is_active=True, parent__isnull=True)
    context = {
        'categories': all_categories,
    }
    return render(request, "MAIN/categoryview.html", context)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)

    # Get direct subcategories
    subcategories = category.subcategories.filter(is_active=True)

    products = None
    if not subcategories.exists():
        # Only fetch products if this is a LEAF category
        products = Product.objects.filter(
            category=category,
            is_active=True,
            is_available=True
        )

    context = {
        'category': category,
        'subcategories': subcategories,
        'products': products,
    }
    return render(request, 'MAIN/categoryview.html', context)

def vendor_detail(request, vendor_id):
    vendor = get_object_or_404(Vendor, id=vendor_id, is_active=True)
    products = Product.objects.filter(vendor=vendor, is_active=True, is_available=True)
    # Get currency symbol from vendor
    currency_info = vendor.get_currency_display_info()
    currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    context = {
        'vendor': vendor,
        'products': products,
        'currency_symbol': currency_symbol,
    }
    return render(request, "MAIN/vendorpublic.html", context)


@login_required(login_url='/login/')
def editprofile(request):
    # Get or create customer profile
    customer = get_or_create_customer_profile(request.user)
    
    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, request.FILES, instance=customer, user=request.user)
        if form.is_valid():
            try:
                form.save()
                return redirect('customerpage')
            except ValidationError as e:
                # Handle ValidationError from form.save() (fallback for race conditions)
                # Model-level validation is handled in form.clean(), but race conditions
                # can still occur between validation and save()
                # Add errors to form so they can be displayed to user
                if hasattr(e, 'error_dict') and e.error_dict:
                    # ValidationError raised with a dictionary of field errors
                    for field, error_list in e.error_dict.items():
                        for error in error_list:
                            if field and field != '__all__':
                                form.add_error(field, error)
                            else:
                                # Handle __all__ or None as non-field errors
                                form.add_error(None, error)
                elif hasattr(e, 'messages') and e.messages:
                    # ValidationError raised with a list of messages
                    for message in e.messages:
                        form.add_error(None, message)
                else:
                    # Fallback: add as non-field error
                    form.add_error(None, str(e))
    else:
        form = CustomerProfileForm(instance=customer, user=request.user)
    
    context = {
        'form': form,
        'customer': customer,
    }
    return render(request, "MAIN/editprofile.html", context)

# KYC form view
@login_required(login_url='/login/')
def submit_kyc(request):
    # 1. Check if they already have a submission
    try:
        kyc = request.user.customer_profile.kyc_profile
        if kyc.status == 'APPROVED':
            messages.info(request, "You are already verified!")
            return redirect('customerpage') # or customer dashboard
        elif kyc.status == 'PENDING':
            messages.info(request, "Your KYC is currently under review.")
            return redirect('customerpage')
    except KYCVerification.DoesNotExist:
        kyc = None

    if request.method == 'POST':
        form = KYCSubmissionForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.customer = request.user.customer_profile
            submission.status = 'PENDING' # Reset status if they are re-submitting after rejection
            submission.save()
            messages.success(request, "KYC Submitted successfully! We will review it shortly.")
            return redirect('customerpage')
    else:
        form = KYCSubmissionForm(instance=kyc)

    return render(request, 'MAIN/submit_kyc.html', {'form': form, 'kyc': kyc})

def kyc_info(request):
    return render(request, "MAIN/kyc_info.html")

@login_required(login_url='/login/')
def vendash(request):
    """Vendor dashboard view that INCLUDES customer context for template inheritance"""
    
    # 1. Vendor Authentication & Status Check
    try:
        vendor = request.user.vendor_profile
        if not vendor.is_active:
            messages.warning(request, "Your account is still under review.")
            return redirect('/customerpage/')
    except AttributeError:
        return redirect('/customerpage/')
    
    # 2. WELCOME MESSAGE LOGIC
    show_welcome = False
    if hasattr(vendor, 'has_seen_welcome') and not vendor.has_seen_welcome:
        show_welcome = True
        vendor.has_seen_welcome = True
        vendor.save(update_fields=['has_seen_welcome'])

    # --- VENDOR DATA (Sales & Earnings) ---
    vendor_orders = Order.objects.filter(vendor=vendor).select_related('customer').prefetch_related('items__product')
    
    orders_vend = vendor_orders.order_by('-created_at')[:4]
    
    # 1. TOTAL EARNINGS (All 'Paid' orders)    
    if hasattr(request.user, 'vendor_profile'):
        wallet_type = Wallet.WalletType.VENDOR
    else:
        wallet_type = Wallet.WalletType.CUSTOMER

    wallet = Wallet.objects.get(user=request.user, wallet_type=wallet_type)

    total_balance = int(wallet.available_balance) + int(wallet.pending_clearing)
    
    # Get vendor's products
    vendor_products = Product.objects.filter(vendor=vendor).select_related('category')[:10]
    
    # Calculate vendor tier
    total_sales = vendor_orders.filter(payment_status='paid').count()
    if total_sales >= 1000:
        tier = "Platinum Tier"
    elif total_sales >= 500:
        tier = "Gold Tier"
    elif total_sales >= 100:
        tier = "Silver Tier"
    else:
        tier = "Bronze Tier"
    
    currency_info = vendor.get_currency_display_info()
    currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    current_hour = timezone.now().hour
    greeting = "Good morning" if current_hour < 12 else "Good afternoon" if current_hour < 17 else "Good evening"

    # --- CUSTOMER DATA ---
    customer = get_or_create_customer_profile(request.user)
    customer_orders = Order.objects.filter(customer=customer).order_by('-created_at')
    total_orders = customer_orders.count()
    recent_orders = customer_orders.order_by('-created_at')[:10]
    pending_deliveries = customer_orders.exclude(status__in=['delivered', 'cancelled', 'refunded']).count()
    ongoing_orders = customer_orders.exclude(status__in=['delivered', 'cancelled', 'refunded'])[:5]
    wishlist_obj, _ = Wishlist.objects.get_or_create(customer=customer)
    wishlist_count = wishlist_obj.total_items

    all_addresses = customer.get_all_addresses()

    # --- CALCULATE PROFILE COMPLETION PERCENTAGE ---
    completion_percentage = 0
    
    # Define the weights for each field (Total = 100%)
    if customer.first_name or request.user.first_name:
        completion_percentage += 15
    if customer.last_name or request.user.last_name:
        completion_percentage += 15
    if customer.phone_number:
        completion_percentage += 15
    if getattr(customer, 'gender', None): # Safely check gender
        completion_percentage += 15
    if customer.profile_picture:
        completion_percentage += 10
    if getattr(customer, 'delivery_pin', None):
        completion_percentage += 15
    if all_addresses: # If they have at least one address
        completion_percentage += 15

    # NEW: The target stock number to calculate the visual bar width
    max_stock_target = 15
    
    context = {
        'vendor': vendor,
        'show_welcome': show_welcome,
        'greeting': greeting,
        'tier': tier,
        'wallet': wallet,
        'total_balance': total_balance,
        'orders_vend': orders_vend,
        'vendor_products': vendor_products,
        'currency_symbol': currency_symbol,
        'total_orders': total_orders,
        'customer': customer,
        'recent_orders': recent_orders,
        'pending_deliveries': pending_deliveries,
        'ongoing_orders': ongoing_orders,
        'wishlist_count': wishlist_count,
        'all_addresses': all_addresses,
        'profile_completion_percentage': completion_percentage,
        'max_stock_target': max_stock_target,
    }
    return render(request, "MAIN/vendordashboard.html", context)

@login_required(login_url='/login/')
def cart(request):    
    customer = get_or_create_customer_profile(request.user)
    
    # Get or create cart
    cart_obj, created = Cart.objects.get_or_create(customer=customer)
    
    # Get cart items with product details AND prefetch the variants
    cart_items = CartItem.objects.filter(cart=cart_obj).select_related(
        'product', 'product__vendor'
    ).prefetch_related('variants')
    
    # Calculate subtotal
    subtotal = Decimal('0.00')
    # Count unique vendors for delivery fee
    unique_vendors = set()
    
    for item in cart_items:
        subtotal += item.subtotal
        if item.product.vendor:
            unique_vendors.add(item.product.vendor.id)
            
    # --- UPDATED SHIPPING LOGIC ---
    vendor_count = len(unique_vendors)
    DELIVERY_FEE_PER_VENDOR = Decimal('250.00')
    
    # If no vendors (empty cart), fee is 0. Otherwise: Vendors * 250
    shipping_estimate = DELIVERY_FEE_PER_VENDOR
    
    # Calculate total
    total = subtotal + shipping_estimate
    
    currency_symbol = DEFAULT_CURRENCY_SYMBOL
    if cart_items.exists():
        first_product = cart_items.first().product
        if first_product.vendor:
            currency_info = first_product.vendor.get_currency_display_info()
            currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    context = {
        'cart': cart_obj,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'shipping_estimate': shipping_estimate, # This now reflects the vendor count calculation
        'total': total,
        'currency_symbol': currency_symbol,
    }
    return render(request, "MAIN/cart.html", context)

def vendrev(request):
    return render(request, "MAIN/vendor-review.html")

def explore_3d_products(request):
    category_slug = request.GET.get("category")

    products = Product.objects.filter(
        model_3d_file__isnull=False,
        is_active=True,
        is_available=True
    )

    if category_slug:
        products = products.filter(category__slug=category_slug)

    categories = Category.objects.filter(
        products__model_3d_file__isnull=False
    ).distinct()

    return render(request, "MAIN/explore_3d_products.html", {
        "products": products,
        "categories": categories,
        "active_category": category_slug,
    })

def filter_3d_products(request):
    category_id = request.GET.get("category")
    products = Product.objects.filter(
        model_3d_file__isnull=False,
        is_active=True,
        is_available=True,
        category_id=category_id
    )
    # Return JSON
    return JsonResponse({
        "products": [{"name": p.name, "slug": p.slug, "image": p.main_image.url} for p in products]
    })

def product3d(request, slug=None):
    """3D product view page"""
    if slug:
        product = get_object_or_404(
            Product.objects.select_related('vendor', 'category').prefetch_related('images'),
            slug=slug,
            is_active=True,
            is_available=True
        )
        # Get currency symbol
        if product.vendor:
            currency_info = product.vendor.get_currency_display_info()
            currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
        else:
            currency_symbol = DEFAULT_CURRENCY_SYMBOL
        
        # Fetch all textures for this product
        textures = product.textures_3d.all()

        # Get related products (same category, excluding current product)
        related_products = Product.objects.filter(
            category=product.category,
            is_active=True,
            is_available=True
        ).exclude(id=product.id).select_related('vendor', 'category')[:4]
        
        # Get "Perfect Partner" products (can be featured products or same category)
        perfect_partner_products = Product.objects.filter(
            is_featured=True,
            is_active=True,
            is_available=True
        ).exclude(id=product.id).select_related('vendor', 'category')[:4]
        
        # Get "Keep Exploring" products (can be different category or featured)
        keep_exploring_products = Product.objects.filter(
            is_active=True,
            is_available=True
        ).exclude(id=product.id).exclude(
            id__in=[p.id for p in perfect_partner_products]
        ).select_related('vendor', 'category')[:4]
        
        context = {
            'product': product,
            'currency_symbol': currency_symbol,
            'related_products': related_products,
            'perfect_partner_products': perfect_partner_products,
            'keep_exploring_products': keep_exploring_products,
            'textures': textures,
        }
    else:
        # Fallback if no product specified (show placeholder)
        context = {
            'product': None,
            'currency_symbol': DEFAULT_CURRENCY_SYMBOL,
            'related_products': [],
            'perfect_partner_products': [],
            'keep_exploring_products': [],
        }
    
    return render(request, "MAIN/3dproduct.html", context)

@login_required(login_url='/login/')
def add_product(request, vendor_id):
    vendor = get_object_or_404(Vendor, id=vendor_id, is_active=True)
    
    # Get currency symbol
    if vendor:
        currency_info = vendor.get_currency_display_info()
        currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    else:
        currency_symbol = DEFAULT_CURRENCY_SYMBOL

    if request.method == 'POST':
        product_form = ProductListingForm(request.POST, request.FILES, vendor=vendor)
        image_form = ProductImageForm(request.POST, request.FILES)
        
        if product_form.is_valid() and image_form.is_valid():
            # 1. Save the Product
            product = product_form.save(commit=False)
            product.vendor = vendor
            product.save()
            
            # 2. Save the Images
            product_image = image_form.save(commit=False)
            product_image.product = product
            product_image.save()
            
            # SUCCESS: Tell the AJAX request to redirect
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'redirect_url': '/vendash/'})
            return redirect('vendash')
            
        else:
            # FAILED: Collect all errors from both forms and send them back as JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                errors = dict(product_form.errors)
                errors.update(dict(image_form.errors))
                return JsonResponse({'success': False, 'errors': errors})

    else:
        product_form = ProductListingForm(vendor=vendor)
        image_form = ProductImageForm()

    context = {
        'product_form': product_form,
        'formset': image_form,
        'currency_symbol': currency_symbol,
    }
    
    return render(request, 'MAIN/product-listing.html', context)

@login_required(login_url='/login/')
def edit_product(request, product_id=None):
    """Edit product for vendors"""
    # Ensure user is a vendor
    if not hasattr(request.user, 'vendor_profile'):
        return redirect('/customerpage/')
    
    vendor = request.user.vendor_profile
    
    if product_id:
        product = get_object_or_404(Product, id=product_id, vendor=vendor)
    else:
        # If no product_id, redirect to manage products
        return redirect('manage_product')
    
    if request.method == 'POST':
        form = ProductListingForm(request.POST, request.FILES, instance=product, vendor=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully!')
            return redirect('manage_product')
    else:
        form = ProductListingForm(instance=product, vendor=vendor)
    
    # Get currency symbol
    currency_info = vendor.get_currency_display_info()
    currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    context = {
        'form': form,
        'product': product,
        'currency_symbol': currency_symbol,
    }
    return render(request, "MAIN/productedit.html", context)

@login_required(login_url='/login/')
def manage_product(request):
    """Manage products for vendors"""
    if not hasattr(request.user, 'vendor_profile'):
        return redirect('/customerpage/')
    
    vendor = request.user.vendor_profile
    all_products = Product.objects.filter(vendor=vendor).select_related('category').order_by('-created_at')
    
    # 1. Calculate Stats (Always based on the FULL list, regardless of search)
    total_products = all_products.count()
    live_count = all_products.filter(is_active=True).count()
    suspended_count = all_products.filter(is_active=False).count()
    last_updated = all_products.aggregate(Max('created_at'))['created_at__max']

    # 2. Get Search & Filter Parameters
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')

    # 3. Apply Filters
    if search_query:
        all_products = all_products.filter(name__icontains=search_query)
    
    if status_filter == 'live':
        all_products = all_products.filter(is_active=True)
    elif status_filter == 'suspended':
        all_products = all_products.filter(is_active=False)
    
    # 4. Pagination (5 items per page)
    paginator = Paginator(all_products, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    currency_info = vendor.get_currency_display_info()
    currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    context = {
        'page_obj': page_obj,
        'total_products': total_products,
        'live_count': live_count,
        'suspended_count': suspended_count,
        'last_updated': last_updated,
        'currency_symbol': currency_symbol,
        'max_stock_target': 15,
        'vendor': vendor,
        # Pass the parameters back to the template so the inputs retain their values
        'search_query': search_query,  
        'status_filter': status_filter,
    }
    return render(request, "MAIN/productmanage.html", context)

@login_required(login_url='/login/')
def inbox(request):
    """View notifications for customer or vendor"""
    
    if hasattr(request.user, 'vendor_profile'):
        profile_kwargs = {'vendor': request.user.vendor_profile}
    else:
        profile_kwargs = {'customer': get_or_create_customer_profile(request.user)}
        
    # 1. DATABASE-LEVEL FILTER: Exclude notifications where the order foreign key is explicitly null
    valid_notifications = Notification.objects.filter(**profile_kwargs).exclude(
        Q(notification_type='order') & Q(order__isnull=True)
    ).order_by('-created_at')

    base_unread = valid_notifications.filter(is_read=False)
    base_read = valid_notifications.filter(is_read=True)[:50]
    
    # 2. PYTHON-LEVEL SAFEGUARD: Catch "Ghost" orders where the ID exists but the object was deleted
    clean_unread = []
    for n in base_unread:
        if n.notification_type == 'order':
            try:
                # Force Django to check if the related object actually exists
                if not n.order: 
                    continue
            except ObjectDoesNotExist:
                # If the order was hard-deleted from the DB, skip this notification
                continue
        clean_unread.append(n)
        
    clean_read = []
    for n in base_read:
        if n.notification_type == 'order':
            try:
                if not n.order:
                    continue
            except ObjectDoesNotExist:
                continue
        clean_read.append(n)

    context = {
        'unread_notifications': clean_unread,
        'read_notifications': clean_read,
        'unread_count': len(clean_unread),
        'read_count': len(clean_read),
    }
    return render(request, "MAIN/notification.html", context)

@login_required(login_url='/login/')
def customerpage(request):
    # Redirect vendors to vendor dashboard instead of customer page
    if hasattr(request.user, 'vendor_profile'):
        vendor_profile = request.user.vendor_profile
        
        # If they are already an ACTIVE vendor, send them to the vendor dashboard
        if vendor_profile.is_active:
            return redirect('/vendash/')
    
    # Get or create customer profile
    customer = get_or_create_customer_profile(request.user)
    
    # 1. Fetch Master Orders (Not Sub-Orders)
    all_masters = MasterOrder.objects.filter(customer=customer).prefetch_related('sub_orders').order_by('-created_at')
    
    # 2. Calculate Stats
    total_orders = all_masters.count()
    pending_deliveries = all_masters.exclude(status__in=['delivered', 'cancelled', 'refunded']).count()
    
    # 3. Categorize for the Tabs
    ongoing_orders = all_masters.exclude(status__in=['delivered', 'cancelled', 'refunded'])
    completed_orders = all_masters.filter(status='delivered')
    cancelled_orders = all_masters.filter(status__in=['cancelled', 'refunded'])
    
    # 4. Recent Orders (Top 5)
    recent_orders = all_masters[:3]
    
    # Get recommended products (featured products, excluding those customer already ordered)
    ordered_product_ids = OrderItem.objects.filter(order__customer=customer).values_list('product_id', flat=True)
    recommended_products = Product.objects.filter(
        is_featured=True,
        is_active=True,
        is_available=True
    ).exclude(id__in=ordered_product_ids).select_related('vendor', 'category')[:3]
    
    # Get wishlist count and items
    wishlist_count = 0
    wishlist_items = []
    wishlist_obj, created = Wishlist.objects.get_or_create(customer=customer)
    wishlist_count = wishlist_obj.total_items
    wishlist_items = WishlistItem.objects.filter(wishlist=wishlist_obj).select_related('product', 'product__vendor')[:10]  # Limit to 10 for display
    
    # Get currency symbol for orders (use first order's vendor currency if available)
    currency_symbol = DEFAULT_CURRENCY_SYMBOL
    if all_masters.exists():
        first_order = all_masters[0]
        if first_order.sub_orders.exists():
            first_sub_order = first_order.sub_orders.first()
            if first_sub_order.vendor:
                currency_info = first_sub_order.vendor.get_currency_display_info()
                currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    # Get currency symbol for wishlist items
    wishlist_currency_symbol = DEFAULT_CURRENCY_SYMBOL
    if wishlist_items:
        first_product = wishlist_items[0].product
        if first_product.vendor:
            currency_info = first_product.vendor.get_currency_display_info()
            wishlist_currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL

    all_addresses = customer.get_all_addresses()

    # --- CALCULATE PROFILE COMPLETION PERCENTAGE ---
    completion_percentage = 0
    
    # Define the weights for each field (Total = 100%)
    if customer.first_name or request.user.first_name:
        completion_percentage += 15
    if customer.last_name or request.user.last_name:
        completion_percentage += 15
    if customer.phone_number:
        completion_percentage += 15
    if getattr(customer, 'gender', None): # Safely check gender
        completion_percentage += 15
    if customer.profile_picture:
        completion_percentage += 10
    if getattr(customer, 'delivery_pin', None):
        completion_percentage += 15
    if all_addresses: # If they have at least one address
        completion_percentage += 15
    
    context = {
        'customer': customer,
        'currency_symbol': currency_symbol,
        'total_orders': total_orders,
        'pending_deliveries': pending_deliveries,
        'ongoing_orders': ongoing_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'recent_orders': recent_orders,
        'recommended_products': recommended_products,
        'wishlist_count': wishlist_count,
        'wishlist_items': wishlist_items,
        'wishlist_currency_symbol': wishlist_currency_symbol,
        'all_addresses': all_addresses,
        'profile_completion_percentage': completion_percentage,
    }
    return render(request, "MAIN/customer.html", context)

# Address Management API Endpoint (Add/Edit)
@login_required(login_url='/login/')
@require_POST
def manage_address(request):
    """API endpoint to Add or Edit customer addresses"""
    customer = request.user.customer_profile
    try:
        data = json.loads(request.body)
        addr_id = data.get('address_id')
        
        address_data = {
            'address_line1': data.get('address_line1', ''),
            'address_line2': data.get('address_line2', ''),
            'city': data.get('city', ''),
            'state': data.get('state', ''),
            'country': data.get('country', 'Nigeria'),
            'label': data.get('label', ''),
        }

        if addr_id == 'primary':
            customer.address_line1 = address_data['address_line1']
            customer.address_line2 = address_data['address_line2']
            customer.city = address_data['city']
            customer.state = address_data['state']
            customer.country = address_data['country']
            
            # Save the primary label securely in the JSON array metadata
            meta_found = False
            for item in customer.additional_addresses:
                if item.get('_meta'):
                    item['primary_label'] = address_data['label']
                    meta_found = True
                    break
            if not meta_found:
                customer.additional_addresses.append({'_meta': True, 'primary_label': address_data['label']})
                
            customer.save()
            return JsonResponse({'success': True, 'message': 'Primary address updated'})

        elif addr_id and str(addr_id).isdigit():
            idx = int(addr_id)
            if isinstance(customer.additional_addresses, list) and 0 <= idx < len(customer.additional_addresses):
                existing_data = customer.additional_addresses[idx]
                existing_data.update(address_data)
                customer.additional_addresses[idx] = existing_data
                customer.save(update_fields=['additional_addresses'])
                return JsonResponse({'success': True, 'message': 'Address updated'})
            else:
                return JsonResponse({'success': False, 'error': 'Address not found'}, status=404)

        else:
            customer.add_extra_address(address_data)
            return JsonResponse({'success': True, 'message': 'New address added'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required(login_url='/login/')
@require_POST
def set_default_address(request):
    customer = request.user.customer_profile
    try:
        data = json.loads(request.body)
        addr_id = data.get('address_id')

        if addr_id == 'primary':
            return JsonResponse({'success': True, 'message': 'Already default'})

        if addr_id is not None and str(addr_id).isdigit():
            idx = int(addr_id)
            
            if isinstance(customer.additional_addresses, list) and 0 <= idx < len(customer.additional_addresses):
                # Grab the extra address they want to make default
                new_default = customer.additional_addresses.pop(idx)
                new_label = new_default.get('label', 'Address')
                
                # Find the old primary label from metadata
                old_primary_label = 'Address'
                meta_idx = None
                for i, item in enumerate(customer.additional_addresses):
                    if item.get('_meta'):
                        old_primary_label = item.get('primary_label', 'Address')
                        meta_idx = i
                        break
                
                # Package up the CURRENT default address so we don't lose it
                old_default = {
                    'address_line1': customer.address_line1,
                    'address_line2': customer.address_line2,
                    'city': customer.city,
                    'state': customer.state,
                    'country': customer.country,
                    'label': old_primary_label,
                }
                
                # Put the old default into the extra addresses list
                if old_default['address_line1'] or old_default['city']:
                    customer.additional_addresses.append(old_default)
                
                # Overwrite the primary fields with the new default data
                customer.address_line1 = new_default.get('address_line1', '')
                customer.address_line2 = new_default.get('address_line2', '')
                customer.city = new_default.get('city', '')
                customer.state = new_default.get('state', '')
                customer.country = new_default.get('country', 'Nigeria')
                
                # Save the new primary label to metadata
                if meta_idx is not None:
                    customer.additional_addresses[meta_idx]['primary_label'] = new_label
                else:
                    customer.additional_addresses.append({'_meta': True, 'primary_label': new_label})
                    
                customer.save()
                return JsonResponse({'success': True, 'message': 'Default address updated!'})
            else:
                return JsonResponse({'success': False, 'error': 'Address not found'}, status=404)
                
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required(login_url='/login/')
@require_POST
def delete_address(request):
    customer = request.user.customer_profile
    try:
        data = json.loads(request.body)
        addr_id = data.get('address_id')

        if addr_id == 'primary':
            return JsonResponse({'success': False, 'error': 'You cannot delete your primary address. Please set another address as default first.'}, status=400)

        if addr_id is not None and str(addr_id).isdigit():
            idx = int(addr_id)
            if isinstance(customer.additional_addresses, list) and 0 <= idx < len(customer.additional_addresses):
                customer.additional_addresses.pop(idx)
                customer.save(update_fields=['additional_addresses'])
                return JsonResponse({'success': True, 'message': 'Address deleted successfully'})
            else:
                return JsonResponse({'success': False, 'error': 'Address not found'}, status=404)
                
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

# Cart AJAX views
@login_required(login_url='/login/')
@require_POST
def add_to_cart(request, product_id):
    customer = get_or_create_customer_profile(request.user)
    quantity = int(request.POST.get('quantity', 1))
    
    # 1. Get the List of Variant IDs from the Frontend
    # The 3D customizer should send: variants=[12, 45, 89] (IDs of selected ProductVariants)
    variant_ids = request.POST.getlist('variants') 
    # Fallback for old templates: check 'color'/'size' inputs and find their IDs
    if not variant_ids:
        # (Add your fallback logic here if keeping old templates active)
        pass

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=product_id, is_active=True)
            
            # Stock Check
            if product.stock_quantity < quantity:
                return JsonResponse({'success': False, 'error': 'Insufficient stock'}, status=400)

            # 2. Validate Variants
            selected_variants = []
            if variant_ids:
                selected_variants = list(ProductVariant.objects.filter(
                    id__in=variant_ids, 
                    product=product, 
                    is_available=True
                ))
                if len(selected_variants) != len(variant_ids):
                    return JsonResponse({'success': False, 'error': 'One or more selected options are invalid'}, status=400)

            # 3. Use the "Smart Add" Logic (Check for duplicates)
            # This replaces your "get_or_create" because M2M makes get_or_create impossible
            cart_obj, _ = Cart.objects.get_or_create(customer=customer)
            
            # Helper to check if item exists with EXACT same variants
            existing_items = CartItem.objects.filter(cart=cart_obj, product=product)
            target_item = None
            
            target_ids = set(v.id for v in selected_variants)
            
            for item in existing_items:
                current_ids = set(item.variants.values_list('id', flat=True))
                if current_ids == target_ids:
                    target_item = item
                    break
            
            if target_item:
                target_item.quantity += quantity
                target_item.save()
            else:
                target_item = CartItem.objects.create(cart=cart_obj, product=product, quantity=quantity)
                target_item.variants.set(selected_variants)

            return JsonResponse({'success': True, 'cart_count': cart_obj.total_items})

    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)

@login_required(login_url='/login/')
@require_POST
def update_cart_item(request, item_id):
    """Update cart item quantity with race-condition protection"""
    if hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    customer = get_or_create_customer_profile(request.user)
    quantity = int(request.POST.get('quantity', 1))
    
    try:
        with transaction.atomic():
            # Fetch cart item with related product
            cart_item = CartItem.objects.select_related('product').get(
                id=item_id,
                cart__customer=customer
            )
            
            if quantity < 1:
                cart_item.delete()
                return JsonResponse({'success': True, 'message': 'Item removed from cart'})
            
            # Lock the product row to prevent TOCTOU race conditions
            product = Product.objects.select_for_update().get(id=cart_item.product.id)
            
            # Re-check stock inside transaction with locked row
            if product.stock_quantity < quantity:
                return JsonResponse({'success': False, 'error': 'Insufficient stock'}, status=400)
            
            cart_item.quantity = quantity
            cart_item.save()

            # 1. Recalculate Cart Totals
            cart = cart_item.cart
            cart_subtotal_val = cart.total_price  # Uses your model property
            
            # 2. Get Shipping (Same logic as cart view)
            shipping_estimate = getattr(settings, 'SHIPPING_ESTIMATE', Decimal('750.00'))
            if not isinstance(shipping_estimate, Decimal):
                shipping_estimate = Decimal(str(shipping_estimate))
                
            # 3. Calculate Grand Total
            total_val = cart_subtotal_val + shipping_estimate
            
            # Calculate subtotal within transaction
            subtotal = float(cart_item.subtotal)
        
        return JsonResponse({
            'success': True,
            'cart_subtotal': f"{cart_subtotal_val:,.2f}",
            'total': f"{total_val:,.2f}"
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Cart item not found'}, status=404)

@login_required(login_url='/login/')
def get_product_variants(request, product_id):
    """
    Get available variants grouped by Type (e.g., Handle, Body) 
    instead of just Color/Size.
    """
    try:
        product = Product.objects.get(id=product_id, is_active=True, is_available=True)
        
        # Output structure: {'Handle': [{'id': 1, 'value': 'Red'}, ...], 'Size': [...]}
        grouped_variants = {}
        
        # Fetch all available variants
        variants = product.variants.filter(is_available=True)
        
        for v in variants:
            v_type = v.variant_type # e.g. "Handle"
            if v_type not in grouped_variants:
                grouped_variants[v_type] = []
            
            grouped_variants[v_type].append({
                'id': v.id,
                'value': v.variant_value
            })
            
        return JsonResponse({
            'success': True,
            'groups': grouped_variants
        })
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)

@login_required(login_url='/login/')
@require_POST
def update_cart_item_variants(request, item_id):
    """
    Update cart item variants (Handles Merge Logic if the new selection matches existing item)
    """
    customer = get_or_create_customer_profile(request.user)
    
    # Get list of new Variant IDs from the modal
    new_variant_ids = request.POST.getlist('variants')
    new_variant_ids = [int(vid) for vid in new_variant_ids if vid]

    try:
        with transaction.atomic():
            cart_item = CartItem.objects.select_related('product').get(
                id=item_id,
                cart__customer=customer
            )
            product = cart_item.product

            # 1. Validate that the new variants belong to this product
            valid_variants = list(ProductVariant.objects.filter(
                id__in=new_variant_ids, 
                product=product
            ))
            
            if len(valid_variants) != len(new_variant_ids):
                return JsonResponse({'success': False, 'error': 'Invalid variant selection'}, status=400)

            # 2. Check for Merge Conflict
            # (Did the user change this item to match an item that ALREADY exists in the cart?)
            existing_items = CartItem.objects.filter(
                cart=cart_item.cart, 
                product=product
            ).exclude(id=item_id) # Don't compare with self
            
            target_ids = set(v.id for v in valid_variants)
            merge_target = None
            
            for item in existing_items:
                current_ids = set(item.variants.values_list('id', flat=True))
                if current_ids == target_ids:
                    merge_target = item
                    break
            
            if merge_target:
                # MERGE LOGIC: Add quantity to existing item, delete current item
                new_qty = merge_target.quantity + cart_item.quantity
                if new_qty > product.stock_quantity:
                     return JsonResponse({'success': False, 'error': f'Insufficient stock. Max {product.stock_quantity}'}, status=400)
                
                merge_target.quantity = new_qty
                merge_target.save()
                cart_item.delete()
                
            else:
                # UPDATE LOGIC: Just change the variants on the current item
                cart_item.variants.set(valid_variants)
                cart_item.save()
        
        return JsonResponse({'success': True, 'message': 'Cart updated'})
        
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Cart item not found'}, status=404)

@login_required(login_url='/login/')
@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart"""
    if hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    customer = get_or_create_customer_profile(request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart__customer=customer)
    cart_item.delete()
    
    return JsonResponse({'success': True, 'message': 'Item removed from cart'})

# Checkout functionality
@login_required(login_url='/login/')
def checkout(request):
    """Checkout page - display order summary and shipping form"""
    from escrow.fee_calculator import calculate_delivery_fee, BASE_DELIVERY_FEE
    
    customer = get_or_create_customer_profile(request.user)
    cart_obj, created = Cart.objects.get_or_create(customer=customer)
    cart_items = CartItem.objects.filter(cart=cart_obj).select_related('product', 'product__vendor')
    
    if customer.kyc_profile.status == "APPROVED":
        kyc_verified = True
    else:
        kyc_verified = False
    
    if not cart_items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')
    
    # Calculate subtotal
    subtotal = Decimal('0.00')
    for item in cart_items:
        subtotal += item.subtotal
    
    # Count unique vendors in cart for delivery fee calculation
    unique_vendors = set()
    for item in cart_items:
        if item.product.vendor:
            unique_vendors.add(item.product.vendor.id)
    vendor_count = len(unique_vendors)
    
    # Calculate delivery fee based on vendor count (₦250 per vendor)
    total_delivery_fee = calculate_delivery_fee(vendor_count)
    delivery_fee_per_vendor = BASE_DELIVERY_FEE
    
    # Calculate total (subtotal + delivery fee)
    total = subtotal + total_delivery_fee
    
    # Get currency symbol
    currency_symbol = DEFAULT_CURRENCY_SYMBOL
    if cart_items.exists():
        first_product = cart_items.first().product
        if first_product.vendor:
            currency_info = first_product.vendor.get_currency_display_info()
            currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    # Pre-fill shipping address from customer profile
    shipping_data = {
        'shipping_address': f"{customer.address_line1 or ''}\n{customer.address_line2 or ''}".strip(),
        'shipping_city': customer.city or '',
        'shipping_state': customer.state or '',
        'shipping_postal_code': customer.postal_code or '',
        'shipping_country': customer.country or '',
    }
    
    # NEW: Fetch all user addresses for the modal
    all_addresses = customer.get_all_addresses()

    context = {
        'cart': cart_obj,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'vendor_count': vendor_count,
        'delivery_fee_per_vendor': delivery_fee_per_vendor,
        'total_delivery_fee': total_delivery_fee,
        'total': total,
        'currency_symbol': currency_symbol,
        'customer': customer,
        'kyc_verified': kyc_verified,
        'shipping_data': shipping_data,
        'payment_method': 'Payment on delivery!',
        'checkout_draft_id': request.session.get('checkout_draft_id'),
        'all_addresses': all_addresses, # For the address selection modal
    }
    return render(request, "MAIN/checkout.html", context)

@login_required(login_url='/login/')
@require_POST
def create_order(request):
    logger = logging.getLogger(__name__)
    
    # --- 1. GET CUSTOMER FIRST (Moved Up) ---
    customer = get_or_create_customer_profile(request.user)

    # GET THE NEW UPDATES FROM CHECKOUT
    if request.method == 'POST':
        
        # --- ROBUST PIN VERIFICATION ---
        delivery_pin = request.POST.get('delivery_pin')
        
        # 1. Did the frontend send a PIN?
        if not delivery_pin:
            return JsonResponse({'success': False, 'error': 'Delivery PIN is required to authorize this order.'})
            
        # 2. Does the customer actually have a PIN set in the database?
        if not customer.delivery_pin:
            return JsonResponse({
                'success': False, 
                'error': 'You have not set up a Delivery PIN yet. Please create one using the link in the PIN popup.'
            })
            
        # 3. Is the PIN correct?
        if not customer.check_delivery_pin(delivery_pin):
            return JsonResponse({'success': False, 'error': 'Incorrect Delivery PIN. Authorization failed.'})
        # -------------------------------

        # --- 0. HANDLE PROFILE UPDATE (If triggered by Unverified Flow) ---
        if request.POST.get('update_profile') == 'true':
            try:
                # Update Text Fields
                c_first_name = request.POST.get('kyc_first_name')
                c_last_name = request.POST.get('kyc_last_name')
                c_phone = request.POST.get('kyc_phone')
                
                if c_first_name: customer.first_name = c_first_name
                if c_last_name: customer.last_name = c_last_name
                if c_phone: customer.phone = c_phone

                customer.gender = request.POST.get('kyc_gender', customer.gender)
                
                # Update Profile Picture (If uploaded)
                if 'kyc_profile_picture' in request.FILES:
                    customer.profile_picture = request.FILES['kyc_profile_picture']
                
                customer.save()
                
                # Sync with User Account (for auth consistency)
                user = request.user
                if c_first_name: user.first_name = c_first_name
                if c_last_name: user.last_name = c_last_name
                user.save()
                
                print(f"✅ Customer Profile Updated: {customer.full_name}")
                
            except Exception as e:
                print(f"⚠️ Profile Update Failed: {e}")
                # We typically continue to order creation even if profile update fails, 
                # or you can return an error JSON here.
    
    # --- SETUP CUSTOMER & CART ---
    cart_obj, created = Cart.objects.get_or_create(customer=customer)
    kyc_verified = False
    
    cart_items = CartItem.objects.filter(cart=cart_obj).select_related(
        'product', 'product__vendor'
    ).prefetch_related('variants')
    
    if not cart_items.exists():
        return JsonResponse({'success': False, 'error': 'Your cart is empty'}, status=400)
    
    try:
        with transaction.atomic():
            # 1. GROUP ITEMS BY VENDOR
            vendor_groups = {}
            for item in cart_items:
                if not item.product: continue
                vendor = item.product.vendor
                if not vendor: continue
                if vendor not in vendor_groups: vendor_groups[vendor] = []
                vendor_groups[vendor].append(item)
            
            # 2. GENERATE MASTER ID
            master_public_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            
            # 3. CONTEXT & CONFIGURATION
            # [FIX] Initialize variables to avoid UnboundLocalError
            draft_id = request.session.get('checkout_draft_id')
            draft_instance = None 
            delivery_type = 'standard_delivery'
            
            # [FIX] Properly fetch the object if ID exists
            if draft_id:
                try:
                    draft_instance = DraftOrder.objects.get(id=draft_id, customer=customer)
                    delivery_type = draft_instance.delivery_type
                except DraftOrder.DoesNotExist:
                    draft_instance = None # Safety fallback

            # Capture Shipping Info
            shipping_address = request.POST.get('shipping_address', '').strip()
            shipping_city = request.POST.get('shipping_city', '').strip()
            shipping_state = request.POST.get('shipping_state', '').strip()
            shipping_postal_code = request.POST.get('shipping_postal_code', '').strip()
            shipping_country = request.POST.get('shipping_country', 'Nigeria').strip()

            # --- 2. KYC OVERRIDE: Check for Verified ID ---
            try:
                # Access the OneToOne profile we created
                kyc = customer.kyc_profile 
                
                if kyc.status == 'APPROVED':
                    # OVERRIDE: Force the name to match the ID
                    recipient_name = kyc.full_name_on_id
                    kyc_verified = True
                    print(f"✅ Using Verified KYC Name: {recipient_name}")

            except ObjectDoesNotExist:
                # No KYC profile exists, stick to address name
                pass

            # 4. CREATE MASTER ORDER (The Customer's Receipt)
            # GLOBAL_DELIVERY_FEE: ₦250 charged ONCE here.
            GLOBAL_DELIVERY_FEE = Decimal('250.00') 
            
            master_order = MasterOrder.objects.create(
                public_order_id=master_public_id,
                customer=customer,
                total_amount=Decimal('0.00'), # Will be updated after loop
                delivery_fee=GLOBAL_DELIVERY_FEE,
                payment_status='pending', 
                is_kyc_verified=kyc_verified
            )

            grand_total_products = Decimal('0.00')
            sub_order_index = 1

            # --- INITIALIZE AGGREGATES FOR MASTER LOGISTICS ---
            all_products_payload = {}
            all_vendors_payload = {}
            all_configurations_payload = {}
            all_pickup_payload = {}
            
            # 5. PROCESS SUB-ORDERS (Per Vendor)
            for vendor, items in vendor_groups.items():
                
                subtotal = Decimal('0.00')
                order_items_buffer = []
                
                # A. Lock Products & Calculate Subtotal
                product_ids = [item.product.id for item in items]
                products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)}

                for item in items:
                    product = products.get(item.product.id)
                    
                    # Stock Check
                    if product.stock_quantity < item.quantity:
                        raise ValidationError(f"Insufficient stock for {product.name}.")
                    
                    item_subtotal = product.price * item.quantity
                    subtotal += item_subtotal
                    
                    order_items_buffer.append({
                        'product': product, 'quantity': item.quantity, 
                        'price': product.price, 'subtotal': item_subtotal,
                        'variants': list(item.variants.all())
                    })

                # B. Create Sub-Order (Vendor View)
                # NOTE: delivery_fee is 0 here so Vendor sees "Flat" earnings.
                order = Order(
                    master_order=master_order,
                    order_number=f"{master_public_id}-{sub_order_index}",
                    customer=customer,
                    vendor=vendor,
                    subtotal=subtotal,
                    shipping_address=shipping_address,
                    shipping_city=shipping_city,
                    shipping_state=shipping_state,
                    shipping_postal_code=shipping_postal_code,
                    shipping_country=shipping_country,
                    status='processing',
                    payment_status='paid', # Marked paid because Master will be locked
                    delivery_type=delivery_type,
                    delivery_fee=Decimal('0.00'), # Hidden from Vendor
                    total=subtotal,
                    is_kyc_verified=kyc_verified
                )
                
                # C. Apply Luxa Service Cut
                # calculate_fees adds 250 by default, so we override it immediately.
                calculate_and_apply_order_fees(order, subtotal)
                order.delivery_fee = Decimal('0.00') 
                order.total = subtotal 
                order.save()
                
                grand_total_products += subtotal

                # D. Credit Vendor (Pending Clearing)
                # Credits the 'vendor_payout' (Subtotal - Service Fee)
                step_2_start_delivery(vendor.user_account, order.vendor_payout, order.id)

                # E. Save Items & Deduct Stock
                for data in order_items_buffer:
                    order_item = OrderItem.objects.create(
                        order=order, product=data['product'],
                        quantity=data['quantity'], price=data['price'],
                        subtotal=data['subtotal']
                    )
                    if data['variants']: 
                        order_item.variants.set(data['variants'])
                    
                    data['product'].stock_quantity -= data['quantity']
                    data['product'].save()

                # -----------------------------------------------------------
                # F. LUXAORDER CREATION (Logistics / Courier System)
                # -----------------------------------------------------------
                
                # 1. Vendor Details (Keyed by Vendor ID)
                all_vendors_payload[str(vendor.id)] = {
                    'business_name': vendor.business_name,
                    'address': vendor.business_address,
                    'city': vendor.city,
                    'phone': vendor.official_phone,
                    'email': vendor.user_account.email
                }

                # 2. Product & Pickup Details
                for item in items:
                    p_id = str(item.product.id)
                    
                    # A. Product Payload (Accumulate Quantity if needed, or overwrite)
                    if p_id in all_products_payload:
                        all_products_payload[p_id]['quantity'] += item.quantity
                    else:
                        all_products_payload[p_id] = {
                            'name': item.product.name, 
                            'quantity': item.quantity,
                            'price': float(item.product.price),
                            'image': item.product.main_image.url if item.product.main_image else ""
                        }
                    
                    # B. Configurations
                    variants_dict = {v.variant_type: v.variant_value for v in item.variants.all()}
                    if variants_dict: 
                        # Note: Simple assignment. If complex variant aggregation is needed, logic goes here.
                        all_configurations_payload[p_id] = variants_dict
                    
                    # C. Pickup Location
                    loc_raw = getattr(item.product, 'pickup_location', None)
                    if loc_raw: 
                        all_pickup_payload[p_id] = loc_raw
                    else: 
                        all_pickup_payload[p_id] = {
                            'address': vendor.business_address, 'city': vendor.city,
                            'state': vendor.state, 'phone': vendor.official_phone,
                        }

                sub_order_index += 1

            # 6. FINALIZE MASTER ORDER
            # Total = (All Products) + (Global Fee)
            master_order.total_amount = grand_total_products + GLOBAL_DELIVERY_FEE
            master_order.payment_status = 'paid'
            master_order.save()

            # --- [UPDATE] G. CREATE UNIFIED LUXAORDER (Courier System) ---
            # Creates one logistics order for the entire Master transaction
            LUXAOrder.objects.create(
                order_source=master_order,  # Linked to MasterOrder
                order_id=str(master_order.public_order_id), # Use Public ID (e.g., ORD-1234) for Courier tracking
                customer_id=str(customer.id),
                delivery_type=delivery_type,
                status="pending_assignment",
                total_price=master_order.total_amount,
                
                # Aggregated Data
                products=all_products_payload, 
                vendors=all_vendors_payload,
                product_configurations=all_configurations_payload,
                pickup_locations=all_pickup_payload,
                
                # Delivery Location (Captured earlier in the view)
                delivery_location={
                    'address': shipping_address, 'city': shipping_city,
                    'state': shipping_state, 'postal_code': shipping_postal_code,
                    'country': shipping_country,
                }
            )

            # 7. LOCK FUNDS (CUSTOMER SIDE)
            # Locks the full amount (Products + 250) from Customer Wallet
            try:
                lock_master_order_funds(request.user, master_order)
            except ValueError as e:
                transaction.set_rollback(True)
                return JsonResponse({
                    'success': False, 
                    'error': f"Payment Failed: {str(e)}",
                    'wallet_url': '/escrow/dashboard/'
                }, status=400)

            # 8. CLEANUP
            cart_items.delete()
            if draft_instance:
                draft_instance.delete()
                # Clear session
                if 'checkout_draft_id' in request.session:
                    del request.session['checkout_draft_id']
            
            return JsonResponse({
                'success': True,
                'message': 'Order placed successfully!',
                'redirect_url': f'/orders/{master_order.public_order_id}/'
            })

    except Exception as e:
        logger.exception('Order Error')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
@login_required
@require_POST
def mark_order_shipped(request, order_id):
    # Security: Ensure user is a vendor
    if not hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    vendor = request.user.vendor_profile
    
    # Security: Ensure the order belongs to THIS vendor
    order = get_object_or_404(Order, pk=order_id, vendor=vendor)
    
    if order.status == 'shipped':
        return JsonResponse({'success': False, 'error': 'Order already shipped'})

    # Update status
    try:
        with transaction.atomic():
            order.status = 'shipped'
            order.shipped_at = timezone.now()
            order.save()
            
            # Escrow Move: Locked -> Pending
            # Use vendor_payout (after Luxa fees) for pending balance
            vendor_share = order.vendor_payout if order.vendor_payout and order.vendor_payout > 0 else order.subtotal
            step_2_start_delivery(request.user, vendor_share, order.id)
            
        return JsonResponse({'success': True, 'message': 'Order marked as shipped'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def confirm_delivery(request, order_id):
    customer = get_or_create_customer_profile(request.user)
    
    # Security: Ensure the order belongs to THIS customer
    order = get_object_or_404(Order, pk=order_id, customer=customer)
    
    if order.status == 'delivered':
        return JsonResponse({'success': False, 'error': 'Order already delivered'})

    # Update status
    try:
        with transaction.atomic():  # <--- Add this safety wrapper
            order.status = 'delivered'
            order.delivered_at = timezone.now()
            order.save()
            
            step_3_complete_delivery(order.id)
            
        return JsonResponse({'success': True, 'message': 'Delivery confirmed'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Wishlist functionality
@login_required(login_url='/login/')
@require_POST
def add_to_wishlist(request, product_id):
    """Add product to wishlist"""
    if hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Vendors cannot add items to wishlist'}, status=403)
    
    customer = get_or_create_customer_profile(request.user)
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Get or create wishlist
    wishlist, created = Wishlist.objects.get_or_create(customer=customer)
    
    # Check if already in wishlist
    wishlist_item, created = WishlistItem.objects.get_or_create(
        wishlist=wishlist,
        product=product
    )
    
    if created:
        return JsonResponse({
            'success': True,
            'message': 'Product added to wishlist',
            'wishlist_count': wishlist.total_items
        })
    else:
        return JsonResponse({
            'success': False,
            'error': 'Product is already in your wishlist'
        }, status=400)

@login_required(login_url='/login/')
@require_POST
def remove_from_wishlist(request, product_id):
    """Remove product from wishlist"""
    if hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    customer = get_or_create_customer_profile(request.user)
    wishlist = get_object_or_404(Wishlist, customer=customer)
    wishlist_item = get_object_or_404(WishlistItem, wishlist=wishlist, product_id=product_id)
    wishlist_item.delete()
    
    return JsonResponse({
        'success': True,
        'message': 'Product removed from wishlist',
        'wishlist_count': wishlist.total_items
    })

@login_required(login_url='/login/')
def wishlist(request):
    """View wishlist"""
    if hasattr(request.user, 'vendor_profile'):
        return redirect('/vendash/')
    
    customer = get_or_create_customer_profile(request.user)
    wishlist_obj, created = Wishlist.objects.get_or_create(customer=customer)
    wishlist_items = WishlistItem.objects.filter(wishlist=wishlist_obj).select_related('product', 'product__vendor', 'product__category')
    
    # Get currency symbol
    currency_symbol = DEFAULT_CURRENCY_SYMBOL
    if wishlist_items.exists():
        first_product = wishlist_items.first().product
        if first_product.vendor:
            currency_info = first_product.vendor.get_currency_display_info()
            currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    context = {
        'wishlist': wishlist_obj,
        'wishlist_items': wishlist_items,
        'currency_symbol': currency_symbol,
    }
    return render(request, "MAIN/wishlist.html", context)

# Search view
def search(request):
    """Search products"""
    query = request.GET.get('q', '').strip()
    products = []
    
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(sku__icontains=query),
            is_active=True,
            is_available=True
        ).select_related('vendor', 'category')[:20]
    
    context = {
        'query': query,
        'products': products,
        'currency_symbol': DEFAULT_CURRENCY_SYMBOL,
    }
    return render(request, "MAIN/search_results.html", context)

# Orders panel view
@login_required(login_url='/login/')
def customer_orders(request):
    """
    Customer orders panel.
    Groups Master Orders based on the status of their sub-shipments.
    """
    from .models import MasterOrder
    
    customer = get_or_create_customer_profile(request.user)
    
    # 1. Fetch Masters with their Sub-Orders
    # We use prefetch_related so we don't hit the DB in the loop
    all_masters = MasterOrder.objects.filter(customer=customer).prefetch_related('sub_orders').order_by('-created_at')
    
    # 2. Categorize Logic
    ongoing_orders = all_masters.exclude(status__in=['delivered', 'cancelled', 'refunded'])
    completed_orders = all_masters.filter(status='delivered')
    cancelled_orders = all_masters.filter(status__in=['cancelled', 'refunded'])

    # 3. Currency Symbol (Grab from first available order or default)
    currency_symbol = DEFAULT_CURRENCY_SYMBOL
    
    if all_masters.exists() and all_masters.first().sub_orders.exists():
        first_vendor = all_masters.first().sub_orders.first().vendor
        if first_vendor:
            c_info = first_vendor.get_currency_display_info()
            currency_symbol = c_info.get('symbol', DEFAULT_CURRENCY_SYMBOL)

    context = {
        'ongoing_orders': ongoing_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'currency_symbol': currency_symbol,
    }
    return render(request, "MAIN/customer_orders.html", context)

@login_required(login_url='/login/')
def customer_order_detail(request, order_id):
    """Customer order detail page"""
    from .models import MasterOrder  # <--- Added missing import
    
    customer = get_or_create_customer_profile(request.user)
    
    # 1. Get the Master Order (The wrapper)
    master_order = get_object_or_404(
        MasterOrder.objects.prefetch_related(
            'sub_orders',
            'sub_orders__vendor',
            'sub_orders__items',
            'sub_orders__items__product',
            'sub_orders__items__variants'
        ),
        public_order_id=order_id, # Lookup by the public string ID
        customer=customer
    )

    # 2. Mark all sub-orders as seen
    for sub in master_order.sub_orders.all():
        if not sub.customer_seen:
            sub.customer_seen = True
            sub.save(update_fields=['customer_seen'])

    context = {
        'master_order': master_order,
        'currency_symbol': DEFAULT_CURRENCY_SYMBOL,
    }
    return render(request, "MAIN/customer_order_detail.html", context)

@login_required(login_url='/login/')
def vendor_product_orders(request):
    """Vendor product orders page - Lists all orders for this vendor"""
    
    # 1. Vendor Check
    try:
        vendor = request.user.vendor_profile
    except AttributeError:
        return redirect('/customerpage/')
    
    # 2. Get Vendor's Orders
    # Since your create_order view splits orders by vendor, 
    # filtering by vendor=vendor AUTOMATICALLY ensures you only see your products.
    orders = Order.objects.filter(vendor=vendor).select_related(
        'customer'
    ).prefetch_related(
        'items__product'   
    ).order_by('-created_at')
    
    # 3. Currency
    currency_info = vendor.get_currency_display_info()
    currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    # 4. CUSTOMER CONTEXT (Crucial for Sidebar/Navbar to work)
    customer = get_or_create_customer_profile(request.user)
    customer_orders = Order.objects.filter(customer=customer).order_by('-created_at')
    
    context = {
        # Vendor Data
        'orders': orders,
        'currency_symbol': currency_symbol,
        
        # Customer Data (Fixes the "Blank Page" issue)
        'customer': customer,
        'pending_deliveries': customer_orders.exclude(status__in=['delivered', 'cancelled', 'refunded']).count(),
        'ongoing_orders': customer_orders.exclude(status__in=['delivered', 'cancelled', 'refunded'])[:5],
        'wishlist_count': Wishlist.objects.filter(customer=customer).values('items').count(), # specific optimization or use your helper
    }
    return render(request, "MAIN/vendor_product_orders.html", context)

@login_required(login_url='/login/')
def vendor_order_detail(request, order_id):
    """Vendor order detail page - Shows specific order details"""
    
    # 1. Vendor Check
    try:
        vendor = request.user.vendor_profile
    except AttributeError:
        return redirect('/customerpage/')
    
    # 2. Get the specific Order
    # This automatically secures it: If order_id exists but belongs to another vendor,
    # get_object_or_404 will raise a 404 Error.
    order = get_object_or_404(
        Order.objects.select_related('vendor', 'customer').prefetch_related(
            'items__product'
        ),
        id=order_id,
        vendor=vendor
    )

    if not order.vendor_seen:
        order.vendor_seen = True
        order.save(update_fields=['vendor_seen'])
    
    # 3. Currency
    currency_info = vendor.get_currency_display_info()
    currency_symbol = currency_info.get('symbol', DEFAULT_CURRENCY_SYMBOL) if isinstance(currency_info, dict) else DEFAULT_CURRENCY_SYMBOL
    
    # 4. CUSTOMER CONTEXT (Crucial for Sidebar/Navbar)
    customer = get_or_create_customer_profile(request.user)
    customer_orders = Order.objects.filter(customer=customer).order_by('-created_at')
    
    context = {
        # Vendor Data
        'order': order,
        'currency_symbol': currency_symbol,
        
        # Customer Data
        'customer': customer,
        'pending_deliveries': customer_orders.exclude(status__in=['delivered', 'cancelled', 'refunded']).count(),
        'ongoing_orders': customer_orders.exclude(status__in=['delivered', 'cancelled', 'refunded'])[:5],
        'wishlist_count': Wishlist.objects.filter(customer=customer).values('items').count(),
    }
    return render(request, "MAIN/vendor_order_detail.html", context)

# Notification actions
@login_required(login_url='/login/')
@require_POST
def mark_notification_read(request, notification_id):
    """Mark notification as read"""
    if hasattr(request.user, 'vendor_profile'):
        notification = get_object_or_404(Notification, id=notification_id, vendor=request.user.vendor_profile)
    else:
        customer = get_or_create_customer_profile(request.user)
        notification = get_object_or_404(Notification, id=notification_id, customer=customer)
    
    # FIX: Use the model's built in method so the timestamp is recorded!
    notification.mark_as_read() 
    
    return JsonResponse({'success': True})

@staff_member_required
def check_notifications(request):
    """
    API endpoint for admin polling. 
    Returns the count of unread notifications for the logged-in user's vendor (or all if superuser).
    """
    if request.user.is_superuser:
        # This excludes User specific alerts (like Wallet Deposits)
        admin_notifs = Notification.objects.filter(
            customer__isnull=True, 
            vendor__isnull=True, 
            is_read=False
        )
        
        unread_count = admin_notifs.count()
        latest = admin_notifs.first()

    elif hasattr(request.user, 'vendor_profile'):
        unread_count = Notification.objects.filter(vendor=request.user.vendor_profile, is_read=False).count()
        latest = Notification.objects.filter(vendor=request.user.vendor_profile, is_read=False).first()
    else:
        return JsonResponse({'count': 0})

    data = {
        'count': unread_count,
        'latest_title': latest.title if latest else None,
        'latest_message': latest.message if latest else None
    }
    return JsonResponse(data)

# Check notifications for vendor and customers
@login_required
def check_user_notifications(request):
    """
    API endpoint that the frontend polls every 30 seconds.
    Returns the latest unread notification for the logged-in user.
    """
    user = request.user
    notifications = Notification.objects.none()

    # Determine if user is Vendor or Customer and get their specific notifications
    if hasattr(user, 'vendor_profile'):
        notifications = Notification.objects.filter(vendor=user.vendor_profile, is_read=False)
    elif hasattr(user, 'customer_profile'):
        notifications = Notification.objects.filter(customer=user.customer_profile, is_read=False)

    # Get the latest one
    latest = notifications.first()
    unread_count = notifications.count()

    # Prepare data for the frontend
    data = {
        'count': unread_count,
        'has_new': latest is not None,
        'latest': {
            'id': latest.id,
            'title': latest.title,
            'message': latest.message,
            'type': latest.notification_type
        } if latest else None
    }
    return JsonResponse(data)

@login_required(login_url='/login/')
@require_POST
def delete_notification(request, notification_id):
    """Delete notification"""
    if hasattr(request.user, 'vendor_profile'):
        notification = get_object_or_404(Notification, id=notification_id, vendor=request.user.vendor_profile)
    else:
        customer = get_or_create_customer_profile(request.user)
        notification = get_object_or_404(Notification, id=notification_id, customer=customer)
    
    notification.delete()
    
    return JsonResponse({'success': True})

# Product management actions
@login_required(login_url='/login/')
@require_POST
def delete_product(request, product_id):
    """Delete product with foreign key protection
    
    Note: There is a small TOCTOU window where a new order/cart could be created
    between the check and deletion. The IntegrityError catch provides a safety net.
    For truly race-free deletion, implement soft deletes (recommended).
    """
    if not hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    vendor = request.user.vendor_profile
    
    try:
        with transaction.atomic():
            product = get_object_or_404(Product, id=product_id, vendor=vendor)
            
            # WishlistItem references - delete them before product deletion
            # (WishlistItems are less critical and can be safely removed)
            WishlistItem.objects.filter(product=product).delete()
            
            # ProductImage references (CASCADE will delete, safe)
            # Notification references (SET_NULL, safe)
            
            product.delete()
        
        return JsonResponse({'success': True, 'message': 'Product deleted'})
    except IntegrityError:
        # Catch any integrity errors that might occur during deletion
        # This provides a safety net for the TOCTOU window and triggers rollback
        return JsonResponse({
            'success': False,
            'error': 'Cannot delete product: it has active references. Consider suspending the product instead.'
        }, status=400)

@login_required(login_url='/login/')
@require_POST
def suspend_product(request, product_id):
    """Suspend/unsuspend product"""
    if not hasattr(request.user, 'vendor_profile'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    vendor = request.user.vendor_profile
    product = get_object_or_404(Product, id=product_id, vendor=vendor)
    product.is_active = not product.is_active
    product.save()
    
    action = 'suspended' if not product.is_active else 'activated'
    return JsonResponse({'success': True, 'message': f'Product {action}'})

# Order Draft views
@login_required(login_url='/login/')
def order_create_form_view(request, draft_id=None):
    """
    Unified view for Creating and Editing Draft Orders.
    - URL: /order-create/         -> AUTO-HARVEST -> Redirects to Dispatch Prompt
    - URL: /order-edit/<uuid>/    -> Renders 'order_edit_page.html' (Full Editor)
    """
    
    # 1. PREPARE COMMON DATA (Products JSON for JS)
    # We prepare this for the 'Edit' template logic
    available_products = Product.objects.filter(
        is_active=True, 
        is_available=True
    ).select_related('category') # <--- Optimization
    
    product_json_list = []
    
    for p in available_products:
        # Resolve Image URL safely
        img_url = '/static/images/icons/delivery.png' # Default if no image
        if p.main_image:
            img_url = p.main_image.url
            
        product_json_list.append({
            'id': str(p.id),
            'name': p.name,
            'category': p.category.name if p.category else "General", # <--- NEW
            'image': img_url, # <--- NEW
            'price': float(p.price) if hasattr(p, 'price') else 0.0,
            'attributes': get_product_structure_for_json(p) 
        })
    
    import json
    product_json_dump = json.dumps(product_json_list)

    # =======================================================
    # MODE A: EDIT/REVIEW EXISTING DRAFT (draft_id is present)
    # =======================================================
    if draft_id:
        customer = get_or_create_customer_profile(request.user)
        draft = get_object_or_404(DraftOrder, id=draft_id, customer=customer)
        
        # --- SERIALIZE EXISTING ITEMS FOR JS ---
        # This allows the frontend to "hydrate" the rows with the correct
        # products, quantities, and selected attributes.
        items_data = []
        for item in draft.items.all():
            items_data.append({
                'product_id': str(item.product.id),
                'quantity': item.quantity,
                'variations': item.variation_choices # {"Color": "Red", "Size": "M"}
            })
        draft_items_dump = json.dumps(items_data)
        
        # --- POST: Saving Changes to Draft ---
        if request.method == 'POST':
            with transaction.atomic():
                # 1. Update Core Draft Fields
                if 'delivery_type' in request.POST:
                    draft.delivery_type = request.POST.get('delivery_type')
                    draft.save()

                # 2. Rebuild Items
                if 'product_ids' in request.POST or 'product_ids' in request.POST.getlist('product_ids'):
                    draft.items.all().delete()
                    
                    product_ids = request.POST.getlist('product_ids')
                    quantities = request.POST.getlist('quantities')
                    
                    for index, p_id in enumerate(product_ids):
                        if not p_id: continue 
                        
                        qty = int(quantities[index])
                        product = Product.objects.get(id=p_id)
                        
                        row_idx = index + 1 
                        variation_data = {}
                        prefix = f"attr_{row_idx}_{p_id}_"
                        for key in request.POST:
                            if key.startswith(prefix):
                                clean_key = key.replace(prefix, '')
                                variation_data[clean_key] = request.POST[key]
                        
                        DraftOrderItem.objects.create(
                            draft_order=draft,
                            product=product,
                            quantity=qty,
                            variation_choices=variation_data
                        )
                
            messages.success(request, "Order updated successfully.")
            
            # FIXED: Redirect to the Dispatch Prompt so they can launch it
            return redirect('order_dispatch_prompt', draft_id=draft.id)
        
        context = {
            'existing_draft': draft,
            'product_json': product_json_dump,
            'draft_items_json': draft_items_dump,
        }
        return render(request, "MAIN/order_draft/order_edit_page.html", context)


    # =======================================================
    # MODE B: CREATE NEW DRAFT (Auto-Harvest from Cart)
    # =======================================================
    else:
        # 1. Identify Customer
        customer = get_or_create_customer_profile(request.user)

        # 2. Check for intent from URL
        requested_delivery_type = request.GET.get('delivery_type', 'standard_delivery')

        # 3. HARVEST THE CART
        with transaction.atomic():
            cart_obj, _ = Cart.objects.get_or_create(customer=customer)
            cart_items = CartItem.objects.filter(cart=cart_obj).select_related('product').prefetch_related('variants')

            if not cart_items.exists():
                messages.warning(request, "Your cart is empty. Please add items before starting delivery.")
                return redirect('cart')

            # Remove any abandoned temporary drafts to keep DB clean
            DraftOrder.objects.filter(customer=customer, status='temporary').delete()

            # Create the Draft with 'temporary' status so it stays hidden
            draft = DraftOrder.objects.create(
                customer=customer,
                delivery_type=requested_delivery_type, 
                status='temporary'  # <--- CHANGED from 'pending'
            )

            # Convert Cart Items -> Draft Items
            for item in cart_items:
                variation_data = {}
                for v in item.variants.all():
                    variation_data[v.variant_type] = v.variant_value
                
                DraftOrderItem.objects.create(
                    draft_order=draft,
                    product=item.product,
                    quantity=item.quantity,
                    variation_choices=variation_data
                )

        # 4. INSTANT REDIRECT -> DISPATCH PROMPT
        # Changed from 'order_edit_form' to 'order_dispatch_prompt'
        return redirect('order_dispatch_prompt', draft_id=draft.id)

@login_required(login_url='/login/')
def proceed_to_checkout(request, draft_id):
    """
    Transfers Draft items to the Main Cart and redirects to the Checkout page.
    Saves the draft_id in session to link the final order later.
    """
    customer = get_or_create_customer_profile(request.user)
    draft = get_object_or_404(DraftOrder, id=draft_id, customer=customer)
    
    # 1. Validation
    if draft.status not in ['approved', 'eligible']:
        messages.error(request, "This order is not eligible for delivery yet.")
        return redirect('order_eligibility', order_id=draft.id)

    with transaction.atomic():
        # Release stock back to the pool so standard checkout can claim it correctly
        manage_draft_stock(draft, 'release')
    
        # 2. Clear current Cart (Draft takes precedence)
        cart, _ = Cart.objects.get_or_create(customer=customer)
        cart.items.all().delete()
        
        # 3. Transfer Items: Draft -> Cart
        for draft_item in draft.items.all():
            # Create Cart Item
            cart_item = CartItem.objects.create(
                cart=cart,
                product=draft_item.product,
                quantity=draft_item.quantity
            )
            
            # REVERSE LOOKUP: JSON Variants -> Database Variants
            # Draft stores: {"Color": "Red"}
            # Cart needs: ProductVariant objects
            if draft_item.variation_choices:
                variant_objects = []
                for v_type, v_value in draft_item.variation_choices.items():
                    # Find the specific variant ID for this product
                    variant = ProductVariant.objects.filter(
                        product=draft_item.product,
                        variant_type=v_type,
                        variant_value=v_value
                    ).first()
                    
                    if variant:
                        variant_objects.append(variant)
                
                if variant_objects:
                    cart_item.variants.set(variant_objects)

    # 4. Save Draft ID to Session (The "Memory")
    # We need this in 'create_order' to know we should create a LUXAOrder
    request.session['checkout_draft_id'] = str(draft.id)
    
    # 5. Go to Standard Checkout
    return redirect('checkout')    

@login_required(login_url='/login/')
def saved_orders_list(request):
    """
    Displays a gallery of 'Draft' orders.
    """
    customer = get_or_create_customer_profile(request.user)
    
    # FILTER: Exclude 'temporary' drafts so abandoned cart clicks don't clutter the list
    drafts = DraftOrder.objects.filter(customer=customer).exclude(status='temporary').order_by('-created_at')
    
    context = {
        'saved_drafts': drafts, 
    }
    return render(request, "MAIN/order_draft/saved_orders_list.html", context)


@login_required(login_url='/login/')
def order_eligibility_view(request, order_id):
    """
    Runs the 'Pre-Flight' check and renders the Result Page.
    Includes fallback logic for missing product fields.
    """
    customer = get_or_create_customer_profile(request.user)
    draft = get_object_or_404(DraftOrder, id=order_id, customer=customer)
    
    
    # 3. PREPARE DISPLAY DATA
    display_items = []
    
    # Prefetch vendor to avoid hitting DB 50 times
    for item in draft.items.select_related('product', 'product__vendor').all():
        
        # --- THE FIX: SAFE LOCATION LOOKUP ---
        # 1. Try to get the specific pickup_location (if you added the field)
        # 2. If missing, fallback to Vendor's Business Address
        # 3. If that's missing, fallback to "Unknown"
        
        loc_raw = getattr(item.product, 'pickup_location', None)
        
        location_display = "Unknown Location"
        
        if loc_raw:
            # If it's JSON (Dictionary)
            if isinstance(loc_raw, dict):
                location_display = loc_raw.get('address') or f"{loc_raw.get('latitude')}, {loc_raw.get('longitude')}"
            # If it's a String
            else:
                location_display = str(loc_raw)
        
        # FALLBACK: Use Vendor Address if Product has no location data
        elif item.product.vendor:
            # Check what your Vendor address field is named (e.g., 'address', 'business_address')
            location_display = getattr(item.product.vendor, 'business_address', "Vendor HQ")
            
        display_items.append({
            'name': item.product.name,
            'product_id': item.product.id,
            'delivery_display': draft.get_delivery_type_display(),
            'vendor': item.product.vendor.business_name if item.product.vendor else "Luxa Vendor",
            'location': location_display, # <--- Uses the safe string now
            'qty': item.quantity,
            'price': item.product.price,
            'image_url': item.product.main_image.url if item.product.main_image else None
        })

    # 4. CONTEXT SETUP
    context = {
        'draft': draft,
        'order_id': draft.id,
        'display_items': display_items,
        
        'show_results': True,

        'has_hidden_items': False 
    }
    
    return render(request, "MAIN/order_draft/order_eligibility.html", context)
    
@login_required(login_url='/login/')
def handle_eligibility_failure(request, order_id):
    """
    Handles the Resolution Actions (POST) and displays the Error Page (GET).
    """
    customer = get_or_create_customer_profile(request.user)
    draft = get_object_or_404(DraftOrder, id=order_id, customer=customer)
    
    # ====================================================
    # 1. HANDLE ACTION BUTTONS (POST)
    # ====================================================
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # --- ACTION A: SWITCH TO STANDARD ---
        if action == 'proceed_standard_current':
            with transaction.atomic():
                draft.delivery_type = 'standard_delivery'
                draft.status = 'pending' # Reset status so it doesn't show error
                draft.save()
            
            messages.success(request, "Switched to Standard Delivery. You can now proceed.")
            # Redirect to payment immediately since Standard always passes
            return redirect('proceed_to_checkout', draft_id=draft.id)

        # --- ACTION C: FIX IN EDITOR ---
        elif action == 'cancel':
            return redirect('order_edit_form', draft_id=draft.id)

    # ====================================================
    # 2. RENDER ERROR PAGE (GET)
    # ====================================================
    
    # --- POPULATE DISPLAY ITEMS (Fixes the "Empty Table" bug) ---
    display_items = []
    for item in draft.items.select_related('product', 'product__vendor').all():
        # Safe Location Lookup (Same logic as order_eligibility_view)
        loc_raw = getattr(item.product, 'pickup_location', None)
        location_display = "Unknown Location"
        if loc_raw:
            if isinstance(loc_raw, dict):
                location_display = loc_raw.get('address') or f"{loc_raw.get('latitude')}, {loc_raw.get('longitude')}"
            else:
                location_display = str(loc_raw)
        elif item.product.vendor:
            location_display = getattr(item.product.vendor, 'business_address', "Vendor HQ")

        display_items.append({
            'name': item.product.name,
            'product_id': item.product.id,
            'delivery_display': draft.get_delivery_type_display(),
            'vendor': item.product.vendor.business_name if item.product.vendor else "Luxa Vendor",
            'location': location_display,
            'qty': item.quantity,
            'price': item.product.price,
            'image_url': item.product.main_image.url if item.product.main_image else None
        })

    # Retrieve errors
    # Note: We re-run the engine quickly to ensure metadata is fresh for the template
    # or grab from session if you prefer. Re-running is safer for "Split" logic visibility.
    
    context = {
        'draft': draft,
        'order_id': draft.id,
        'display_items': display_items, # <--- Added this!
        
        # Engine Results for the Template
        'show_results': True,
    }
    
    return render(request, "MAIN/order_draft/order_eligibility.html", context)

@login_required(login_url='/login/')
def order_dispatch_prompt(request, draft_id):
    """
    Interstitial: [Start Delivery] vs [Save for Later]
    """
    customer = get_or_create_customer_profile(request.user)
    draft = get_object_or_404(DraftOrder, id=draft_id, customer=customer)
    
    if request.method == 'POST':
        choice = request.POST.get('choice')

        # User has made a choice, so we make the draft permanent
        if draft.status == 'temporary':
            draft.status = 'pending'
            draft.save()
        
        # CHOICE A: START ELIGIBILITY (Keep Cart for now, in case they fail and want to edit)
        if choice == 'now':
            return redirect('order_eligibility', order_id=draft.id)
            
        # CHOICE B: SAVE FOR LATER (Clear Cart & Notify)
        elif choice == 'later':
            # 1. Clear the Main Cart (Since draft is safe)
            try:
                # 1. Deduct Stock
                manage_draft_stock(draft, 'reserve')
                
                # 2. Clear Cart
                Cart.objects.filter(customer=customer).first().items.all().delete()
                
                messages.success(request, "Order saved! Items reserved for 48 hours.")
                return redirect('saved_orders_list')
                
            except ValueError as e:
                # If stock ran out while they were deciding
                messages.error(request, str(e))
                return redirect('cart')
            
    return render(request, "MAIN/order_draft/order_dispatch_prompt.html", {'draft': draft})

@login_required(login_url='/login/')
def delete_draft(request, draft_id):
    customer = get_or_create_customer_profile(request.user)
    draft = get_object_or_404(DraftOrder, id=draft_id, customer=customer)
    
    # Return stock before deleting
    manage_draft_stock(draft, 'release')

    draft.delete()
    messages.success(request, "Draft deleted successfully.")
    return redirect('saved_orders_list')

# Delivery PIN Setup View
@login_required
def setup_delivery_pin(request):
    """Page for the customer to create their PIN from the checkout flow."""
    # if hasattr(request.user.customer_profile, 'delivery_pin'):
    #     # If they already have a delivery PIN, redirect them away
    #     return redirect('change_delivery_pin')
    
    customer = request.user.customer_profile

    if request.method == 'POST':
        pin = request.POST.get('pin')
        confirm_pin = request.POST.get('confirm_pin')

        if not pin or len(pin) != 4 or not pin.isdigit():
            messages.error(request, "PIN must be exactly 4 digits.")
        elif pin != confirm_pin:
            messages.error(request, "PINs do not match.")
        else:
            # Set the PIN
            customer.set_delivery_pin(pin)
            # Render a simple template that tells them to close the tab
            return render(request, 'MAIN/order_pin_system/pin_success_close.html')

    return render(request, 'MAIN/order_pin_system/setup_pin.html')

def change_delivery_pin(request):
    """Page for the customer to change their existing delivery PIN."""
    if not hasattr(request.user.customer_profile, 'delivery_pin'):
        # If they don't have a PIN yet, redirect them to setup
        return redirect('setup_delivery_pin')
    
    customer = request.user.customer_profile

    if request.method == 'POST':
        current_pin = request.POST.get('current_pin')
        new_pin = request.POST.get('new_pin')
        confirm_new_pin = request.POST.get('confirm_new_pin')

        if not customer.check_delivery_pin(current_pin):
            messages.error(request, "Current PIN is incorrect.")
        elif not new_pin or len(new_pin) != 4 or not new_pin.isdigit():
            messages.error(request, "New PIN must be exactly 4 digits.")
        elif new_pin != confirm_new_pin:
            messages.error(request, "New PINs do not match.")
        else:
            # Update the PIN
            customer.set_delivery_pin(new_pin)
            messages.success(request, "Delivery PIN updated successfully.")

    return render(request, 'MAIN/order_pin_system/change_pin.html')

@login_required
@require_POST
def request_delivery_pin_reset(request):
    """Generates a secure token and sends the PIN reset email."""
    customer = request.user.customer_profile
    recipient_email = customer.email or request.user.email
    
    signer = TimestampSigner()
    # Sign the customer's ID to create a unique, verifiable token
    token = signer.sign(str(customer.id))
    
    reset_url = request.build_absolute_uri(reverse('reset_delivery_pin', args=[token]))
    
    try:
        send_mail(
            subject="Reset Your Delivery PIN - Luxa",
            message=(
                f"Hello {customer.first_name},\n\n"
                f"You requested to reset your Delivery PIN. Click the link below to set a new one. "
                f"For your security, this link expires in 1 hour.\n\n"
                f"{reset_url}\n\n"
                f"If you did not request this, please ignore this email.\n\n"
                f"Best regards,\nThe Luxa Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False
        )
        messages.success(request, f"A PIN reset link has been sent to {recipient_email}.")
    except Exception as e:
        messages.error(request, "Failed to send reset email. Please try again later.")
    
    return redirect('change_delivery_pin')

@login_required
def reset_delivery_pin(request, token):
    """Validates the token and allows the user to set a new PIN without the old one."""
    signer = TimestampSigner()
    
    try:
        # Token is valid for 1 hour (3600 seconds)
        customer_id = signer.unsign(token, max_age=3600)
    except SignatureExpired:
        messages.error(request, "The reset link has expired. Please request a new one.")
        return redirect('change_delivery_pin')
    except BadSignature:
        messages.error(request, "Invalid reset link.")
        return redirect('change_delivery_pin')
        
    customer = request.user.customer_profile
    
    # Security check: Ensure the token belongs to the logged-in user
    if str(customer.id) != str(customer_id):
        messages.error(request, "Unauthorized request.")
        return redirect('index')

    if request.method == 'POST':
        new_pin = request.POST.get('new_pin')
        confirm_new_pin = request.POST.get('confirm_new_pin')
        
        if not new_pin or len(new_pin) != 4 or not new_pin.isdigit():
            messages.error(request, "New PIN must be exactly 4 digits.")
        elif new_pin != confirm_new_pin:
            messages.error(request, "PINs do not match.")
        else:
            customer.set_delivery_pin(new_pin)
            messages.success(request, "Your Delivery PIN has been successfully reset!")
            return redirect('editprofile')
            
    return render(request, 'MAIN/order_pin_system/reset_pin.html')
