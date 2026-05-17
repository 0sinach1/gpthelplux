import uuid
import random
import string
import datetime
from django.db import models
from django.contrib.auth.models import User
from django.forms import ValidationError
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from luxa_crave.models import University_Profile, University_Outlet

def validate_photo_file(value):
    if not value.name.endswith(('.png', '.jpg')):
        raise ValidationError('Only .jpg and .png files are allowed!')
    
def validate_photo_size(value):
    max_size_mb = 2 
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Photo file too large. Maximum size allowed is {max_size_mb} MB.")

# --- COURIER MODEL (THE ID CARD) ---
class Courier(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]

    SOCIALS = [
        ('INSTAGRAM', 'Instagram',),
        ('WHATSAPP', 'Whatsapp'),
    ]
        

    # PERSONAL INFO
    user_account = models.OneToOneField(User, on_delete=models.CASCADE, related_name='courier_profile')
    home_location = models.JSONField(blank=True, null=True)
    date_of_birth = models.DateField(null=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    photo = models.ImageField(upload_to='courier_photos/', blank=True, null=True, validators=[validate_photo_size, validate_photo_file])

    # Social media
    social_media_platform = models.CharField(max_length=20, choices=SOCIALS, null=True, blank=True)
    social_media_handle = models.CharField(max_length=100, blank=True, null=True, help_text="Your username on the selected social media platform (e.g., @yourhandle)")

    COURIER_CATEGORY_CHOICES = [
        ('SAME_DAY', 'Same-Day Professional'),
        ('STANDARD', 'Standard Logistics'),
        ('CAMPUS', 'Campus Profile'),
        ('CAMPUS_INTERCEPTOR', 'Campus Interceptor Profile'),
        ('EXTERNAL_UPDATER', 'External Updater Profile'),
    ]
    courier_category = models.CharField(
        max_length=20, 
        choices=COURIER_CATEGORY_CHOICES,
        default='CAMPUS'
    )
    courier_student_profile_choices = models.ForeignKey(University_Profile, on_delete=models.SET_NULL, null=True, blank=True)

    interceptor_outlet = models.ForeignKey(University_Outlet, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_outlet')

    # toggle
    manual_key_required = models.BooleanField(default=True)
    
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    verification_date = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_online = models.BooleanField(default=False) # Switched to True when working
    is_locked = models.BooleanField(default=False) # True when first order enters bucket
    is_busy = models.BooleanField(default=False)
    is_scouting = models.BooleanField(default=False)
    is_immune = models.BooleanField(default=False, help_text="True if they are protected from auto-scouting due to a recent order dump or SLA failure.")
    scouting_started_at = models.DateTimeField(null=True, blank=True)   
    
    # Tracks when the very first order of a new batch was assigned
    batch_start_time = models.DateTimeField(blank=True, null=True)
    
    # Tracks when they last hit "Awaiting Confirmation" (to find "Lazy" couriers)
    last_delivery_at = models.DateTimeField(null=True, blank=True)

    last_active = models.DateTimeField(auto_now=True)

    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    consecutive_absences = models.IntegerField(default=0, help_text="Tracks consecutive days of missing shift grace periods.")
    is_suspended = models.BooleanField(default=False, help_text="True if they hit the 2-day strikeout or data falsification penalty.")

    active_shift_start = models.DateTimeField(null=True, blank=True, help_text="Used to calculate the 15-minute grace period.")
    last_heartbeat_ping = models.DateTimeField(null=True, blank=True, help_text="Updated every 30s by the frontend. Determines ALIVE/DEAD status.")

    reliability_score = models.FloatField(
        default=100.0, 
        help_text="The R-Score (0.0 to 100.0). Drops based on SLA failures."
    )
    active_shift_end = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Triggers the 5-Minute Routing Blindspot before clock-out."
    )
    courier_pocket = models.JSONField(
        default=list, 
        blank=True, 
        help_text="Temporary holding zone for scouted dumped orders awaiting the Tollbooth."
    )

    current_online_session_start = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Records the exact timestamp when they toggle 'is_online' to True."
    )

    @property
    def network_name(self):
        """
        Sub-categorizes the courier into specific networks.
        Only 'CAMPUS' uses the gender-split logic.
        Standard and Same-Day return their existing labels to avoid breaking the main engine.
        """
        if self.courier_category == 'CAMPUS':
            # Specific logic for the new Campus venture
            if self.gender == 'female':
                return "CAMPUS_FEMALE_NETWORK"
            if self.gender == 'male':
                return "CAMPUS_MALE_NETWORK"
            return "CAMPUS_GENERAL_NETWORK"

        # Legacy logic: Returns 'STANDARD_NETWORK' or 'SAME_DAY_NETWORK'
        # This keeps your main ecommerce engine running without any changes.
        return f"{self.courier_category}_NETWORK"

    # Used for the status checks and restrictions in the frontend
    @property
    def is_on_active_batch(self):
        """
        Checks if the courier currently has any batches that are forming, assigned, or in transit.
        Used to lock the UI status toggle.
        """
        return self.batches.filter(status__in=['forming', 'assigned', 'in_transit']).exists()

    def __str__(self):
        return f"{self.user_account.first_name} {self.user_account.last_name} ({self.courier_category})"
    
    

class CourierAdministrator(models.Model):
    courier = models.OneToOneField(Courier, on_delete=models.CASCADE, related_name='admin_profile')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    can_manage_escrow = models.BooleanField(default=True)
    can_manage_disputes = models.BooleanField(default=True)

    def __str__(self):
        return f"Admin: {self.courier.user_account.username}"

# --- SECURITY GATE MODEL (THE DAILY LOG) ---
class CourierAccessLog(models.Model):
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name='access_logs')
    daily_access_key = models.CharField(max_length=12)
    issued_at = models.DateTimeField(auto_now_add=True)
    
    # --- NEW FIELDS FOR TRIPWIRE LOGIC ---
    # Stores the "Master Cookie ID" from the trusted device
    authorized_device_id = models.CharField(max_length=255, null=True, blank=True)
    
    # Track which office staff issued the physical key
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-issued_at']

    @classmethod
    def is_access_granted(cls, courier_instance):
        # 1. Get the latest log entry
        latest_log = cls.objects.filter(courier=courier_instance).order_by('-issued_at').first()
        if not latest_log:
            return False

        # 2. Convert all times to LOCAL time
        now = timezone.localtime(timezone.now())
        log_time = timezone.localtime(latest_log.issued_at)
        
        # 3. SET YOUR DEADLINE 
        deadline = now.replace(hour=5, minute=0, second=0, microsecond=0)

        # --- THE UPDATED LOGIC (DATE FIRST, THEN FORWARD COUNT) ---

        # STEP 1: DATE CHECK (The "New Day" Rule)
        # If the key is from any day before today, it is dead.
        if log_time.date() < now.date():
            return False

        # STEP 2: FORWARD TIME LOGIC (Your Scenario A & B)
        
        # Scenario A: The deadline has already passed today
        if now >= deadline:
            # If the key was issued BEFORE that deadline, it is now EXPIRED.
            if log_time < deadline:
                return False

        # Scenario B: We haven't reached the deadline yet
        # (This is your Forward Count—staying valid until the wall hits)
        else:
            # Safety check: If for some reason the key is 24+ hours old
            if (now - log_time).days >= 1:
                return False
            
        # If it passes the Date Check and hasn't hit the Time Wall, it's valid.
        return True
    
    @classmethod
    def regenerate_key(cls, courier_instance):
        """
        THE NUCLEAR RESET: 
        Deletes the current key and creates a brand new one.
        This breaks the 'Mirror' for everyone instantly.
        """
        import random
        new_key = str(random.randint(100000, 999999))
        
        # We create a fresh log, which effectively replaces the old one
        # as the 'latest' Master Key.
        return cls.objects.create(
            courier=courier_instance,
            daily_access_key=new_key,
            issued_at=timezone.now(),
            authorized_device_id=None # Reset ownership so the next valid login claims it
        )

    @classmethod
    def get_or_create_daily_key(cls, courier_instance):
        # If no active shift exists, trigger the creation of the first Master Key
        if not cls.is_access_granted(courier_instance):
            import random
            new_key = str(random.randint(100000, 999999))
            
            cls.objects.create(
                courier=courier_instance,
                daily_access_key=new_key,
                issued_at=timezone.now()
            )
            return new_key
        
        # Otherwise, return the current Master Key
        return cls.objects.filter(courier=courier_instance).latest('issued_at').daily_access_key


# --- COURIER ENGINE (THE BRAIN & CACHE) ---
class CourierEngine(models.Model):
    courier = models.OneToOneField('Courier', on_delete=models.CASCADE, related_name='engine')
    
    # LIVE TRACKING
    current_lat = models.FloatField(null=True, blank=True)
    current_lng = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default='offline') # offline, available, busy
    last_location_update = models.DateTimeField(auto_now=True)

    # THE CACHED FIELD (Stored in DB for fast Decision Engine queries)
    current_stop_load = models.PositiveIntegerField(default=0)

    @property
    def has_active_session(self):
        """Checks the Security Gate model for the 5 AM reset status"""
        return CourierAccessLog.is_access_granted(self.courier)

    @property
    def max_stop_limit(self):
        """Dynamic limit based on the ID Card type"""
        if self.courier.courier_category == 'SAME_DAY':
            return 10
        return 30

    def calculate_current_load(self):
        
        from MAIN.models import LUXAOrder
        """
        Nitty-Gritty logic that reads the LUXAOrder JSONs.
        """
        
        active_orders = LUXAOrder.objects.filter(
            assigned_courier=self.courier
        ).exclude(status__in=['completed', 'cancelled'])

        pending_stops = set()

        for order in active_orders:
            # 1. Check Pickups in Product JSON
            for prod_id, prod_data in order.products.items():
                c_status = prod_data.get('courier_status')
                if c_status in ['assigned_courier', 'pending']:
                    loc = order.pickup_locations.get(prod_id)
                    if loc:
                        pending_stops.add(f"P-{loc['latitude']}-{loc['longitude']}")
            
            # 2. Check Delivery Drop-off
            has_items_in_bag = any(
                p.get('courier_status') == 'picked_up' 
                for p in order.products.values()
            )
            if has_items_in_bag:
                d_loc = order.delivery_location
                pending_stops.add(f"D-{d_loc['latitude']}-{d_loc['longitude']}")

        return len(pending_stops)

    def refresh_load(self):
        """
        The Refresher: Updates the physical DB field 'current_stop_load'.
        """
        self.current_stop_load = self.calculate_current_load()
        self.save(update_fields=['current_stop_load'])

    def __str__(self):
        lock_status = "🔓" if self.has_active_session else "🔒"
        return f"{lock_status} {self.courier.user_account.username} Load: {self.current_stop_load}"
    
    
class DeliveryBatch(models.Model):
    # Statuses: forming -> assigned -> completed (Burned)
    batch_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    courier = models.ForeignKey('Courier', on_delete=models.SET_NULL, null=True, blank=True, related_name='batches')
    status = models.CharField(max_length=20, default='forming')
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True) # <-- ADD THIS
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_volume = models.PositiveIntegerField(default=0)
    bag_location_tag = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Metadata stamp copied directly from the order payload's delivery_point."
    )

    genesis_anchor = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        help_text="The T=0 starting location declared by the courier."
    )
    current_anchor = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        help_text="The physically verified location based on the last Anchor Trigger."
    )
    batch_efficiency = models.FloatField(
        null=True, 
        blank=True, 
        help_text="The calculated E_batch score applied at completion."
    )

    # Add these to DeliveryBatch
    matrix_manifest = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Stores the Brain's calculated pickup/drop-off sequence and micro ETAs."
    )
    total_eta_minutes = models.IntegerField(
        default=0, 
        help_text="The master ETA for the entire batch."
    )


    # HIGHLIGHT: The "Batch Burn" Check
    def check_batch_burn(self):
        from django.utils import timezone
        
        terminal_statuses = ['delivered', 'completed', 'pending_cancellation', 'cancelled']
        
        # 1. Grab both Standard and Campus orders
        standard_orders = list(self.orders.all())
        campus_orders = list(self.campus_orders.all())
        all_children = standard_orders + campus_orders
        
        if not all_children:
            return False
        
        # 2. Check if every single order in the batch is done
        is_ready_to_burn = all(
            getattr(o, 'status', '').lower() in terminal_statuses 
            for o in all_children
        )
        
        if is_ready_to_burn:
            self.status = 'completed'
            self.completed_at = timezone.now() # 🌍 THE MISSING PIECE! The UI needs this to stop the timer!
            self.save(update_fields=['status', 'completed_at'])

            if self.courier:
                self.courier.is_busy = False
                self.courier.last_delivery_at = timezone.now()
                self.courier.save(update_fields=['is_busy', 'last_delivery_at'])
                

            return True 
        return False
# --- SIGNALS ---

@receiver(post_save, sender=Courier)
def ensure_engine_exists(sender, instance, created, **kwargs):
    if created:
        # 1. Always create the engine (Brain)
        CourierEngine.objects.get_or_create(courier=instance)
        
        # 2. Toggle Logic for First-Time Signup
        if not instance.manual_key_required:
            # AUTO-LOG: Generate the key now so 'has_active_session' is True
            CourierAccessLog.get_or_create_daily_key(instance)
        else:
            # MANUAL GATE: Don't create a key. 
            # This forces the dashboard redirect to 'verify_daily_key'
            pass


class Courier_Shift_Roster(models.Model):
    """
    The Ledger. Stores the exact 1-hour blocks a courier committed to.
    """
    courier = models.ForeignKey('Courier', on_delete=models.CASCADE, related_name='shifts')
    shift_date = models.DateField()
    
    # E.g., start_time = 14:00, end_time = 15:00
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    # THE REDEMPTION TRACKER:
    # If True, they didn't pick this manually; the Engine snapped them 
    # into this shift because they took an order from the Dump/Fairness lane.
    is_auto_snapped = models.BooleanField(default=False) 
    
    created_at = models.DateTimeField(auto_now_add=True)

    minutes_online = models.FloatField(
        default=0.0, 
        help_text="Stopwatch: Tracks actual minutes connected to the Engine during this specific shift block."
    )

    class Meta:
        # Absolute Rule: A courier cannot book the exact same hour twice on the same day
        unique_together = ('courier', 'shift_date', 'start_time')
        ordering = ['-shift_date', 'start_time']

        verbose_name = "Courier Shift Roster"
        verbose_name_plural = "Courier Shift Rosters"

    def __str__(self):
        snap_badge = " [SNAPPED]" if self.is_auto_snapped else ""
        return f"{self.courier.user_account.username} | {self.shift_date} | {self.start_time.strftime('%H:%M')}{snap_badge}"


class Courier_Exemption_Request(models.Model):
    """
    The Exemption Vault. 
    Protects a courier from the 7 PM Closing Bell Audit if approved.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    courier = models.ForeignKey('Courier', on_delete=models.CASCADE, related_name='exemptions')
    target_date = models.DateField(help_text="The specific day they cannot work.")
    reason = models.TextField(help_text="Why are they missing the shift? (e.g., Exam, Illness)")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # A courier can only request one exemption per day
        unique_together = ('courier', 'target_date')

        verbose_name = "Courier Exemption Request"
        verbose_name_plural = "Courier Exemption Requests"

    def __str__(self):
        return f"Exemption: {self.courier.user_account.username} for {self.target_date} ({self.status})"


class Manager_Ping(models.Model):
    """
    Tracks real-time SLA intercepts for the Manager's Hot-Drop and Scavenger Waterfall.
    """
    courier = models.ForeignKey('couriers.Courier', on_delete=models.CASCADE, related_name='manager_pings')
    campus_order = models.ForeignKey('luxa_crave.Campus_Engine_Order', on_delete=models.CASCADE, related_name='active_pings')
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired (Ghosted)'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    sla_seconds = models.IntegerField(default=15, help_text="How many seconds the courier has to respond.")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Ping for {self.courier.user_account.username} - {self.status.upper()}"
    

class BannedEmail(models.Model):
    email = models.EmailField(unique=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255, default="2-Day Strikeout")

    def __str__(self):
        return self.email
    


class Courier_Telemetry_Log(models.Model):
    """
    The Black Box Flight Recorder for the Master Equation.
    Logs every single variable used to calculate a score change so admins can audit the math.
    """
    courier = models.ForeignKey('Courier', on_delete=models.CASCADE, related_name='telemetry_logs')
    batch = models.ForeignKey('DeliveryBatch', on_delete=models.SET_NULL, null=True, blank=True)
    
    event_trigger = models.CharField(
        max_length=50, 
        help_text="e.g., 'BATCH_COMPLETION', 'GHOST_PENALTY', 'UNAUTHORIZED_DUMP'"
    )
    
    # --- The Math Variables ---
    c_ratio_logged = models.FloatField(default=1.0, help_text="Lifetime Empathy Ratio (C)")
    e_batch_logged = models.FloatField(default=1.0, help_text="Local Batch Efficiency (E_batch)")
    bonus_points_applied = models.FloatField(default=0.0, help_text="Scavenger/Rescue points (B)")
    penalty_points_applied = models.FloatField(default=0.0, help_text="Deductions (P)")
    
    # --- The Outcome ---
    old_score = models.FloatField()
    new_score = models.FloatField()
    
    # --- Audit Trail ---
    calculation_details = models.TextField(blank=True, null=True, help_text="Human-readable breakdown of the math.")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        delta = self.new_score - self.old_score
        direction = "📈" if delta > 0 else "📉" if delta < 0 else "➖"
        return f"{direction} {self.courier.user_account.username} | {self.event_trigger} | {self.old_score} -> {self.new_score}"