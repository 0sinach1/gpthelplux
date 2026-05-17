from django.apps import apps
from django.db import models, IntegrityError, transaction
from django.urls import reverse
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, MinValueValidator
from django.utils.text import slugify
from decimal import Decimal
from datetime import date
import uuid
from django.utils import timezone

from couriers.models import Courier

# Validators of media files
def validate_video_file(value):
    if not value.name.endswith(('.mp4', '.mov', '.avi')):
        raise ValidationError('Only .mp4, .mov, or .avi files are allowed.')
    
def validate_video_size(value):
    max_size_mb = 50 
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Video file too large. Maximum size allowed is {max_size_mb} MB.")
    
def validate_photo_file(value):
    if not value.name.endswith(('.png', '.jpg', '.jpeg')):
        raise ValidationError('Only .jpg and .png files are allowed!')
    
def validate_photo_size(value):
    max_size_mb = 2 
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Photo file too large. Maximum size allowed is {max_size_mb} MB.")

# Create your models here.

def validate_iso_4217_currency_code(value):
    """Validator for ISO 4217 currency codes (3-letter uppercase)
    
    Validates format: exactly 3 uppercase letters. The choices field restricts
    available options in forms, but this validator ensures data integrity.
    Rejects empty strings and None values.
    """
    if value is None or (isinstance(value, str) and len(value.strip()) == 0):
        raise ValidationError('Currency code is required.')
    if not isinstance(value, str) or len(value) != 3:
        raise ValidationError('Currency code must be exactly 3 characters (ISO 4217 format).')
    if not value.isalpha() or not value.isupper():
        raise ValidationError('Currency code must be 3 uppercase letters (e.g., USD, EUR, NGN).')

# Vendor model
class Vendor(models.Model):
    """Model representing a vendor/seller in the ecommerce platform"""

    BUSINESS_TYPE_CHOICES = [
        ('registered', 'Registered Business'),
        ('individual', 'Individual Business'),
    ]

    CATEGORY_CHOICES = [
        ('fashion', 'Fashion'),
        ('electronics', 'Electronics'),
        ('groceries', 'Groceries'),
        ('beauty', 'Beauty & Health'),
        ('home', 'Home & Living'),
        ('others', 'Others'),
    ]
    
    # Common ISO 4217 currency codes for choices (most commonly used)
    CURRENCY_CODE_CHOICES = [
        ('USD', 'USD - US Dollar'),
        ('EUR', 'EUR - Euro'),
        ('GBP', 'GBP - British Pound'),
        ('NGN', 'NGN - Nigerian Naira'),
        ('JPY', 'JPY - Japanese Yen'),
        ('AUD', 'AUD - Australian Dollar'),
        ('CAD', 'CAD - Canadian Dollar'),
        ('CHF', 'CHF - Swiss Franc'),
        ('CNY', 'CNY - Chinese Yuan'),
        ('INR', 'INR - Indian Rupee'),
        ('ZAR', 'ZAR - South African Rand'),
        ('MXN', 'MXN - Mexican Peso'),
        ('SGD', 'SGD - Singapore Dollar'),
        ('HKD', 'HKD - Hong Kong Dollar'),
        ('AED', 'AED - UAE Dirham'),
        ('SAR', 'SAR - Saudi Riyal'),
        ('GHS', 'GHS - Ghanaian Cedi'),
        ('KES', 'KES - Kenyan Shilling'),
        ('XAF', 'XAF - Central African CFA Franc'),
        ('XOF', 'XOF - West African CFA Franc'),
    ]
    
    # Basic vendor information
    business_name = models.CharField(max_length=200, unique=True, help_text="Must match NIN and Bank records")
    contact_person = models.CharField(max_length=100, help_text="Contact name for customers")
    official_email = models.EmailField(unique=True, help_text="Please use a business or official email")
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
    official_phone = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    selling_category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, null=True, blank=True)
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPE_CHOICES, default='individual')
    instagramlink = models.CharField(max_length=100, help_text="Get the link of your instagram page and paste it here.", default="Instagram profile link")
    is_luxa_insider = models.BooleanField(default=False, help_text="Is this vendor a Luxa Insider?")
    warrantyinfo = models.TextField(
        blank=True, 
        null=True, 
        help_text="Detailed warranty, refund, and return policy information."
    )
    
    # Business details
    business_license = models.CharField(max_length=100, unique=True, blank=True, null=True, help_text="Input Your National Indentification Number or Taxpayer Identification number")
    tax_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    legal_document = models.FileField(upload_to='vendor_documents/', blank=True, null=True)
    
    # Visual representation
    image = models.ImageField(upload_to='vendors/', blank=True, null=True, help_text="Vendor logo or profile image", validators=[validate_photo_size, validate_photo_file])
    
    # Address information
    business_address = models.CharField(max_length=200)
    delivery_location = models.JSONField(blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='Nigeria')
    
    # Currency settings
    # currency_code is the authoritative source for financial operations (ISO 4217 format)
    currency_code = models.CharField(
        max_length=3,
        default='NGN',
        choices=CURRENCY_CODE_CHOICES,
        validators=[validate_iso_4217_currency_code],
        help_text="ISO 4217 currency code (e.g., USD, EUR, NGN). This is the authoritative currency for transactions and pricing."
    )
    
    # Business status and verification
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    verification_date = models.DateTimeField(blank=True, null=True)

    # --- NEW: Sales Tracking ---
    total_sales = models.PositiveIntegerField(
        default=0, 
        help_text="Total number of completed sales. Admins can manually reset this to 0."
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # User account (one-to-one relationship with Django User)
    user_account = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor_profile')
    
    class Meta:
        ordering = ['business_name']
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'
    
    def __str__(self):
        return self.business_name
    
    @property
    def currency_symbol(self):
        """Get currency symbol derived from currency_code
        
        This is a computed property, not a stored field. The symbol is always
        derived from currency_code to ensure data consistency.
        """
        if self.currency_code:
            return self._get_symbol_from_code()
        return 'NGN₦'  # Default fallback
    
    def get_currency_display_info(self):
        """Get currency code and symbol for display
        
        Returns a dictionary with 'code' and 'symbol' keys.
        Always returns a valid dict, never None.
        """
        return {
            'code': self.currency_code or 'USD',
            'symbol': self.currency_symbol,
        }
    
    def _get_symbol_from_code(self):
        """Get currency symbol from ISO 4217 code (fallback mapping)
        
        This method provides the canonical symbol mapping for each currency code.
        Symbols are disambiguated to avoid conflicts (e.g., US$ for USD, MX$ for MXN).
        """
        symbol_map = {
            'USD': 'US$', 'EUR': '€', 'GBP': '£', 'NGN': '₦', 'JPY': 'JP¥',
            'AUD': 'A$', 'CAD': 'C$', 'CHF': 'CHF', 'CNY': 'CN¥', 'INR': '₹',
            'ZAR': 'R', 'MXN': 'MX$', 'SGD': 'S$', 'HKD': 'HK$', 'AED': 'د.إ',
            'SAR': '﷼', 'GHS': '₵', 'KES': 'KSh', 'XAF': 'FCFA', 'XOF': 'CFA',
        }
        return symbol_map.get(self.currency_code, self.currency_code)

# Customer model
class Customer(models.Model):
    """Model representing a customer in the ecommerce platform"""

    GENDER_CHOICES = [
        ('male', 'male'),
        ('female', 'female'),
    ]

    class socials(models.TextChoices):
        INSTAGRAM = 'INSTAGRAM', 'Instagram'
        # FACEBOOK = 'FACEBOOK', 'Facebook'
    
    # Personal information
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    username = models.CharField(max_length=50, default='yourusername')
    email = models.EmailField(unique=True)
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True, help_text="WhatsApp number is preferrable",)
    date_of_birth = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='customer_profiles/', blank=True, null=True, help_text="Customer profile picture", validators=[validate_photo_size, validate_photo_file])
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="male")
    social_media_platform = models.CharField(max_length=20, choices=socials.choices, null=True, blank=True)
    social_media_handle = models.CharField(max_length=100, blank=True, null=True, help_text="Your username on the selected social media platform (e.g., @yourhandle)")
    
    # Address information
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Nigeria')
    label = models.CharField(max_length=50, blank=True, null=True, help_text="Label for this address (e.g., Home, Work)")  

    # NEW: Store extra addresses as a list of dictionaries without a new model
    additional_addresses = models.JSONField(
        default=list, 
        blank=True, 
        help_text="Stores a list of extra address dictionaries"
    )

    # PROMO DISCOUNTS FOR SPECIAL USERS
    promo_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))], help_text="Percentage discount for this customer (e.g., 10.00 for 10% off). Admins can set this manually.")
    promo_daily_total = models.PositiveIntegerField(default=0, help_text="The max number of courions the customer is allowed to use his discount on.")
    promo_daily_counter = models.PositiveIntegerField(default=0, help_text="Tracks how many times the promo has been used today. Resets daily at midnight.")

    last_promo_date = models.DateField(null=True, blank=True)
    
    # Customer preferences
    newsletter_subscription = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Account status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(blank=True, null=True)
    has_seen_welcome = models.BooleanField(default=False, help_text="Has the vendor seen the dashboard welcome popup?")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(blank=True, null=True)
    
    # User account (one-to-one relationship with Django User)
    user_account = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')

    # Luxa Craving University Profile (optional one-to-one relationship)
    university_profile = models.OneToOneField(
        'luxa_crave.University_Profile', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='customer_profile'
    )

    # NEW: Delivery Authentication PIN - It is separate from the escrow pin!
    delivery_pin = models.CharField(
        max_length=128, # Length is 128 to allow for password hashing
        blank=True, 
        null=True, 
        help_text="Secure PIN for delivery verification"
    )
    
    def set_delivery_pin(self, raw_pin):
        from django.contrib.auth.hashers import make_password
        self.delivery_pin = make_password(raw_pin)
        self.save()

    def check_delivery_pin(self, raw_pin):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_pin, self.delivery_pin)
    
    # =========================================================
    # NEW HELPER METHODS FOR ADDRESS MANAGEMENT
    # =========================================================
    
    def get_all_addresses(self):
        """
        Returns a combined list of the primary address and all additional addresses.
        Useful for rendering lists in templates.
        """
        addresses = []
        primary_label = 'Address' # Fallback

        # 1. Safely extract the primary label from our hidden metadata dictionary
        if isinstance(self.additional_addresses, list):
            for item in self.additional_addresses:
                if item.get('_meta'):
                    primary_label = item.get('primary_label', 'Address')
                    break
        
        # 1. Grab the primary address from the hardcoded fields
        if self.address_line1 or self.city:
            addresses.append({
                'id': 'primary',
                'is_primary': True,
                'address_line1': self.address_line1,
                'address_line2': self.address_line2,
                'city': self.city,
                'state': self.state,
                'postal_code': self.postal_code,
                'country': self.country,
                'label': primary_label,
            })
            
        # 2. Append all the extra addresses from the JSON array
        if isinstance(self.additional_addresses, list):
            for index, addr in enumerate(self.additional_addresses):
                if addr.get('_meta'):
                    continue
                
                addr_copy = addr.copy()
                addr_copy['id'] = index # Give it a temporary ID based on array index
                addr_copy['is_primary'] = False
                addresses.append(addr_copy)
                
        return addresses

    def add_extra_address(self, address_dict):
        """
        Appends a new address dictionary to the JSONField.
        Expected format: {'address_line1': '...', 'city': '...', ...}
        """
        if not isinstance(self.additional_addresses, list):
            self.additional_addresses = []
            
        self.additional_addresses.append(address_dict)
        self.save(update_fields=['additional_addresses'])

    def remove_extra_address(self, index):
        """Removes an extra address by its list index."""
        if isinstance(self.additional_addresses, list) and 0 <= index < len(self.additional_addresses):
            self.additional_addresses.pop(index)
            self.save(update_fields=['additional_addresses'])
            return True
        return False
    
    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

# KYC model for customers
class KYCVerification(models.Model):
    class IDType(models.TextChoices):
        NIN = 'NIN', 'National Identity Number (NIN)'
        PASSPORT = 'PASSPORT', 'International Passport'
        DRIVERS_LICENSE = 'DRIVERS_LICENSE', 'Driver\'s License'
        VOTERS_CARD = 'VOTERS_CARD', 'Voter\'s Card'
        LMU_ID_CARD = 'LMU_IDCARD', 'LMU ID Card'

    class socials(models.TextChoices):
        INSTAGRAM = 'INSTAGRAM', 'Instagram'
        # FACEBOOK = 'FACEBOOK', 'Facebook'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        APPROVED = 'APPROVED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'

    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='kyc_profile')
    full_name_on_id = models.CharField(max_length=200)
    social_media_platform = models.CharField(max_length=20, choices=socials.choices, null=True, blank=True)
    social_media_handle = models.CharField(max_length=100, blank=True, null=True, help_text="Your username on the selected social media platform (e.g., @yourhandle)")
    id_type = models.CharField(max_length=50, choices=IDType.choices)
    id_number = models.CharField(max_length=50)
    
    # Secure Image Uploads
    document_front = models.FileField(upload_to='kyc_docs/front/')
    document_back = models.FileField(upload_to='kyc_docs/back/', null=True, blank=True)
    selfie = models.ImageField(upload_to='kyc_docs/selfies/', help_text="A photo of you holding your ID")
    
    # Admin Handling
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, null=True, help_text="Why was this rejected?")
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='kyc_reviews')

    def __str__(self):
        return f"{self.customer.user_account.username} - {self.get_status_display()}"

# Category model
class Category(models.Model):
    """Model representing product categories in the ecommerce platform"""
    
    # Category information
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, help_text="URL-friendly version of the name")
    description = models.TextField(blank=True, help_text="Brief description of the category")
    
    # Category hierarchy
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='subcategories')
    
    # Visual representation
    image = models.ImageField(upload_to='categories/', blank=True, null=True, help_text="Category image/icon")
    
    # Category status
    is_active = models.BooleanField(default=True)

    is_featured = models.BooleanField(default=False, help_text="Show this category prominently on the homepage")
    
    # SEO fields
    meta_title = models.CharField(max_length=200, blank=True, help_text="SEO title for this category")
    meta_description = models.TextField(blank=True, help_text="SEO description for this category")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ('slug', 'parent',) 
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'


    def __str__(self):
        # This helps in the admin interface to see the hierarchy
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name


      # 🔒 VALIDATION
    def clean(self):
        if self.parent:
            if self.parent == self:
                raise ValidationError("A category cannot be its own parent.")

            ancestor = self.parent
            while ancestor:
                if ancestor == self:
                    raise ValidationError(
                        "Circular category hierarchy detected."
                    )
                ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        self.full_clean()  # forces clean() to run
        super().save(*args, **kwargs)
           
    
    def get_absolute_url(self):    
        if self.parent:
            return reverse(
                'subcategory_detail',
                kwargs={
                    'parent_slug': self.parent.slug,
                    'slug': self.slug
                }
            )
        return reverse('category_detail', kwargs={'slug': self.slug})

    
    @property
    def has_children(self):
        """Check if this category has subcategories"""
        return self.subcategories.exists()
    
    def get_all_subcategories(self):
        """Get all subcategories recursively"""
        subcategories = []
        for subcat in self.subcategories.all():
            subcategories.append(subcat)
            subcategories.extend(subcat.get_all_subcategories())
        return subcategories

# Validators for 3D model files
def validate_3d_model_file(value):
    """Validator for 3D model files - only allows .glb and .gltf extensions"""
    if value:
        allowed_extensions = ('.glb', '.gltf')
        if not value.name.lower().endswith(allowed_extensions):
            raise ValidationError('Only .glb and .gltf files are allowed for 3D models.')

# Product model with multi-currency pricing support
def validate_3d_model_size(value):
    """Validator for 3D model file size - enforces maximum size limit"""
    if value:
        max_size_mb = 30
        if value.size > max_size_mb * 1024 * 1024:
            raise ValidationError(f"3D model file too large. Maximum size allowed is {max_size_mb} MB.")

# Product model
class Product(models.Model):
    """Model representing a product in the ecommerce platform
    
    Products support multi-currency pricing. The price is stored in the vendor's
    currency (vendor.currency_code), which is the authoritative source for financial
    operations. Currency conversion should be performed at the transaction level if needed.
    """
    
    # Basic product information
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True, help_text="URL-friendly version of the name (auto-generated if not provided)")
    description = models.TextField(help_text="Detailed product description. **this is bold** *this is italics* ")
    sku = models.CharField(max_length=50, unique=True, help_text="Stock Keeping Unit")
    features = models.TextField(help_text="Provide a detailed Specification of what the product is like. Size, Color etc. Must be written in an ordered manner. **this is bold** *this is italics*", default="Input Features")
    includeditems = models.TextField(help_text="What the package comes with on delivery. Must be written in an ordered manner. **this is bold** *this is italics*", default="Input included items")
    
    # Relationships
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    
    # Pricing
    # Price is stored in the vendor's currency (vendor.currency_code is authoritative)
    # For multi-currency support, prices are in the vendor's native currency
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Product price in vendor's currency (vendor.currency_code). Use vendor.get_currency_display_info() for formatting."
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Original price for sale items (in vendor's currency)"
    )
    
    # Images
    main_image = models.ImageField(upload_to='products/', help_text="Main product image")
    
    # 3D Model (for 3D product preview)
    model_3d_file = models.FileField(
        upload_to='products/3d_models/',
        blank=True,
        null=True,
        validators=[validate_3d_model_file, validate_3d_model_size],
        help_text="3D model file for preview (GLB, GLTF only, max 20MB)"
    )
    
    # Inventory
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)], help_text="Available stock quantity")
    is_available = models.BooleanField(default=True)
    
    # Product variants (deprecated - use ProductVariant model instead)
    # Kept for backward compatibility during migration
    available_colors = models.CharField(max_length=500, blank=True, help_text="[DEPRECATED] Use ProductVariant model. Comma-separated list of available colors")
    available_sizes = models.CharField(max_length=500, blank=True, help_text="[DEPRECATED] Use ProductVariant model. Comma-separated list of available sizes")
    
    def get_available_colors(self):
        """Get available colors from ProductVariant model"""
        return self.variants.filter(variant_type='color', is_available=True).values_list('variant_value', flat=True)
    
    def get_available_sizes(self):
        """Get available sizes from ProductVariant model"""
        return self.variants.filter(variant_type='size', is_available=True).values_list('variant_value', flat=True)
    
    #vendor-entered variant field
    vendor_variants = models.JSONField(
        blank=True,
        null=True,
        help_text="Vendor-entered variants e.g {'Color': ['Red', 'Blue'], 'Size': ['S', 'M']}"
    )

    # Status and metadata
    is_approved = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False, help_text="Show this product prominently")
    is_active = models.BooleanField(default=False)
    has_variants = models.BooleanField(default=False, help_text="Does this product have variants (colors, sizes, etc.)?")
    is_color = models.BooleanField(default=False, help_text="Choose whether this product has color variants for 3D mesh customization.")
    # pickup_location = models.JSONField(blank=True, null=True, help_text="Geo-location for product pickup (if applicable)")
    
    # SEO
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('product_detail', kwargs={'slug': self.slug})
    
    @property
    def in_stock(self):
        """Check if product is in stock"""
        return self.stock_quantity > 0 and self.is_available
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage if compare_at_price exists"""
        if self.compare_at_price and self.compare_at_price > self.price:
            return int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0
    


    def get_price_display(self):
        """Get formatted price with currency symbol from vendor
        
        Simple formatting for early users/testers. Currency formatting can be
        enhanced later when needed.
        """
        if not self.vendor:
            # Fallback if vendor is missing
            from .constants import DEFAULT_CURRENCY_SYMBOL
            currency_symbol = DEFAULT_CURRENCY_SYMBOL
        else:
            currency_info = self.vendor.get_currency_display_info()
            currency_symbol = currency_info.get('symbol', 'US$') if isinstance(currency_info, dict) else 'US$'
        
        return f"{currency_symbol}{self.price}"
    
    def get_currency_code(self):
        """Get the currency code for this product (from vendor)"""
        if not self.vendor:
            from .constants import DEFAULT_CURRENCY_CODE
            return DEFAULT_CURRENCY_CODE
        return self.vendor.currency_code or 'USD'
    
    def clean(self):
        if self.category:
            # Prevent assigning product to parent category
            if self.category.subcategories.exists():
                raise ValidationError({
                    'category': 'Products can only be assigned to subcategories, not parent categories.'
                })
        
    def save(self, *args, **kwargs):
        self.full_clean()

        """Override save to auto-generate slug from name if not provided
        
        Includes race-condition protection: if IntegrityError occurs due to
        slug collision, regenerates slug and retries up to 5 times.
        """
        if not self.slug:
            # Generate slug from name
            base_slug = slugify(self.name)
            # Reserve 10 chars for counter suffix (supports up to "-999999999")
            max_base_length = 190
            slug = base_slug[:max_base_length]
            
            # Ensure uniqueness (pre-check to avoid unnecessary retries)
            original_slug = slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{original_slug}-{counter}"
                if len(slug) > 200:
                    # If counter makes it too long, truncate base further
                    counter_suffix = f"-{counter}"
                    slug = original_slug[:200-len(counter_suffix)] + counter_suffix
                counter += 1
            
            self.slug = slug
        
        # Race-condition protection: retry on IntegrityError
        max_attempts = 5
        attempts = 0
        last_error = None
        
        while attempts < max_attempts:
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                break  # Success, exit loop
            except IntegrityError as e:
                last_error = e
                # Check if error is related to slug uniqueness
                error_str = str(e).lower()
                if 'slug' in error_str:
                    # Regenerate slug with uniqueness check and retry
                    base_slug = slugify(self.name)
                    max_base_length = 190
                    original_slug = base_slug[:max_base_length]
                    # Start counter from attempts + 1 to ensure different slug each retry
                    counter = attempts + 1
                    slug = f"{original_slug}-{counter}"
                    if len(slug) > 200:
                        counter_suffix = f"-{counter}"
                        slug = original_slug[:200-len(counter_suffix)] + counter_suffix
                    
                    # Check if this slug already exists (avoid unnecessary retry)
                    while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                        counter += 1
                        slug = f"{original_slug}-{counter}"
                        if len(slug) > 200:
                            counter_suffix = f"-{counter}"
                            slug = original_slug[:200-len(counter_suffix)] + counter_suffix
                    
                    self.slug = slug
                    attempts += 1
                else:
                    # Not a slug-related error, re-raise immediately
                    raise
        else:
            # All attempts exhausted, re-raise last error
            if last_error:
                raise last_error
            raise IntegrityError("Failed to save product after multiple attempts due to slug collision")

#product target mesh model
class ProductTargetMesh(models.Model):
    """
    Represents a mesh or part of a product that can have colors.
    Example: 'handle', 'strap', 'button'.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='target_meshes'
    )

    name = models.CharField(max_length=50)

    class Meta:
        unique_together = ('product', 'name')

    def __str__(self):
        return f"{self.name} ({self.product.name})"

#product color model
class ProductColor(models.Model):
    """
    Represents a color option for a product mesh.
    """
    target_mesh = models.ForeignKey(
        ProductTargetMesh,
        on_delete=models.CASCADE,
        related_name='colors'
    )
    name = models.CharField(max_length=50, default="mesh-color")
    color_hex = models.CharField(
        max_length=7,
        validators=[
            RegexValidator(
                regex=r'^#[0-9A-Fa-f]{6}$',
                message='Enter a valid hex color (e.g., #FF5733).'
            )
        ]
    )

    class Meta:
        unique_together = ('target_mesh', 'color_hex')

    def __str__(self):
        return f"{self.color_hex} ({self.target_mesh.name})"

#product image model
class ProductImage(models.Model):
    """Model for storing additional product images"""
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    orthographicfront = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size],  
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True
    )
    orthographicleft = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size],  
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True
    )
    orthographicright = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size],  
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True
    )
    orthographicback = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size],  
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True
    )
    orthographictop = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size],  
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True
    )
    orthographicbottom = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size], 
        help_text="Upload a <2mb orthographic image", 
        null=True, 
        blank=True
    )
    perspectivefront = models.ImageField(
        upload_to='products/imagesfor3d', 
        validators=[validate_photo_file, validate_photo_size],  
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True
    )
    perspectiveback = models.ImageField(
        upload_to='products/imagesfor3d',
        validators=[validate_photo_file, validate_photo_size], 
        help_text="Upload a <2mb perspective image",
        null=True, 
        blank=True,
    )
    video360 = models.FileField(
        upload_to='productvideos/', 
        validators=[validate_video_file, validate_video_size],
        help_text="Upload a 360° product video (max 50MB)",
        null=True, 
        blank=True,
    )

    info_text = models.CharField(max_length=200, blank=True, help_text="Info text for accessibility")
    order = models.IntegerField(default=0, help_text="Display order")
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
    
    def __str__(self):
        if self.product:
            return f"{self.product.name} - Image {self.order}"
        return f"Image {self.order} (No product)"

# Processed Product Media model
class ProcessedProductMedia(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='processed_media')

    # Processed images you manually upload after editing
    final_main_image = models.ImageField(
        upload_to='products/processed/',
        null=True, blank=True,
        help_text="The final main image shown on the site"
    )

    final_thumbimg1 = models.ImageField(upload_to='products/processed/', null=True, blank=True)
    final_thumbimg2 = models.ImageField(upload_to='products/processed/', null=True, blank=True)
    final_thumbimg3 = models.ImageField(upload_to='products/processed/', null=True, blank=True)
    final_thumbimg4 = models.ImageField(upload_to='products/processed/', null=True, blank=True)
    final_thumbimg5 = models.ImageField(upload_to='products/processed/', null=True, blank=True)

    def __str__(self):
        return f"Processed media for {self.product.name}"
    
    def thumbnails(self):
        return [
            self.final_thumbimg1,
            self.final_thumbimg2,
            self.final_thumbimg3,
            self.final_thumbimg4,
            self.final_thumbimg5,
        ]

# MasterOrder model For customer view
class MasterOrder(models.Model):
    """
    The 'Receipt' for the Customer. 
    Aggregates multiple Vendor Orders into one single transaction reference.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The ID the customer sees (e.g. ORD-2024-8239)
    public_order_id = models.CharField(max_length=50, unique=True)
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='master_orders')
    is_kyc_verified = models.BooleanField(default=False, help_text="True if the recipient name matches their Govt ID")
    
    # Financial Aggregates
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'In Transit'), # or 'in_transit'
        ('awaiting_validation', 'Awaiting Validation'), 
        ('delivered', 'Delivered'),
        ('pending_cancellation', 'Pending Cancellation'), 
        ('cancelled', 'Cancelled'),
    ]
    
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='pending')

    # --- TIMELINE FIELDS ---
    processed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True) # Step right before delivery
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        # --- AUTO-STAMP THE TIMELINE ON STATUS CHANGE ---
        if self.pk:
            old_order = MasterOrder.objects.filter(pk=self.pk).first()
            if old_order and old_order.status != self.status:
                now = timezone.now()
                
                if self.status == 'processing' and not self.processed_at:
                    self.processed_at = now
                elif self.status in ['shipped', 'in_transit'] and not self.shipped_at:
                    self.shipped_at = now
                elif self.status == 'awaiting_validation' and not self.validated_at:
                    self.validated_at = now
                elif self.status == 'delivered' and not self.delivered_at:
                    self.delivered_at = now
        
        super().save(*args, **kwargs)

        # 2. Sync to LUXA (Both are in MAIN app)
        try:
            luxa = self.synchronized_order.first()
            
            if luxa:
                old_status = luxa.status
                
                # --- EXPLICIT STATUS MAPPING ---
                # Left Side: MasterOrder Status | Right Side: LUXAOrder Status
                STATUS_MAP = {
                    # The Courier is "Done" when it's awaiting validation, delivered, or cancelled
                    'awaiting_validation': 'completed',
                    'delivered':           'completed',
                    'cancelled':           'completed', 
                    
                    # Transit statuses map 1:1
                    'shipped':             'shipped',
                    'pending_cancellation':'pending_cancellation',
                }

                # Only apply if we have a valid mapping
                if self.status in STATUS_MAP:
                    target_status = STATUS_MAP[self.status]
                    
                    # Prevent redundant saves
                    if luxa.status != target_status:
                        luxa.status = target_status
                        print(f"DEBUG: Internal Sync {self.public_order_id} -> {luxa.order_id} to {luxa.status}")
                        luxa.save() # Triggers Batch Burn
                
            else:
                # Optional: Silent pass if no courier assigned yet
                pass
                
        except Exception as e:
            print(f"DEBUG: Syncing Failed - {str(e)}")
    
    
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_status = models.CharField(max_length=20, default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)

    # Inside class MasterOrder(models.Model):

    


# Order and OrderItem models
class Order(models.Model):
    """Model representing a customer order"""
    
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    # Order identification
    order_number = models.CharField(max_length=50, unique=True, help_text="Unique order identifier")
    
    # Relationships
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='orders')
    
    # Order details
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    is_kyc_verified = models.BooleanField(default=False, help_text="True if the recipient name matches their Govt ID")

    # Delivery type [cms feature]
    delivery_type = models.CharField(
        max_length=20,
        choices=[('standard_delivery', 'Standard'), ('same_day_delivery', 'Same Day')],
        null=True, # Important: nullable for old orders
        blank=True
    )
    
    # Payment information
    payment_method = models.CharField(max_length=50, default='quickteller', help_text="Payment method used")
    payment_transaction_id = models.CharField(max_length=200, blank=True, null=True, help_text="Payment transaction ID from payment gateway")

    # Track if the specific user has viewed the order details
    vendor_seen = models.BooleanField(default=False, help_text="Has the vendor viewed this order?")
    customer_seen = models.BooleanField(default=False, help_text="Customer creates the order, so default is True. Reset to False on status updates.")
    
    # Pricing (stored in vendor's currency)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    
    # Platform fees (Luxa delivery and service fees)
    delivery_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Delivery fee charged per vendor (default ₦250)"
    )
    luxa_cut_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Platform service fee percentage applied to this order"
    )
    luxa_cut_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Platform service fee amount deducted from vendor payout"
    )
    vendor_payout = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Final amount vendor receives after platform fees"
    )
    
    # Shipping information
    shipping_address = models.TextField(help_text="Full shipping address")
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100)
    shipping_postal_code = models.CharField(max_length=20)
    shipping_country = models.CharField(max_length=100)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shipped_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)

    # NEW LINK: Connects this vendor-shipment to the main receipt
    master_order = models.ForeignKey(
        MasterOrder, 
        on_delete=models.CASCADE, 
        related_name='sub_orders',
        null=True, 
        blank=True
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
    
    def __str__(self):
        return f"Order {self.order_number}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generate unique order number with collision handling
            import uuid
            
            max_attempts = 10
            attempts = 0
            
            while attempts < max_attempts:
                # Use 12 hex chars for better uniqueness (16^12 = ~281 trillion combinations)
                order_number = f"ORD-{uuid.uuid4().hex[:12].upper()}"
                
                # Check if this order_number already exists
                if not Order.objects.filter(order_number=order_number).exists():
                    self.order_number = order_number
                    break
                
                attempts += 1
            
            if not self.order_number:
                # If we exhausted all attempts, try one more time with full UUID
                # This should be extremely rare
                self.order_number = f"ORD-{uuid.uuid4().hex.upper()}"
                # Final check - if still exists, raise exception
                if Order.objects.filter(order_number=self.order_number).exists():
                    raise ValueError(
                        f"Unable to generate unique order number after {max_attempts} attempts. "
                        "Please try again or contact support."
                    )
        
        # Attempt save and catch IntegrityError as final safety net
        try:
            super().save(*args, **kwargs)
        except IntegrityError as e:
            if 'order_number' in str(e).lower():
                # If order_number collision occurred, regenerate and retry once
                import uuid
                self.order_number = f"ORD-{uuid.uuid4().hex[:12].upper()}"
                super().save(*args, **kwargs)
            else:
                raise
    
    @property
    def vendor_earnings(self):
        """Calculate vendor earnings (total minus platform fees)
        
        Returns vendor_payout if set, otherwise falls back to subtotal for
        backward compatibility with older orders.
        """
        if self.vendor_payout and self.vendor_payout > 0:
            return self.vendor_payout
        return self.subtotal

#  OrderItem model
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='order_items')
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    
    # NEW: Permanent record of the variants selected
    variants = models.ManyToManyField(
        'ProductVariant', 
        blank=True, 
        related_name='order_items'
    )
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def save(self, *args, **kwargs):
        self.subtotal = self.price * self.quantity
        super().save(*args, **kwargs)

    def get_variant_description(self):
        """
        Permanent record of what the user selected at checkout.
        """
        selected = self.variants.all()
        if not selected:
            return ""
        descriptions = [f"{v.variant_type.title()}: {v.variant_value}" for v in selected]
        return ", ".join(descriptions)

# Draft order for customers
class DraftOrder(models.Model):
    # Keep UUID for the draft itself (it's internal, so it's safe)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # ADAPTER 1: Point to your EXISTING Customer model
    # The database will store the Integer ID of the customer here.
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE, 
        related_name='draft_orders'
    )
    
    delivery_type = models.CharField(
        max_length=20,
        choices=[('standard_delivery', 'Standard'), ('same_day_delivery', 'Same Day')],
        default='standard_delivery'
    )
    status = models.CharField(max_length=50, default="awaiting_delivery_start")
    stock_reserved = models.BooleanField(default=False, help_text="Does the order reserve any products?")
    
    # ADAPTER 2: Change this to CharField or IntegerField
    # This stores the ID of a Main Order if you split it. 
    original_order_id = models.CharField(max_length=100, null=True, blank=True) 
    
    created_at = models.DateTimeField(auto_now_add=True)

class DraftOrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft_order = models.ForeignKey(DraftOrder, on_delete=models.CASCADE, related_name='items')
    
    # ADAPTER 3: Point to your EXISTING Product model
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    
    # THE BRIDGE: This JSON field saves us!
    # It doesn't care if you use "Attributes" or "Mesh Colors".
    # It just stores: {"Color": "Red", "Size": "M"}
    variation_choices = models.JSONField(default=dict) 
    quantity = models.PositiveIntegerField(default=1)
    
class EligibilityStagingArea(models.Model):
    """
    Optimized table for the decision engine logic.
    """
    # Order ID is a DraftOrder (UUID), so this stays UUIDField
    order_id = models.UUIDField(db_index=True)
    
    # CHANGED: Customer and Product in main app likely use Integer IDs. 
    # If your Main app uses Integer IDs, these must be IntegerField!
    customer_id = models.IntegerField(db_index=True) 
    product_id = models.IntegerField()
    
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['order_id', 'customer_id']),
        ]

class LUXAOrder(models.Model):
# --- INJECTED: Link to Draft ---
    order_source = models.ForeignKey(
        MasterOrder, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='synchronized_order'
    )


    LUXA_STATUS_CHOICES = [
        ('pending_assignment', 'Pending Assignment'),
        ('processing', 'Processing'),
        ('assigned', 'Assigned'),
        ('shipped', 'In Transit'),
        ('completed', 'Completed'), # This triggers the 'Batch Burn'
        ('pending_cancellation', 'Pending Cancellation'),
        ('dumped', 'Dumped'),        
        ('failed', 'Failed'),
    ]

    batch = models.ForeignKey(
        'couriers.DeliveryBatch', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='orders'
    )
    # This status is used by the Batch Burn logic
    status = models.CharField(max_length=30, 
                              choices=LUXA_STATUS_CHOICES, 
                              default='pending_assignment')
    





    
    
    # Core Identifiers
    order_id = models.CharField(max_length=100, primary_key=True) 
    customer_id = models.CharField(max_length=100)
    
    # Order Metadata
    delivery_type = models.CharField(max_length=20)
    same_day_eligibility = models.CharField(max_length=20, default="pending")  # Not to be shown used internally
    standard = models.CharField(max_length=20, default="pending")              # used internally not shown 
  
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00) # Added
    
    # The JSON Data Blocks
    # { "PROD_ID": {"name": "Alekhine", "price": "150.00", "total_qty": 3} }
    products = models.JSONField()            
    
    # { "PROD_ID": "VENDOR_DETAILS" }
    vendors = models.JSONField()             
    
    # { "PROD_ID": { "Variation 1": {"customization": {"Frame": "Gold"}, "qty": 1}, ... } }
    product_configurations = models.JSONField() 
    
    # { "PROD_ID": {"latitude": 0.0, "longitude": 0.0} }
    pickup_locations = models.JSONField()    
    
    # {"latitude": 0.0, "longitude": 0.0}
    delivery_location = models.JSONField()

    assigned_courier = models.ForeignKey(
        Courier, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_orders'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True) # Added to track sync changes
    # status



    @property
    def source_order(self):
        """Universal alias for the MasterOrder (Required by Courier View)"""
        return self.order_source

    @property
    def cancel_status_map(self):
        """Tells the view what the MasterOrder status should be on cancellation"""
        return 'pending_cancellation'
    
    @property
    def supports_proxy(self):
        """Enables the Seed Phrase/PIN verification logic for Standard orders"""
        return False
    
    
    @property
    def display_data(self):
        # --- SAFE DEFAULTS ---
        internal_id = self.order_id
        name = "Standard Customer"
        location = "Standard Delivery Address"
        avatar_url = None
        is_approved = False

        try:
            # order_source is the MasterOrder
            if self.order_source and self.order_source.customer:
                cust = self.order_source.customer
                
                # 1. Get the Name
                name = getattr(cust, 'full_name', "Standard Customer")

                # --- 2. UNIVERSAL KYC CHECK ---
            # Using the exact logic from the Campus network to ensure consistency
                if hasattr(cust, 'kyc_profile') and cust.kyc_profile:
                    is_approved = (cust.kyc_profile.status == 'APPROVED')

                # 2. Get Avatar
                if hasattr(cust, 'profile_picture') and cust.profile_picture:
                    avatar_url = cust.profile_picture.url

                # 3. Get the exact Delivery Address
                # Check the sub_orders linked to this MasterOrder
                sub_order = self.order_source.sub_orders.first()
                
                if sub_order and getattr(sub_order, 'shipping_address', None):
                    # Use the exact checkout shipping address
                    location = f"{sub_order.shipping_address}, {getattr(sub_order, 'shipping_city', '')}"
                elif hasattr(cust, 'address_line1') and cust.address_line1:
                    # Fallback to profile address
                    location = f"{cust.address_line1}, {getattr(cust, 'city', '')}"
        except Exception as e:
            # If anything fails, we still return the defaults instead of crashing
            print(f"Error in LUXAOrder display_data: {e}")

        return {
            'internal_id': internal_id, # Matches card button logic
            'customer_name': name,
            'delivery_location': location, # Changed from 'location' to match template
            'authorized_photo': avatar_url, # Matches card image logic
            'total': getattr(self, 'total_price', 0),
            'network': 'LUXA E-COMMERCE',
            "is_kyc_approved": is_approved
        }
    def save(self, *args, **kwargs):
        # 1. Save the LUXAOrder first
        super().save(*args, **kwargs)

        # 2. Force the Batch to re-evaluate
        if self.batch:
            print(f"DEBUG: LUXAOrder {self.order_id} saved as {self.status}. Triggering Batch {self.batch.batch_id}...")
            
            # Use the method you shared earlier
            success = self.batch.check_batch_burn()
            
            if success:
                print(f"DEBUG: SUCCESS! Batch {self.batch.batch_id} has been BURNED.")
            else:
                # This will tell us if it failed because an order is still 'shipped'
                print(f"DEBUG: Batch {self.batch.batch_id} is NOT ready to burn yet.")
    def __str__(self):
        return f"LUXA Sync: {self.order_id} ({self.get_status_display()})"

def lock_order(self):
        """Marks order as assigned as part of the Heartbeat Lock"""
        self.status = 'assigned'
        self.save()

# Cart models
class Cart(models.Model):
    """Model representing a shopping cart"""
    
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'
    
    def __str__(self):
        return f"Cart for {self.customer.full_name}"
    
    @property
    def total_items(self):
        """Get total number of items in cart"""
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0
    
    @property
    def total_price(self):
        """Calculate total price of all items in cart"""
        total = Decimal('0.00')
        for item in self.items.all():
            total += item.product.price * item.quantity
        return total

# ProductVariant model
class ProductVariant(models.Model):
    """Model representing product variants (colors, sizes, etc.)
    
    This model normalizes variant data and replaces the CSV string fields.
    Each variant has a type (e.g., 'color', 'size') and a value (e.g., 'Red', 'Large').
    """
    mesh_color_source = models.OneToOneField(
        'ProductColor', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='generated_variant',
        help_text="If this variant was auto-generated from a 3D mesh color"
    )
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    variant_type = models.CharField(
            max_length=50, 
            db_index=True,  
            help_text="Type of variant (e.g., 'Color', 'Size', 'Handle', 'Rims')"
        )    
    variant_value = models.CharField(max_length=100, help_text="Value of the variant (e.g., 'Red', 'Large')")
    is_available = models.BooleanField(default=True, help_text="Whether this variant is currently available")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['product', 'variant_type', 'variant_value']
        indexes = [
            models.Index(fields=['product', 'variant_type']),
            models.Index(fields=['product', 'is_available']),
        ]
        ordering = ['variant_type', 'variant_value']
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
    
    def __str__(self):
        return f"{self.product.name} - {self.variant_type}: {self.variant_value}"

# Product texture model
class Product3DTexture(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='textures_3d')
    # Optional: If you want to link a texture to a specific variant (e.g. "Blue" variant gets "Blue Fabric")
    variant = models.ForeignKey('ProductVariant', on_delete=models.SET_NULL, null=True, blank=True)
    
    name = models.CharField(max_length=50, help_text="e.g. 'Leather', 'Denim', 'Red Pattern'")
    texture_file = models.ImageField(upload_to='product_textures/')
    thumbnail = models.ImageField(upload_to='product_textures/thumbs/', null=True, blank=True, help_text="Small preview for the UI button")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

# ProductVariantImage model
class ProductVariantImage(models.Model):
    """Model for storing images associated with product variants (colors, sizes, etc.)
    
    This allows different images to be displayed based on the selected variant.
    For example, when a user selects 'Red' color, images for the red variant are shown.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variant_images')
    variant = models.ForeignKey(
        ProductVariant, 
        on_delete=models.CASCADE, 
        related_name='images',
        help_text="The variant (color, size, etc.) these images are associated with"
    )
    
    # Image fields - main image and thumbnails for this variant
    main_image = models.ImageField(
        upload_to='products/variant_images/',
        null=True, blank=True,
        help_text="Main image for this variant"
    )
    thumbnail1 = models.ImageField(upload_to='products/variant_images/', null=True, blank=True)
    thumbnail2 = models.ImageField(upload_to='products/variant_images/', null=True, blank=True)
    thumbnail3 = models.ImageField(upload_to='products/variant_images/', null=True, blank=True)
    thumbnail4 = models.ImageField(upload_to='products/variant_images/', null=True, blank=True)
    thumbnail5 = models.ImageField(upload_to='products/variant_images/', null=True, blank=True)
    
    order = models.IntegerField(default=0, help_text="Display order for this variant image set")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['variant__variant_type', 'variant__variant_value', 'order']
        unique_together = ['product', 'variant']
        verbose_name = 'Product Variant Image'
        verbose_name_plural = 'Product Variant Images'
    
    def __str__(self):
        return f"{self.product.name} - {self.variant.variant_type}: {self.variant.variant_value}"
    
    def get_all_images(self):
        """Get all images for this variant as a list"""
        images = []
        if self.main_image:
            images.append(self.main_image)
        for thumb in [self.thumbnail1, self.thumbnail2, self.thumbnail3, self.thumbnail4, self.thumbnail5]:
            if thumb:
                images.append(thumb)
        return images

# CartItem model
class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    
    # The Many-to-Many bucket for selected variants
    variants = models.ManyToManyField(
        'ProductVariant', 
        blank=True, 
        related_name='cart_items'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'

    def __str__(self):
        return f"{self.cart.customer.full_name} - {self.product.name} x{self.quantity}"
    
    @property
    def subtotal(self):
        return self.product.price * self.quantity

    def get_variant_description(self):
        """
        Helper to display selected options in Cart/Checkout.
        Returns string like: "Handle: Red, Body: Blue"
        """
        # Prefetch to prevent 50 DB queries if you have 50 items
        selected = self.variants.all()
        if not selected:
            return ""
        
        # .title() makes 'handle' look like 'Handle'
        descriptions = [f"{v.variant_type.title()}: {v.variant_value}" for v in selected]
        return ", ".join(descriptions)

# Wishlist models
class Wishlist(models.Model):
    """Model representing a customer's wishlist"""
    
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='wishlist')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Wishlist'
        verbose_name_plural = 'Wishlists'
    
    def __str__(self):
        return f"Wishlist for {self.customer.full_name}"
    
    @property
    def total_items(self):
        """Get total number of items in wishlist"""
        return self.items.count()

# WishlistItem model
class WishlistItem(models.Model):
    """Model representing an item in a wishlist"""
    
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlist_items')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['wishlist', 'product']  # One wishlist item per product
        ordering = ['-created_at']
        verbose_name = 'Wishlist Item'
        verbose_name_plural = 'Wishlist Items'
    
    def __str__(self):
        return f"{self.wishlist.customer.full_name} - {self.product.name}"

# Notification model
class Notification(models.Model):
    """Model representing notifications for users"""
    
    NOTIFICATION_TYPE_CHOICES = [
        ('order', 'Order Update'),
        ('payment', 'Payment'),
        ('shipping', 'Shipping'),
        ('product', 'Product'),
        ('promotion', 'Promotion'),
        ('system', 'System'),
    ]
    
    # Recipient (can be customer or vendor)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notifications', blank=True, null=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='notifications', blank=True, null=True)
    
    # Notification details
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES, default='system')
    
    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    
    # Optional link to related object
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, blank=True, null=True, related_name='notifications')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, blank=True, null=True, related_name='notifications')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
    
    def clean(self):
        """Validate recipient, BUT allow System notifications (None/None)"""
        from django.core.exceptions import ValidationError
        
        # LOGIC CHANGE: Only raise error if it's NOT a generic system alert
        # If both are None, we assume it's for the Admins.
        pass 

    @property
    def is_admin_notification(self):
        """Helper to identify system-wide alerts"""
        return self.customer is None and self.vendor is None
    
    def __str__(self):
        recipient = self.customer.full_name if self.customer else (self.vendor.business_name if self.vendor else 'Unknown')
        return f"Notification for {recipient}: {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save()
# Proxy models for different notification types
class AdminNotification(Notification):
    """Proxy model for System/Admin alerts only"""
    class Meta:
        proxy = True
        verbose_name = 'Admin Alert'
        verbose_name_plural = 'Admin Alerts'
# Proxy models for different notification types
class UserNotification(Notification):
    """Proxy model for Customer/Vendor messages only"""
    class Meta:
        proxy = True
        verbose_name = 'User Message'
        verbose_name_plural = 'User Messages'