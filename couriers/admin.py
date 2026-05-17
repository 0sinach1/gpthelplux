from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils.html import format_html
from django.utils import timezone
from .models import BannedEmail, Courier, Courier_Exemption_Request, Courier_Shift_Roster, Courier_Telemetry_Log, CourierAccessLog, CourierEngine, DeliveryBatch, CourierAdministrator
from MAIN.models import LUXAOrder
from luxa_crave.models import University_Order

# ==========================================
# 1. PROXY MODELS (The Foundation)
# ==========================================

class StandardCourier(Courier):
    class Meta:
        proxy = True
        verbose_name = "👤 Standard Network Courier"
        verbose_name_plural = "👤 Standard Network Couriers"

class CampusCourier(Courier):
    class Meta:
        proxy = True
        verbose_name = "🎓 Campus Network Courier"
        verbose_name_plural = "🎓 Campus Network Couriers"

class ExternalUpdater(Courier):
    class Meta:
        proxy = True
        verbose_name = "🔄 External Updater"
        verbose_name_plural = "🔄 External Updaters"

class CampusInterceptor(Courier):
    class Meta:
        proxy = True
        verbose_name = "🚆 Campus Interceptor"
        verbose_name_plural = "🚆 Campus Interceptors"

class StandardBatch(DeliveryBatch):
    class Meta:
        proxy = True
        verbose_name = "📦 Standard Delivery Batch"
        verbose_name_plural = "📦 Standard Delivery Batches"

class CampusBatch(DeliveryBatch):
    class Meta:
        proxy = True
        verbose_name = "🎒 Campus Delivery Batch"
        verbose_name_plural = "🎒 Campus Delivery Batches"

class StandardDump(LUXAOrder):
    class Meta:
        proxy = True
        verbose_name = "Standard Dump Order"
        verbose_name_plural = "Standard Dump Orders"

class CampusDump(University_Order):
    class Meta:
        proxy = True
        verbose_name = "Campus Dump Order"
        verbose_name_plural = "Campus Dump Orders"

# ==========================================
# 2. CLEANUP
# ==========================================

try:
    admin.site.unregister(Courier)
    admin.site.unregister(DeliveryBatch)
    admin.site.unregister(LUXAOrder)
except NotRegistered:
    pass

# ==========================================
# 3. STANDARD NETWORK COURIERS (EXACT ORIGINAL LAYOUT)
# ==========================================

@admin.register(StandardCourier)
class StandardCourierAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).exclude(courier_category='CAMPUS')

    # Re-using your preferred list display
    list_display = ['user_account', 'gender', 'courier_category', 'created_at', 'is_verified', 'is_active', 'is_online']
    search_fields = ['user_account']
    list_editable = ('is_verified', 'is_active', 'is_online')
    ordering = ('-created_at',)

    # Disable 'Add' button here to keep it as a viewing bucket only
    def has_add_permission(self, request):
        return False

# --- INJECTION: CUSTOM FILTER ---
class DumpedStatusFilter(admin.SimpleListFilter):
    title = 'Assignment Status'
    parameter_name = 'dump_status'

    def lookups(self, request, model_admin):
        return (
            ('dumped', '📦 Dumped_Standard'),
            ('real', '👤 Real Couriers'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'dumped':
            return queryset.filter(assigned_courier__user_account__username="Dumped_Standard")
        if self.value() == 'real':
            return queryset.exclude(assigned_courier__user_account__username="Dumped_Standard").exclude(assigned_courier__isnull=True)
        return queryset

@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    # Matches your model: 'courier_category'
    fieldsets = (
        ('Personal Info', {
            'fields': ('user_account', 'date_of_birth', 'gender', 'photo', 'social_media_platform', 'social_media_handle')
        }),
        ('Status & Category', {
            'fields': ('courier_category', 'interceptor_outlet', 'is_verified', 'is_active', 'is_online', 'is_scouting')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    list_display = (
        'user_account', 
        'get_first_name',
        'heartbeat_status',      # <-- The new visual status
        'last_heartbeat_ping',    # <-- The raw timestamp
        'gender', 
        'courier_category', 
        'interceptor_outlet', 
        'is_verified', 
        'is_active',
        'is_online',
        'is_scouting',
        'is_suspended',
        'consecutive_absences',
        'scouting_started_at',
        'created_at',
        'reliability_score',
       
    )

    ordering = ('-created_at',)

    list_filter = ('courier_category', 'gender', 'is_verified', 'is_active')
    list_editable = ('is_verified', 'is_active', 'is_online', 'reliability_score', 'is_suspended', 'consecutive_absences')
    search_fields = ('user_account__username', 'user_account__first_name', 'user_account__last_name', 'user_account__email')
    readonly_fields = ('created_at', 'updated_at', 'last_heartbeat_ping')

    # 3. Create the Custom Visual Column
    def heartbeat_status(self, obj):
        if not obj.is_online:
            return "⚪ OFFLINE"

        if not obj.last_heartbeat_ping:
            return "⚫ NO PULSE YET"
        
        # Calculate exactly what the Brain calculates
        time_since_ping = (timezone.now() - obj.last_heartbeat_ping).total_seconds()
        
        if time_since_ping <= 60:
            return f"🟢 ALIVE ({int(time_since_ping)}s ago)"
        elif time_since_ping <= 120:
            return f"🟡 LAGGING ({int(time_since_ping)}s ago)"
        else:
            return f"🔴 DEAD ({int(time_since_ping)}s ago)"
            
    heartbeat_status.short_description = "Brain Connection"

    # --- RESTORING ORIGINAL BULK ACTIONS ---
    actions = ['bulk_deactivate', 'bulk_offline', 'bulk_unverify', 'bulk_online']

    @admin.display(description='First Name')
    def get_first_name(self, obj):
        return obj.user_account.first_name
    
    @admin.action(description="Deactivate selected couriers")
    def bulk_deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Selected couriers have been deactivated.")

    @admin.action(description="Force selected couriers offline")
    def bulk_offline(self, request, queryset):
        queryset.update(is_online=False)
        self.message_user(request, "Selected couriers are now offline.")

    @admin.action(description="Force selected couriers online")
    def bulk_online(self, request, queryset):
        queryset.update(is_online=True)
        self.message_user(request, "Selected couriers are now online.")

    @admin.action(description="Unverify selected couriers")
    def bulk_unverify(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, "Selected couriers are now unverified.")

# ==========================================
# 4. CAMPUS NETWORK COURIERS (FULL STRUCTURE + UNIVERSITY)
# ==========================================

@admin.register(CampusCourier)
class CampusCourierAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Specifically only show Campus category
        return super().get_queryset(request).filter(courier_category='CAMPUS')

    # --- EXACT ORIGINAL FIELDS + UNIVERSITY PROFILE ---
    fields = (
        'user_account', 
        'courier_category',
        'courier_student_profile_choices', # THE CAMPUS FIELD
        'gender', 
        'social_media_platform',
        'social_media_handle',
        'total_earnings',
        'interceptor_outlet',
        'is_verified', 
        'is_active', 
        'is_online',
        'is_scouting',
        'is_immune',
        'scouting_started_at',
        'date_of_birth', 
        'verification_date', 
        'home_location',
        'created_at', 
        'updated_at'
    )

    # Included Gender and University Profile in the view
    list_display = (
        'user_account', 
        'get_first_name',
        'courier_student_profile_choices', # Visible University
        'gender',                          # Visible Gender
        'total_earnings',                  # Visible Total Earnings
        'is_verified', 
        'is_active',
        'is_online',
        'is_scouting',
        'is_immune',
        'interceptor_outlet',
        'scouting_started_at',
        'created_at',
    )

    ordering = ('-created_at',)

    # Full Filtering Power
    list_filter = (
        'courier_student_profile_choices', 
        'gender', 
        'is_verified', 
        'is_active'
    )
    
    list_editable = ('is_verified', 'is_active', 'is_online', 'is_immune')
    search_fields = ('user_account__username', 'user_account__first_name', 'user_account__last_name')
    readonly_fields = ('created_at', 'updated_at')

    # --- RESTORING ORIGINAL BULK ACTIONS ---
    actions = ['bulk_deactivate', 'bulk_offline', 'bulk_unverify', 'bulk_online']

    @admin.display(description='First Name')
    def get_first_name(self, obj):
        return obj.user_account.first_name
    
    @admin.action(description="Deactivate selected couriers")
    def bulk_deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Selected couriers have been deactivated.")

    @admin.action(description="Force selected couriers offline")
    def bulk_offline(self, request, queryset):
        queryset.update(is_online=False)
        self.message_user(request, "Selected couriers are now offline.")

    @admin.action(description="Force selected couriers online")
    def bulk_online(self, request, queryset):
        queryset.update(is_online=True)
        self.message_user(request, "Selected couriers are now online.")

    @admin.action(description="Unverify selected couriers")
    def bulk_unverify(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, "Selected couriers are now unverified.")


# EXTERNAL UPDATER (PRESERVED AS VIEW-ONLY)
@admin.register(CampusInterceptor)
class CampusInterceptorAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(courier_category='CAMPUS_INTERCEPTOR')

    list_display = ['user_account', 'gender', 'courier_category', 'created_at', 'updated_at']
    fields = ['user_account', 'gender', 'courier_category']
    search_fields = ['user_account']

# EXTERNAL UPDATER (PRESERVED AS VIEW-ONLY)
@admin.register(ExternalUpdater)
class ExternalUpdaterAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(courier_category='EXTERNAL_UPDATER')

    list_display = ['user_account', 'gender', 'courier_category', 'created_at', 'updated_at']
    fields = ['user_account', 'gender', 'courier_category']
    search_fields = ['user_account']


# --- INJECTION: ADMIN PROFILE FOR COURIER MANAGEMENT --- This allows us to link specific couriers to admin accounts for managing escrow and disputes.
@admin.register(CourierAdministrator)
class CourierAdministratorAdmin(admin.ModelAdmin):
    list_display = ('courier', 'get_email', 'can_manage_escrow', 'created_at')
    search_fields = ('courier__user_account__username', 'courier__user_account__email', 'courier__user_account__first_name')
    list_filter = ('can_manage_escrow', 'created_at')
    
    # This creates a searchable dropdown instead of a massive list of 1,000s of couriers
    autocomplete_fields = ('courier',) 

    def get_email(self, obj):
        return obj.courier.user_account.email
    get_email.short_description = 'Admin Email'


# ==========================================
# 5. CAMPUS DELIVERY BATCH (SPECIFIC UPDATED SECTION)
# ==========================================

class UniversityOrderInline(admin.TabularInline):
    """Inline for Campus Orders allowing status edits and gender visibility."""
    model = University_Order
    
    # Fields to display: includes Customer Gender (Read-only) and Status (Editable)
    fields = [
        'order_id', 
        'get_customer_gender', 
        'status', 
        'total_physical_packs', 
        'order_date'
    ]

    ordering = ('-order_date',)
    
    # We lock everything except 'status' to protect order integrity
    readonly_fields = [
        'order_id', 
        'get_customer_gender', 
        'order_date', 
        'total_physical_packs'
    ]
    
    extra = 0
    show_change_link = True
    fk_name = 'batch'

    @admin.display(description="Customer Gender")
    def get_customer_gender(self, obj):
        """Displays the gender of the customer who placed the order."""
        if obj.crave_student_profile:
            gender = obj.crave_student_profile.gender
            color = "#d63384" if gender == "Female" else "#0d6efd"
            return format_html('<b style="color: {};">{}</b>', color, gender)
        return "-"

@admin.register(CampusBatch)
class CampusBatchAdmin(admin.ModelAdmin):
    """Specialized Admin for Campus Logistics with Gender visibility."""
    def get_queryset(self, request):
        return super().get_queryset(request).filter(courier__courier_category='CAMPUS')

    # LIST VIEW: Shows Courier Name and Gender FIRST, then Batch metrics
    list_display = [
        'get_courier_name', 
        'get_courier_gender', 
        'batch_id', 
        'get_total_packs', 
        'get_location_tag',
        'get_unique_orders', 
        'status', 
        'created_at'
    ]

    ordering = ('-created_at',)
    
    list_filter = ['status', 'courier__gender']
    
    # LOCKING: Batch ID, Courier, and Assignment Status are READ-ONLY (Managed by Engine)
    readonly_fields = ['batch_id', 'bag_location_tag', 'created_at']
    
    # DETAIL VIEW: Injects the editable orders table
    inlines = [UniversityOrderInline]

    # --- Display Methods for Courier Information ---
    @admin.display(description="📍 Bag Location (Anchor)")
    def get_location_tag(self, obj):
        """Translates IDs into Names by checking both string 'value' and integer 'id'."""
        if not obj.bag_location_tag:
            return format_html('<span style="color: #999;">No Anchor</span>')

        loc_val = obj.bag_location_tag.get('location_id')
        build_val = obj.bag_location_tag.get('building_id')

        from luxa_crave.models import Campus_Location, Location_Building
        
        # --- SMART LOOKUP ---
        # 1. Try looking up by the 'value' field (the string)
        building = Location_Building.objects.filter(value=build_val).first()
        location = Campus_Location.objects.filter(value=loc_val).first()

        # 2. If that fails, try looking up by the actual database Primary Key (id)
        if not building and str(build_val).isdigit():
            building = Location_Building.objects.filter(id=int(build_val)).first()
        if not location and str(loc_val).isdigit():
            location = Campus_Location.objects.filter(id=int(loc_val)).first()

        # --- OUTPUT ---
        if building:
            return format_html(
                '<div style="line-height: 1.2;">'
                '<b style="color: #666; font-size: 10px;">{}</b><br>'
                '<span style="background: #fff3e0; color: #e65100; padding: 2px 8px; '
                'border-radius: 10px; font-weight: bold; border: 1px solid #ffe0b2;">'
                '🏗️ {}</span>'
                '</div>', 
                location.name if location else "Campus", 
                building.name
            )
        
        return format_html('<code style="color:red;">ID Mismatch: {}</code>', build_val)
    
    @admin.display(description="Courier Assigned")
    def get_courier_name(self, obj):
        if obj.courier:
            return obj.courier.user_account.username
        return format_html('<span style="color: #dc3545; font-weight: bold;">🔴 Unassigned</span>')

    @admin.display(description="Courier Gender")
    def get_courier_gender(self, obj):
        if obj.courier:
            gender = obj.courier.gender
            color = "#d63384" if gender == "Female" else "#0d6efd"
            return format_html('<b style="color: {};">{}</b>', color, gender)
        return "-"

    # --- Logistics Metric Calculations ---

    @admin.display(description="Total Physical Packs")
    def get_total_packs(self, obj):
        # Sums the packs from University_Order related_name='campus_orders'
        orders = obj.campus_orders.all()
        return sum(o.total_physical_packs for o in orders) if orders else 0

    @admin.display(description="Total Unique Orders")
    def get_unique_orders(self, obj):
        return obj.campus_orders.count()
    




    # ==========================================
# 5.5 STANDARD DELIVERY BATCH (MIRROR OF CAMPUS)
# ==========================================

class LUXAOrderInline(admin.TabularInline):
    """Inline for Standard Logistics Orders allowing status edits."""
    model = LUXAOrder
    
    # Standard orders use 'order_id' as the primary reference
    fields = [
        'order_id', 
        'status', 
        'delivery_type', 
        'total_price', 
        'created_at'
    ]
    
    # Protect core logistics data, only allow manual status overrides
    readonly_fields = [
        'order_id', 
        'delivery_type', 
        'total_price', 
        'created_at'
    ]
    
    extra = 0
    show_change_link = True
    fk_name = 'batch' # Links to DeliveryBatch

@admin.register(StandardBatch)
class StandardBatchAdmin(admin.ModelAdmin):
    """Mirror of CampusBatch for the Standard Courier Network."""
    
    def get_queryset(self, request):
        # Exclude CAMPUS category to only show Standard network batches
        return super().get_queryset(request).exclude(courier__courier_category='CAMPUS')

    # LIST VIEW: Organized like Campus (Courier Info -> ID -> Metrics -> Status)
    list_display = [
        'get_courier_name', 
        'get_courier_gender', 
        'batch_id', 
        'get_unique_orders', 
        'status', 
        'created_at'
    ]

    ordering = ('-created_at',)
    
    list_filter = ['status', 'courier__gender']
    
    # Managed by the Selection Gate / Decision Engine
    readonly_fields = ['batch_id', 'courier', 'created_at']
    
    # DETAIL VIEW: Injects the LUXAOrder table
    inlines = [LUXAOrderInline]

    @admin.display(description="Courier Assigned")
    def get_courier_name(self, obj):
        if obj.courier:
            return obj.courier.user_account.username
        return format_html('<span style="color: #dc3545; font-weight: bold;">🔴 Unassigned</span>')

    @admin.display(description="Courier Gender")
    def get_courier_gender(self, obj):
        if obj.courier:
            gender = obj.courier.gender
            color = "#d63384" if gender == "Female" else "#0d6efd"
            return format_html('<b style="color: {};">{}</b>', color, gender)
        return "-"

    @admin.display(description="Orders in Batch")
    def get_unique_orders(self, obj):
        # DeliveryBatch related_name for LUXAOrder is 'orders'
        return obj.orders.count()
    

# ==========================================
# 6. DUMP ADMINS (Preserved)
# ==========================================

@admin.register(StandardDump)
class StandardDumpAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(assigned_courier__user_account__username="Dumped_Standard")
    list_display = ['order_id', 'status', 'delivery_type', 'total_price', 'created_at']
    def has_add_permission(self, request): return False

    ordering = ('-created_at',)

@admin.register(CampusDump)
class CampusDumpAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            engine_view__assigned_campus_courier__user_account__username__in=["Dumped_Campus_Female_Orders", "Dumped_Campus_Male_Orders"]
        )
    list_display = ['order_id', 'total_physical_packs_db', 'get_dump_name', 'status', 'order_date']

    ordering = ('-order_date',)
    
    @admin.display(description="Dump Source")
    def get_dump_name(self, obj):
        engine_order = getattr(obj, 'engine_view', None)
        if engine_order and engine_order.assigned_campus_courier:
            name = engine_order.assigned_campus_courier.user_account.username
            color = "#d63384" if "Female" in name else "#0d6efd"
            return format_html('<b style="color: {};">{}</b>', color, name)
        return "Unassigned"
    


    from django.utils import timezone
# Make sure to import Courier_Exemption_Request at the top of your admin.py!

@admin.register(Courier_Exemption_Request)
class CourierExemptionAdmin(admin.ModelAdmin):
    list_display = ('courier', 'target_date', 'status', 'reason_preview', 'created_at')
    list_filter = ('status', 'target_date')
    search_fields = ('courier__user_account__username', 'courier__user_account__email', 'reason')
    
    # These are the custom buttons that will appear at the top of the list!
    actions = ['approve_exemptions', 'reject_exemptions']

    def reason_preview(self, obj):
        """Truncates long excuses so the table looks clean."""
        return obj.reason[:50] + '...' if len(obj.reason) > 50 else obj.reason
    reason_preview.short_description = "Excuse"

    @admin.action(description="✅ APPROVE selected exemptions")
    def approve_exemptions(self, request, queryset):
        # Instantly updates all selected rows to approved
        updated = queryset.update(status='approved', reviewed_at=timezone.now())
        self.message_user(request, f"Successfully approved {updated} shift exemptions.")

    @admin.action(description="❌ REJECT selected exemptions")
    def reject_exemptions(self, request, queryset):
        # Instantly updates all selected rows to rejected
        updated = queryset.update(status='rejected', reviewed_at=timezone.now())
        self.message_user(request, f"Successfully rejected {updated} shift exemptions.")


    # Make sure Courier_Shift_Roster is imported at the top of your file!

@admin.register(Courier_Shift_Roster)
class CourierShiftRosterAdmin(admin.ModelAdmin):
    # 1. The Columns: Shows exactly when they are working and who they are
    list_display = ('shift_date', 'start_time', 'end_time', 'courier', 'is_auto_snapped', 'created_at')
    
    # 2. The Filter Sidebar: This gives you the control you asked for!
    # You can click "Tomorrow" and "14:00" to instantly see everyone working at 2 PM.
    list_filter = ('shift_date', 'start_time', 'is_auto_snapped')
    
    # 3. Search Bar: Instantly find a specific courier's schedule
    search_fields = ('courier__user_account__username', 'courier__user_account__first_name', 'courier__user_account__last_name')
    
    # 4. THE MAGIC GROUPING: 
    # This forces the table to group everything by Date first, and then perfectly group them by Time.
    # All 2:00 PM workers will be clustered together, followed by 3:00 PM, etc.
    ordering = ('-shift_date', 'start_time', 'courier')
    
    # Optional: Prevents you from accidentally editing a shift and breaking the strict hour-block logic
    readonly_fields = ('created_at',)
    
    # Makes the list longer so you can see the whole day at a glance
    list_per_page = 100

# ==========================================
# 7. SYSTEM CORE
# ==========================================
admin.site.register(CourierAccessLog)
admin.site.register(CourierEngine)


@admin.register(BannedEmail)
class BannedEmailAdmin(admin.ModelAdmin):
    list_display = ('email', 'reason', 'banned_at')
    search_fields = ('email', 'reason')
    list_filter = ('banned_at',)

@admin.register(Courier_Telemetry_Log)
class CourierTelemetryLogAdmin(admin.ModelAdmin):
    # 1. What columns show up in the main table
    list_display = (
        'get_courier_name', 
        'event_trigger', 
        'old_score', 
        'get_score_delta', 
        'new_score', 
        'timestamp'
    )
    
    # 2. Filters on the right sidebar
    list_filter = ('event_trigger', 'timestamp')
    
    # 3. Search bar (Search by username, email, or exact batch ID)
    search_fields = (
        'courier__user_account__username', 
        'courier__user_account__email', 
        'batch__batch_id'
    )
    
    # 4. Makes the page strictly READ-ONLY. (Flight recorders shouldn't be edited)
    readonly_fields = (
        'courier', 'batch', 'event_trigger', 
        'c_ratio_logged', 'e_batch_logged', 
        'bonus_points_applied', 'penalty_points_applied', 
        'old_score', 'new_score', 'calculation_details', 'timestamp'
    )
    
    # Adds a nice date drill-down menu at the top of the list
    date_hierarchy = 'timestamp'
    
    list_per_page = 50

    # Organize the detail view cleanly
    fieldsets = (
        ('Event Context', {
            'fields': ('courier', 'batch', 'event_trigger', 'timestamp')
        }),
        ('The Master Equation Variables', {
            'fields': ('c_ratio_logged', 'e_batch_logged', 'bonus_points_applied', 'penalty_points_applied'),
            'description': 'The exact variables injected into the engine at the millisecond of calculation.'
        }),
        ('The Outcome', {
            'fields': ('old_score', 'new_score', 'calculation_details')
        }),
    )

    def get_courier_name(self, obj):
        return obj.courier.user_account.username
    get_courier_name.short_description = 'Courier'
    get_courier_name.admin_order_field = 'courier__user_account__username'

    def get_score_delta(self, obj):
        """Creates a color-coded visual indicator of the score change"""
        delta = obj.new_score - obj.old_score
        if delta > 0:
            return format_html('<span style="color: #16a34a; font-weight: bold;">+{}</span>', round(delta, 1))
        elif delta < 0:
            return format_html('<span style="color: #dc2626; font-weight: bold;">{}</span>', round(delta, 1))
        return format_html('<span style="color: #6b7280; font-weight: bold;">0.0</span>')
    get_score_delta.short_description = 'Delta'

    # Remove the "Add" button so admins can't fake telemetry logs
    def has_add_permission(self, request):
        return False