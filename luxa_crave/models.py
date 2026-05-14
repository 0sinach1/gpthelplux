import datetime

from django.utils.timezone import localtime, now
import uuid
from decimal import Decimal
from django.db import models, IntegrityError
from django.core.validators import MinValueValidator
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

# Importing from your MAIN app
from MAIN import models as main_models

# RESTRICTIONS FOR "STRANGE" PRODUCTS IN ORDER PACK MODEL IN pack_surcharge() function

GLOBAL_MAX_ITEM_QTY = 30
MAX_MULTIPLIER_PER_PACK = 10
MAX_TOTAL_PACKS_IN_BAG = 10 # Updated on the 30-3-2026 to 10

def validate_photo_file(value):
    if not value.name.endswith(('.png', '.jpg')):
        raise ValidationError('Only .jpg and .png files are allowed!')
    
def validate_photo_size(value):
    max_size_mb = 2 
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Photo file too large. Maximum size allowed is {max_size_mb} MB.")


# --- 1. UNIVERSITY & OUTLET INFRASTRUCTURE ---

class University_Profile(models.Model):
    # New Professional ID for the Engine
    profile_id = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False, 
        help_text="Unique identifier for campus routing (e.g., CAMPUS-XXXX)",
        null=True # Nullable for existing institution records
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    photo = models.ImageField(validators=[validate_photo_file, validate_photo_size], upload_to='customer_profiles/', blank=True, null=True)

    campus_call_sign = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-z0-9_]+$',
                message='Call sign must be lowercase, contain no spaces, and only use letters, numbers, or underscores.'
            )
        ],
        help_text="Short code for logic routing (e.g., 'landmark_uni'). No spaces or caps allowed."
    )

    on_break = models.BooleanField(default=False, help_text="Toggle to pause all orders for this university profile without taking it down completely.")

    # ==========================================
    # --- SHIFT SCHEDULER: OPERATING HOURS ---
    # ==========================================
    # Weekdays (Monday - Friday)
    weekday_open = models.TimeField(default=datetime.time(14, 0), help_text="e.g., 14:00:00 (2:00 PM)")
    weekday_close = models.TimeField(default=datetime.time(19, 0), help_text="e.g., 19:00:00 (7:00 PM)")
    
    # Weekends (Saturday - Sunday)
    weekend_open = models.TimeField(default=datetime.time(9, 0), help_text="e.g., 09:00:00 (9:00 AM)")
    weekend_close = models.TimeField(default=datetime.time(19, 0), help_text="e.g., 19:00:00 (7:00 PM)")


    def save(self, *args, **kwargs):
        if not self.profile_id:
            import uuid
            new_id = f"CAMPUS-{uuid.uuid4().hex[:8].upper()}"
            while University_Profile.objects.filter(profile_id=new_id).exists():
                new_id = f"CAMPUS-{uuid.uuid4().hex[:8].upper()}"
            self.profile_id = new_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.profile_id})"
    
class Campus_Location(models.Model):
    """Admin-Defined: The general zone on campus."""
    university = models.ForeignKey(University_Profile, on_delete=models.CASCADE, related_name='campus_locations')
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=100, default="none", help_text="The exact 'location_category' value that will be used in the frontend")

    def __str__(self):
        return f"{self.name} ({self.university.name})"

class Location_Building(models.Model):
    """Admin-Defined: The specific building within that zone."""
    parent_location = models.ForeignKey(Campus_Location, on_delete=models.CASCADE, related_name='buildings')
    name = models.CharField(max_length=100, help_text="The building name to be used in the strategy logic.")
    value = models.CharField(max_length=100, default="none", help_text="The exact 'building' value that will be used in the frontend")

    def __str__(self):
        return f"{self.name} - {self.parent_location.name}"

class Crave_Student_Profile(models.Model):
    """Tracks the user's default university so they skip the selection page next time."""
    customer = models.OneToOneField('MAIN.Customer', on_delete=models.CASCADE, related_name='crave_profile')
    default_university = models.ForeignKey(University_Profile, on_delete=models.SET_NULL, null=True, blank=True)
    campus_address = models.ForeignKey(Campus_Location, on_delete=models.SET_NULL, null=True, blank=True)
    campus_building = models.ForeignKey(Location_Building, on_delete=models.SET_NULL, null=True, blank=True)
    room_number = models.CharField(max_length=20, null=True, blank=True)
    proxy_enabled = models.BooleanField(default=False)

# Default proxy settings for customers
class Default_Proxy_Settings(models.Model):
    """" Defines the default proxy details for a customer, which can be used to pre-fill delivery information during checkout. """
    
    GENDER_CHOICES = [
        ('male', 'male'),
        ('female', 'female'),
    ]

    proxy_seed_phrase_hash = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text="Hashed seed phrase for proxy authentication."
    )
    customer = models.OneToOneField(Crave_Student_Profile, on_delete=models.CASCADE, related_name='default_proxy')
    proxy_location = models.ForeignKey(Campus_Location, on_delete=models.SET_NULL, null=True, blank=True)
    proxy_building = models.ForeignKey(Location_Building, on_delete=models.SET_NULL, null=True, blank=True)
    proxy_name = models.CharField(max_length=255, null=True, blank=True)
    proxy_address = models.CharField(max_length=255, null=True, blank=True)
    proxy_photo = models.ImageField(upload_to='proxy_photos/', null=True, blank=True)
    proxy_gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="male")

    # Inside class Default_Proxy_Settings(models.Model):

    def check_seed_phrase(self, entered_phrase):
        """
        Compare the entered phrase against the stored phrase.
        Handles plain text comparison and removes extra spaces.
        """
        if not self.proxy_seed_phrase_hash or not entered_phrase:
            return False
            
        # Standard string comparison (case-sensitive or .lower() for ease)
        return self.proxy_seed_phrase_hash.strip() == entered_phrase.strip()

    def __str__(self):        
        return f"Proxy for {self.customer.customer.user_account.username} - {self.proxy_name or 'No Name'}"

class University_Outlet(models.Model):
    university = models.ForeignKey(University_Profile, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    availability_status = models.BooleanField(default=True) # True = Open, False = Closed
    icon_url = models.CharField(max_length=255, null=True, blank=True)

    time_open = models.TimeField(null=True, blank=True, help_text="e.g., 08:00:00")
    time_closed = models.TimeField(null=True, blank=True, help_text="e.g., 20:00:00")

    description = models.TextField()

    @property
    def is_currently_open(self):
        """Checks manual status first, then verifies if current time is within open hours."""
        if not self.availability_status:
            return False
            
        # If admin hasn't set hours yet, rely solely on the manual availability_status
        if not self.time_open or not self.time_closed:
            return True
            
        current_time = localtime(now()).time()
        
        # Standard daytime hours (e.g., 8 AM to 8 PM)
        if self.time_open < self.time_closed:
            return self.time_open <= current_time <= self.time_closed
        else:
            # Handles overnight shifts (e.g., Open 10 PM, Close 4 AM)
            return current_time >= self.time_open or current_time <= self.time_closed

    def __str__(self):
        return f"{self.name} - {self.university.name}"

class University_Outlet_Section(models.Model):
    outlet = models.ForeignKey(University_Outlet, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=255)
    description = models.TextField()
    # REMOVED price field here. Sections don't have prices, items do.

    def __str__(self):
        return f"{self.name} - {self.outlet.name}"

class Section_Product(models.Model):
    section = models.ForeignKey(University_Outlet_Section, on_delete=models.CASCADE, related_name='products')
    product_name = models.CharField(max_length=255)
    description = models.TextField()
    unit_of_measure = models.CharField(max_length=50) # e.g., 'Portion', 'Spoon', 'Wrap'
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    availability_status = models.BooleanField(default=True)
    last_updated_availability = models.DateTimeField(auto_now=True, help_text="Updates every time the kitchen verifies stock.")
    is_a_soup = models.BooleanField(default=False)
    is_strange = models.BooleanField(default=False)
    strange_value = models.CharField(max_length=255, null=True, blank=True, help_text="The exact 'strange_value' that will trigger validation pack validator .")
    requires_pack = models.BooleanField(default=True) # PDF Spec: True/False
    comes_with_pack = models.BooleanField(default=False) # For items that automatically come with a pack (e.g., a full meal)
    need_soup = models.BooleanField(default=False) # For items that require a soup addition
    not_ordered_alone = models.BooleanField(default=False) # For items that can't be ordered by themselves (e.g., a side that must be paired with a main)
    product_image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    filling_value = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('1.00'),
        help_text="The internal 'volume' this item takes (e.g. 0.5 for rice, 1.5 for chicken)"
    )
    has_charge = models.BooleanField(default=False, help_text="A way to know whether the product needs extra charges for fees")
    

    def __str__(self):
        return f"{self.product_name} ({self.section.name})"


# --- 2. PACK SIZING & TEMPLATES ---

class Pack_Size_Config(models.Model):
    """Defines the available pack sizes and their vendor fees."""
    PACK_CHOICES = [
        ('loose', 'No Pack'),
        ('small', 'Small Pack'),  
        ('medium', 'Medium Pack'),  
        ('large', 'Large Pack'),    
    ]
    size_name = models.CharField(max_length=20, choices=PACK_CHOICES, unique=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2) # The cost of the container
    max_capacity = models.PositiveIntegerField(help_text="Max items this pack can hold")
    pack_image = models.ImageField(upload_to='pack_images/', null=True, blank=True)
    max_overflow = models.DecimalField(max_digits=10, decimal_places=2, help_text="Absolute limit including nylons")
    influence_value= models.PositiveIntegerField(default=0)
    availability = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.get_size_name_display()} (₦{self.base_price})"


# --- 3. THE "ORDER > PACK > ITEM" HIERARCHY ---

class University_Order(models.Model):
    """
    LAYER 1: The Raw Source of Truth for LUXA Campus.
    Isolated from MasterOrder. Retains campus-specific logistics logic.
    """
    ORDER_STATUS_CHOICES = [
        ('ordering_mode', 'Ordering Mode'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('assigned', 'Assigned'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False, 
        null=True
    )
    customer = models.ForeignKey('MAIN.Customer', on_delete=models.CASCADE)
    
    # Payload for Layer 2 and Layer 3
    terminal_payload = models.JSONField(null=True, blank=True)
    
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=ORDER_STATUS_CHOICES, default='ordering_mode')

    extra_info = models.TextField(null=True, blank=True) # For any special instructions or notes 

    # --- ADMIN-CONTROLLED DROPDOWNS ---
    location_category = models.ForeignKey(Campus_Location, on_delete=models.SET_NULL, null=True, blank=True)
    building = models.ForeignKey(Location_Building, on_delete=models.SET_NULL, null=True, blank=True)

    # --- STUDENT MANUAL INPUT ---
    building_block = models.CharField(
        max_length=50, 
        null=True, 
        blank=True, 
        help_text="e.g., Block G, West Wing"
    )
    room_number = models.CharField(
        max_length=20, 
        null=True, 
        blank=True, 
        help_text="e.g., Room 405"
    )

    batch = models.ForeignKey(
        'couriers.DeliveryBatch', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='campus_orders' 
    )

    # --- VIP BYPASS FLAG ---
    custom_assigned = models.BooleanField(
        default=False, 
        help_text="True if the customer bypassed the engine to handpick a courier."
    )

    used_daily_promo = models.BooleanField(default=False)

    # --- NEW: RUSH HOUR WAIT FEE ---
    wait_fee = models.BooleanField(
        default=False,
        help_text="True if ordered from BackYard Caf between 5:30 PM and 7:00 PM."
    )

    total_physical_packs_db = models.PositiveIntegerField(default=0) # New field to store the total physical packs for accurate querying

    is_advance_withdrawn = models.BooleanField(
        default=False, 
        help_text="Phase 7: The Escrow Padlock. Locks the Escape Hatch when True."
    )
    ticked_at_outlet = models.BooleanField(default=False)
    ticked_purchased = models.BooleanField(default=False)
    ticked_in_transit = models.BooleanField(default=False)
    
    is_suspended = models.BooleanField(
        default=False, 
        help_text="The Cryogenic Protocol. True if customer agreed to a massive vendor delay."
    )

    CANCELLATION_CHOICES = [
        ('vendor_closed', 'Vendor is closed'),
        ('out_of_stock', 'Item out of stock'),
        ('massive_delay', 'Vendor delay too long'),
        ('bag_full', 'Bag capacity exceeded'),
        ('other', 'Other (See details)'),
    ]
    cancellation_reason_category = models.CharField(
        max_length=50, 
        choices=CANCELLATION_CHOICES, 
        null=True, 
        blank=True,
        help_text="Fast-selection choice for the courier."
    )
    cancellation_reason_details = models.TextField(
        null=True, 
        blank=True, 
        help_text="Mandatory text explanation if 'Other' is selected, or extra context."
    )

    # --- RETAINED ORIGINAL LOGIC ---
    @property
    def professional_id(self):
        """
        Returns the University Profile ID (e.g., CAMPUS-XXXX).
        If not found, returns the first 8 chars of the Order ID.
        """
        try:
            # Path: Order -> Outlet -> University -> Profile_ID
            if self.outlet and self.outlet.university and self.outlet.university.profile_id:
                return self.outlet.university.profile_id
        except:
            pass
        return f"ORD-{str(self.order_id)[:8].upper()}"

    @property
    def source_order(self):
        return self # I am my own source

    @property
    def cancel_status_map(self):
        return 'cancelled'

    @property
    def supports_proxy(self):
        # Check the related engine view or customer profile
        if hasattr(self, 'engine_view'):
            return True 
        return False
    
    # Inside class University_Order(models.Model):

    @property
    def get_customer_interface(self): # Change the name to something unique
        """
        The absolute safety net. 
        Tries to get the Layer 2 UI, falls back to itself if missing.
        """
        try:
            return self.customer_view # Tries the OneToOne relation
        except Exception:
            return self

    @property
    def is_auth_ready(self):
        """
        Corrected logic:
        1. Get the Crave_Student_Profile (related_name='crave_profile')
        2. Check if it has Default_Proxy_Settings (related_name='default_proxy')
        3. Check if the 'proxy_seed_phrase_hash' field has a value.
        """
        profile = getattr(self.customer, 'crave_profile', None)
        if profile and hasattr(profile, 'default_proxy'):
            # Use the exact field name from your Default_Proxy_Settings model
            return bool(profile.default_proxy.proxy_seed_phrase_hash)
        return False
    
    @property
    def total_physical_packs(self):
        """
        Sums the influence_value already saved on each pack.
        """
        return sum(pack.influence_value for pack in self.packs.all())
    

    @property
    def total_surcharge_fee(self):
        """Sums up all bread surcharges across all packs"""
        return sum((pack.pack_surcharge for pack in self.packs.all()), Decimal('0.00'))

    @property # HOLDS THE CALCULATION FOR THE DELIVERY FEE
    def delivery_fee(self):
        total_surcharge = Decimal('0.00')
        has_standard_pack = False
        
        for pack in self.packs.all():
            if pack.items.exclude(product__is_strange=True).exists() or pack.pack_surcharge < Decimal('1.00'):
                has_standard_pack = True
                
            total_surcharge += pack.pack_surcharge 

        base_fee = Decimal('0.00')
        if has_standard_pack:
            # --- NEW: BREAD_EGG DYNAMIC PACK COUNTING ---
            standard_pack_count = 0
            for p in self.packs.all():
                if p.items.exclude(product__is_strange=True).exists() or p.pack_surcharge < Decimal('1.00'):
                    
                    # Count how many bread_eggs are in this specific pack
                    bread_egg_qty = sum(item.quantity for item in p.items.all() if getattr(item.product, 'strange_value', '') == 'bread_egg')
                    
                    # If it has bread_eggs, each one counts as a pack. Otherwise, it defaults to 1.
                    base_count = bread_egg_qty if bread_egg_qty > 0 else 1
                    
                    # Add to the total count, accounting for the bundle multiplier
                    standard_pack_count += (base_count * p.multiplier)
            
            if standard_pack_count > 0:
                # Cap at 10 to prevent breaking the math formula
                count = min(standard_pack_count, 10)
                
                if count == 10:
                    # Special bulk rate for hitting the max
                    rate_per_pack = Decimal('300.00')
                else:
                    # Formula: 400 for 1st pack, drops by 10 for each additional pack up to 9.
                    rate_drop = (count - 1) * 10
                    rate_per_pack = Decimal('400.00') - Decimal(str(rate_drop))
                
                # Calculate the final base delivery fee
                base_fee = Decimal(str(count)) * rate_per_pack
                
                # base_fee = Decimal(str(count)) * Decimal('200.00') - PROMO FLAT FEE OF 200
                
        final_delivery_fee = base_fee + total_surcharge

        # --- APPLY WAIT FEE ---
        if getattr(self, 'wait_fee', False):
            final_delivery_fee += Decimal('300.00')

        # --- APPLY LOYALTY DISCOUNT ---
        if getattr(self, 'used_daily_promo', False) and self.customer.promo_percentage > 0:
            discount_multiplier = Decimal('1.00') - (self.customer.promo_percentage / Decimal('100.00'))
            final_delivery_fee = final_delivery_fee * discount_multiplier
            
        return final_delivery_fee.quantize(Decimal('0.00'))
    

    @property
    def total_order_cost(self):
        # 1. Price of the food itself (e.g., the ₦1800 for the bread)
        subtotal = sum((pack.total_pack_cost for pack in self.packs.all()), Decimal('0.00'))
        
        # 2. This ALREADY includes (Standard Tier + Bread Surcharges)
        # because of the update we made to the delivery_fee property
        total_delivery = self.delivery_fee
        
        return subtotal + total_delivery
    
    def get_active_campus_couriers(self):
        from couriers.models import Courier
        return Courier.objects.filter(is_online=True, courier_category='CAMPUS').select_related('user_account')
            

    def can_add_pack(self, multiplier=1):
        if (self.total_physical_packs + multiplier) > MAX_TOTAL_PACKS_IN_BAG:
            return False, "Courier limit reached! Checkout this bag first to buy more."
        return True, "Success"

    
    def save(self, *args, **kwargs):
        if not self.order_number:
            max_attempts = 10
            attempts = 0
            while attempts < max_attempts:
                new_number = f"ORD-UC-{uuid.uuid4().hex[:12].upper()}"
                if not University_Order.objects.filter(order_number=new_number).exists():
                    self.order_number = new_number
                    break
                attempts += 1
        
        try:
            super().save(*args, **kwargs)
        except IntegrityError as e:
            if 'order_number' in str(e).lower():
                self.order_number = f"ORD-UC-{uuid.uuid4().hex[:12].upper()}"
                super().save(*args, **kwargs)
            else:
                raise

    def __str__(self):
        return f"{self.order_number or self.order_id} by {self.customer.user_account.username}"
    
    
class Customer_Order_View(models.Model):
    """
    LAYER 2: The Student's User Interface Model.
    Includes verification for the Hashed Seed Phrase.
    """
    raw_order = models.OneToOneField(
        'University_Order', 
        on_delete=models.CASCADE, 
        related_name='customer_view'
    )

    readable_id = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)

    @property
    def is_auth_ready(self):
        """Checks the proxy settings through the raw_order relationship."""
        crave_profile = getattr(self.raw_order.customer, 'crave_profile', None)
        if crave_profile and hasattr(crave_profile, 'default_proxy'):
            return bool(crave_profile.default_proxy.proxy_seed_phrase_hash)
        return False

    @property
    def authorized_recipient_name(self):
        """Only shows Proxy if 'proxy_enabled' is True in Crave_Student_Profile."""
        crave_profile = self.raw_order.customer.crave_profile
        
        if crave_profile.proxy_enabled and hasattr(crave_profile, 'default_proxy'):
            return f"AUTHORIZED PROXY: {crave_profile.default_proxy.proxy_name}"
        
        return f"STUDENT: {self.raw_order.customer.user_account.username}"

    @property
    def authorized_photo(self):
        """Switches photo based on the proxy_enabled status."""
        crave_profile = self.raw_order.customer.crave_profile
        
        if crave_profile.proxy_enabled:
            if hasattr(crave_profile, 'default_proxy') and crave_profile.default_proxy.proxy_photo:
                return crave_profile.default_proxy.proxy_photo.url
        
        # Fallback to student's main profile picture from the MAIN app
        return self.raw_order.customer.profile_picture.url

    def save(self, *args, **kwargs):
        if not self.readable_id:
            import random
            # Generates the #LC-XXX ID for quick courier/student reference
            self.readable_id = f"#LC-{random.randint(100, 999)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.readable_id} - View for {self.raw_order.order_number}"


class Campus_Engine_Order(models.Model):
    """
    LAYER 3: The Machine-Interface Model.
    Provides a structured JSON for the external Engine App.
    Pulls strict gender data from the MAIN.Customer model.
    """
    raw_order = models.OneToOneField(
        'University_Order', 
        on_delete=models.CASCADE, 
        related_name='engine_view'
    )

    # The Structured Output for the Engine
    engine_payload = models.JSONField(
        editable=False, 
        help_text="Machine-optimized JSON for the Engine App."
    )


    ENGINE_STATUS_CHOICES = [
        ('pending', 'Pending'),      # Just created, waiting for engine
        ('processing', 'Processing'), # Engine is currently working on it
        ('assigned', 'Assigned'),
        ('shipped', 'In Transit'),
        ('completed', 'Completed'),
        ('pending_cancellation', 'Pending Cancellation'),  # Courier found
        ('dumped', 'Dumped'),        # No courier found, sent to dump
        ('failed', 'Failed'),        # System error (e.g., DB crash),
    ]

    status = models.CharField(
        max_length=30, 
        choices=ENGINE_STATUS_CHOICES, 
        default='pending',
        help_text="Status of the order in relation to the courier assignment."
    )

    assigned_at = models.DateTimeField(null=True, blank=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    assigned_campus_courier = models.ForeignKey(
        "couriers.Courier", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_campus_orders'
    )

    # Add this inside Campus_Engine_Order in luxa_crave/models.py
    expected_eta_minutes = models.IntegerField(
        null=True, 
        blank=True, 
        help_text="The dynamically calculated minutes until delivery. Updated by the ACM Brain."
    )


    def generate_engine_payload(self):
        """
        Structures the data for the External Engine.
        Uses the exact GENDER_CHOICES from the Customer/Proxy model.
        """
        order = self.raw_order
        customer = order.customer # Accessing MAIN.Customer
        crave_profile = customer.crave_profile
        
        # Check if proxy is active to set the 'is_proxy' flag
        use_proxy = crave_profile.proxy_enabled and hasattr(crave_profile, 'default_proxy')

        # --- THE FIX: DYNAMIC GENDER ROUTING ---
        # If proxy is enabled, use the proxy's gender. Otherwise, use the customer's.
        if use_proxy and crave_profile.default_proxy.proxy_gender:
            target_gender = crave_profile.default_proxy.proxy_gender
        else:
            target_gender = customer.gender

        # --- THE AUTOMATIC STAMP LOGIC ---
        # We grab the first item's outlet since validation ensures the whole bag matches
        first_pack = order.packs.first()
        first_item = first_pack.items.first() if first_pack else None
        origin_outlet_id = first_item.product.section.outlet.id if first_item else None
        origin_outlet_name = first_item.product.section.outlet.name if first_item else None

        building_id = order.building.id if order.building else None
        building_name = order.building.name if order.building else "N/A"
        
        # 🌍 THE FIX: MEMORY RETRIEVAL
        # Before we build the new payload, grab any dynamic flags from the old one!
        existing_payload = self.engine_payload or {}
        existing_acm_state = existing_payload.get('acm_state', {})
        saved_scavenger_signature = existing_acm_state.get('scavenged_by', None)

        payload = {
            "order_metadata": {
                "order_id": str(order.order_id),
                "order_number": order.order_number,
                "university_id": order.location_category.university.profile_id,
                "campus_call_sign": order.location_category.university.campus_call_sign, # ADDED
            },
            "customer_data": {
                "customer_id": customer.id, # Primary identifier
                "username": customer.user_account.username,
                "gender": target_gender, # <--- UPDATED: Dynamically switches!
            },
            "delivery_point": {
                "location_id": order.location_category.id,
                "location_name": order.location_category.name, # ADDED
                "building_id": building_id,
                "building_name": building_name, # ADDED
                "block": order.building_block,
                "room": order.room_number,
                "is_proxy": use_proxy,
                "outlet_id": origin_outlet_id,
                "outlet_name": origin_outlet_name,
            },
            "security_config": {
                "requires_seed_phrase": use_proxy and bool(crave_profile.default_proxy.proxy_seed_phrase_hash),
            },
            "logistics_summary": {
                "total_packs": order.total_physical_packs, # Safely falls back if missing
            },

            "acm_state": {
                "is_advance_withdrawn": order.is_advance_withdrawn,
                "is_suspended": order.is_suspended,
                "tollbooth": {
                    "at_outlet": order.ticked_at_outlet,
                    "purchased": order.ticked_purchased,
                    "in_transit": order.ticked_in_transit
                }
            }
        }

        # 🌍 THE FIX: MEMORY RE-INJECTION
        # If a courier claimed this order earlier, put their signature back in!
        if saved_scavenger_signature:
            payload["acm_state"]["scavenged_by"] = saved_scavenger_signature
            
        return payload
    

    @property
    def display_data(self):
        raw = self.raw_order
        # If raw_order is somehow missing, we return a barebones dict immediately
        if not raw:
            return {'customer_name': "Broken Link", 'internal_id': "Error"}

        customer = getattr(raw, 'customer', None)

        # 1. FIXED OUTLET RESOLUTION (Traversing through .product)
        try:
            outlet_name = "Campus Outlet"
            first_pack = raw.packs.all().first()
            if first_pack:
                first_item = first_pack.items.all().first()
                # FIX: Must go through item.product to get to the section
                if first_item and first_item.product and first_item.product.section:
                    outlet_name = first_item.product.section.outlet.name.strip()
        except Exception as e:
            outlet_name = f"Outlet Error: {e}"

        # 2. BUNDLE LIST (Internal Try/Except)
        bundle_list = []
        try:
            for pack in raw.packs.all():
                items_in_bundle = []
                for item in pack.items.all():
                    items_in_bundle.append({
                        'name': item.product.product_name if item.product else 'Unknown',
                        'qty': item.quantity,
                        'unit_price': item.product.unit_price if item.product else 0,
                        'ind_items_cost': (item.quantity * item.product.unit_price) if item.product else 0,
                    })
                
                p_size = getattr(pack, 'pack_size', None)
                bundle_list.append({
                    'pack_name': p_size.size_name if p_size else "Standard Pack",
                    'pack_price': p_size.base_price if p_size else 0,
                    'total_items_cost': getattr(pack, 'total_item_cost', 0) or 0,
                    'show_pack_header': True if p_size else False,
                    'multiplier': getattr(pack, 'multiplier', 1) or 1,
                    'items': items_in_bundle
                })
        except Exception as e:
            bundle_list = [{'pack_name': f"Bundle Error: {e}", 'items': []}]

        # 3. NAME & PHOTO (Safe Defaults)
        f_name = getattr(customer, 'first_name', '') if customer else ''
        l_name = getattr(customer, 'last_name', '') if customer else ''
        full_name = f"{f_name} {l_name}".strip() or getattr(customer, 'username', 'Unknown Customer')

        try:
            photo_url = customer.profile_picture.url if customer and customer.profile_picture else '/static/images/user.png'
        except:
            photo_url = '/static/images/user.png'

        # 4. FINAL DICTIONARY (No global try/except here)
        return {
            'outlet_name': outlet_name,
            'authorized_photo': photo_url,
            'customer': customer,
            'customer_name': full_name,
            'customer_id': getattr(customer, 'id', 0),
            'Volume': getattr(raw, 'total_physical_packs_db', 0) or 0,
            'order_id': str(getattr(raw, 'order_id', '0')),
            'order_number_short': str(getattr(raw, 'order_id', '0'))[-8:],
            'network_label': 'Courions',
            'delivery_location': f"{raw.location_category.university.name}, {raw.building.value} -> Room {raw.room_number}" if getattr(raw, 'building', None) else f"RM {getattr(raw, 'room_number', 'N/A')}",
            'extra_info': raw.extra_info if (raw.extra_info) else "No extra instructions",
            'kyc_details': customer.kyc_profile if (customer and hasattr(customer, 'kyc_profile') and customer.kyc_profile) else "No KYC Profile",
            'is_kyc_approved': (customer.kyc_profile.status == 'APPROVED') if (customer and hasattr(customer, 'kyc_profile') and customer.kyc_profile) else False,
            'internal_id': str(getattr(raw, 'order_id', '0')),
            'bundles': bundle_list,
            'manifest_total': (getattr(raw, 'total_order_cost', 0) or 0) - (getattr(raw, 'delivery_fee', 0) or 0),
            'proxy_data': customer.crave_profile.default_proxy if (customer and hasattr(customer, 'crave_profile') and hasattr(customer.crave_profile, 'default_proxy')) else None,
            'expected_eta_minutes': self.expected_eta_minutes or 0,
        }
    def save(self, *args, **kwargs):
        # Regenerates the payload whenever the order or customer data is saved
        self.engine_payload = self.generate_engine_payload()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Engine JSON for {self.raw_order.order_number}"

class Order_Pack(models.Model):
    """Represents an instantiated pack inside the user's 'Bottom Pack Bar'."""
    order = models.ForeignKey(University_Order, on_delete=models.CASCADE, related_name='packs')
    pack_size = models.ForeignKey(Pack_Size_Config, 
                                  on_delete=models.PROTECT,
                                  null=True, 
                                  blank=True)
    
    status = models.CharField(max_length=20, default='Open') # 'Open' (in bottom bar) or 'Closed' (in summary view)
    created_at = models.DateTimeField(auto_now_add=True)
    multiplier = models.PositiveIntegerField(default=1) # Add this field
    influence_value = models.PositiveIntegerField(default=0) # Add this field

    @property
    def total_item_cost(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_pack_cost(self):
        """Updated to include multiplier"""
        needs_pack = self.items.filter(product__requires_pack=True).exists()
        pack_fee = self.pack_size.base_price if needs_pack else Decimal('0.00')
        it_has_charge = True if self.items.filter(product__has_charge=True).exists() else False

        if it_has_charge:
            pack_fee += Decimal('50.00') # Flat fee for any pack containing chargeable items

        return (self.total_item_cost + pack_fee) * self.multiplier


    @property
    def contains_normal_item(self):
        """
        Check if any product in this pack is NOT strange.
        Matches JS: if (!isStrange) { hasNormalItem = true; }
        """
        # We use product__is_strange to look into the Section_Product model
        return self.items.filter(product__is_strange=False).exists()

    @property
    def pack_surcharge(self):
        """
        Calculate surcharges for 'Strange' products like Bread.
        Matches JS: SPECIAL_RESTRICTIONS logic.
        """
        surcharge = Decimal('0.00')
        restrictions = {
            'large_bread': Decimal('250.00'),
            'medium_bread': Decimal('200.00'),
            'small_bread': Decimal('125.00'),
            'bread_egg': Decimal('0.00'),
        }
        
        for item in self.items.all():
            # Check properties on the linked product
            if item.product.is_strange and item.product.strange_value in restrictions:
                fee = (item.quantity * self.multiplier) * restrictions[item.product.strange_value]
                surcharge += fee
        return surcharge
    

    @property
    def box_fill_level(self):
        """Calculates current sum of items that MUST be inside the box"""
        return sum(item.product.filling_value * item.quantity for item in self.items.all() if item.product.requires_pack)

    @property
    def total_payload_level(self):
        """Calculates current sum of EVERYTHING (Box + Overflow)"""
        return sum(item.product.filling_value * item.quantity for item in self.items.all())

    def can_add_item(self, product, quantity=1):
        """The Master Algorithm Check"""
        new_value = product.filling_value * quantity
        
        # Rule 1: If it needs a box, check the 'max_capacity' (The Lid Rule)
        if product.requires_pack:
            if (self.box_fill_level + new_value) > self.pack_size.max_capacity:
                return False, "The box is full! Try a larger pack or use an overflow item."

        # Rule 2: Check the 'max_overflow' (The Gaming Rule)
        if (self.total_payload_level + new_value) > self.pack_size.max_overflow:
            return False, "This pack has reached its absolute weight limit."
        
        # Rule 3: Anti-Gaming (Max units of ONE item in one pack)
        existing_item = self.items.filter(product=product).first()
        current_qty = existing_item.quantity if existing_item else 0
        if (current_qty + quantity) > GLOBAL_MAX_ITEM_QTY:
            return False, f"Maximum {GLOBAL_MAX_ITEM_QTY} units of this item allowed per pack."

        return True, "Success"
    
    def clean(self):
        """Enforce the max multiplier for a single pack configuration"""
        if self.multiplier > MAX_MULTIPLIER_PER_PACK:
            from django.core.exceptions import ValidationError
            raise ValidationError(f"You cannot order more than {MAX_MULTIPLIER_PER_PACK} of the same pack configuration.")

class Order_Pack_Item(models.Model):
    """The actual food items dropped into a specific pack."""
    pack = models.ForeignKey(Order_Pack, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Section_Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    
    @property
    def subtotal(self):
        """PDF Spec: Unit Price X Quantity"""
        return self.product.unit_price * Decimal(str(self.quantity))
    
    def clean(self):
        if self.quantity > GLOBAL_MAX_ITEM_QTY:
            from django.core.exceptions import ValidationError
            raise ValidationError(f"Maximum quantity for {self.product.product_name} is {GLOBAL_MAX_ITEM_QTY}.")

    

class User_Venture_Profile_Settings(models.Model):
    """
    The Base Hub for all unique venture settings.
    Unique to: Each User + Each Specific Profile (e.g., Landmark).
    
    This is currently an EMPTY anchor. We will add fields here 
    manually as we define them one by one.
    """
    user = models.ForeignKey('MAIN.Customer', on_delete=models.CASCADE)
    profile = models.ForeignKey('University_Profile', on_delete=models.CASCADE)
    
    selected_theme = models.CharField(max_length=50, default="standard_light")   #theme settings

    class Meta:
        # Ensures that a user has exactly one settings record per profile.
        unique_together = ('user', 'profile')
        verbose_name = "User Venture Profile Setting"

    def __str__(self):
        return f"Settings Hub: {self.user} @ {self.profile.name}"
    
    

# --- 4. CAMPUS PRESETS ---

class Campus_Pack_Preset(models.Model):
    """
    Stores a customer's custom pack order for quick 1-click cart injection.
    Tied to a specific outlet because products are outlet-specific.
    """
    customer = models.ForeignKey(Crave_Student_Profile, on_delete=models.CASCADE, related_name='presets')
    outlet = models.ForeignKey(University_Outlet, on_delete=models.CASCADE, related_name='pack_presets')

    # NEW: Add the multiplier field
    pack_multiplier = models.PositiveIntegerField(default=1)
    
    preset_name = models.CharField(max_length=100, help_text="e.g., 'My Friday Lunch', 'Post-Exam Feast'")
    pack_size = models.ForeignKey(Pack_Size_Config, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.preset_name} ({self.customer.customer.user_account.username})"
    
    @property
    def current_total_price(self):
        """Dynamically calculates the price based on CURRENT vendor prices, not historical ones."""
        items_total = sum(item.product.unit_price * item.quantity for item in self.items.all())
        pack_fee = self.pack_size.base_price if self.pack_size else Decimal('0.00')
        
        # Check if any item actually requires the pack container
        needs_pack = any(item.product.requires_pack for item in self.items.all())
        if not needs_pack:
            pack_fee = Decimal('0.00')
            
        # UPDATED: Multiply the base cost by the saved pack multiplier
        return (items_total + pack_fee) * self.pack_multiplier

class Campus_Pack_Preset_Item(models.Model):
    """The individual food items saved inside a preset."""
    preset = models.ForeignKey(Campus_Pack_Preset, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Section_Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity}x {self.product.product_name}"
    
class VerificationPing(models.Model):
    """The central request sent from the Engine to the Kitchen Interceptor."""
    outlet = models.ForeignKey(University_Outlet, on_delete=models.CASCADE, related_name='active_pings')
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('resolved', 'Resolved')], default='pending')
    interceptor_message = models.TextField(null=True, blank=True, help_text="Mandatory if any item is out of stock.")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Ping for {self.outlet.name} - {self.status}"

class VerificationPingItem(models.Model):
    """The specific low-confidence items the kitchen needs to check."""
    ping = models.ForeignKey(VerificationPing, on_delete=models.CASCADE, related_name='flagged_items')
    product = models.ForeignKey(Section_Product, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)

