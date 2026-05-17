from django.contrib import admin
import json
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Campus_Location,
    Default_Proxy_Settings,
    Location_Building,
    University_Profile,
    Crave_Student_Profile,
    University_Outlet,
    University_Outlet_Section,
    Section_Product,
    Pack_Size_Config,
    University_Order,
    Campus_Engine_Order,
    Order_Pack,
    Order_Pack_Item,
    Campus_Pack_Preset,
    Campus_Pack_Preset_Item
)
from django import forms
from django.core.exceptions import ValidationError

# --- 1. UNIVERSITY & OUTLET INFRASTRUCTURE ---

class Campus_LocationInline(admin.TabularInline):
    model = Campus_Location
    extra = 0

class Location_BuildingInline(admin.TabularInline):
    model = Location_Building
    extra = 0

class SectionProductInline(admin.TabularInline):
    model = Section_Product
    extra = 0

class SectionProductAdminForm(forms.ModelForm):
    class Meta:
        model = Section_Product
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        # Use .get() to avoid KeyErrors if a field is missing from the layout
        is_strange = cleaned_data.get("is_strange", False)
        strange_string = cleaned_data.get("strange_value", "")

        # 1. Validation: Strange checked but no name
        if is_strange and not strange_string:
            self.add_error('strange_value', "Required when 'Is Strange' is active.")

        # 2. Validation: Name exists but Strange not checked
        elif not is_strange and strange_string:
            # Instead of failing, we can just clear the string automatically
            cleaned_data['strange_value'] = ""
            
        return cleaned_data


@admin.register(University_Profile)
class UniversityProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'on_break', 'campus_call_sign', 'view_outlets_link', 'weekday_open', 'weekday_close', 'weekend_open', 'weekend_close')
    search_fields = ('name', 'campus_call_sign', 'profile_id')
    readonly_fields = ('profile_id',)
    list_editable = ('on_break',)  # Allows quick toggling of break status from the list view
    inlines = [Campus_LocationInline]

    def view_outlets_link(self, obj):
        count = obj.university_outlet_set.count()
        url = reverse("admin:luxa_crave_university_outlet_changelist") + f"?university__id__exact={obj.id}"
        return format_html('<a href="{}">{} Outlets</a>', url, count)
    view_outlets_link.short_description = "Outlets"

@admin.register(Campus_Location)
class CampusLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'university',)
    list_filter = ('university',)
    search_fields = ('name', 'university__name')

    inlines = [Location_BuildingInline]

class DefaultProxyInline(admin.TabularInline):
    model = Default_Proxy_Settings
    extra = 0

@admin.register(Crave_Student_Profile)
class CraveStudentProfileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'default_university')
    list_filter = ('default_university',)
    list_select_related = ('customer', 'customer__user_account', 'default_university')
    search_fields = ('customer__user_account__email', 'customer__first_name', 'customer__last_name')

    list_per_page = 20

    inlines = [DefaultProxyInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'default_university')
        }),
        ('Student Primary Address', {
            'fields': ('campus_address', 'campus_building', 'room_number')
        }),
        ('Proxy Settings', {
            'fields': ('proxy_enabled',),
            'description': 'Enable or disable proxy ordering for this student. If enabled, default proxy settings will be applied to their orders unless overridden.'
        }),
    )

    def customer_link(self, obj):
        if obj.customer:
            # Assumes your MAIN app customer admin is accessible here
            url = reverse("admin:MAIN_customer_change", args=[obj.customer.id])
            return format_html('<a href="{}">{}</a>', url, obj.customer.full_name)
        return "-"
    customer_link.short_description = "Customer"

@admin.register(University_Outlet)
class UniversityOutletAdmin(admin.ModelAdmin):
    list_display = ('name', 'university', 'view_sections_link', 'availability_status', 'time_open', 'time_closed')
    list_editable = ('availability_status',)
    list_filter = ('university', 'availability_status')
    list_select_related = ('university',)
    search_fields = ('name', 'university__name')

    def view_sections_link(self, obj):
        count = obj.sections.count()
        url = reverse("admin:luxa_crave_university_outlet_section_changelist") + f"?outlet__id__exact={obj.id}"
        return format_html('<a href="{}">{} Sections</a>', url, count)
    view_sections_link.short_description = "Sections"

@admin.register(University_Outlet_Section)
class UniversityOutletSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'outlet', 'view_products_link')
    list_filter = ('outlet__university', 'outlet')
    list_select_related = ('outlet',)
    search_fields = ('name',)

    inlines = [SectionProductInline]

    def view_products_link(self, obj):
        count = obj.products.count()
        url = reverse("admin:luxa_crave_section_product_changelist") + f"?section__id__exact={obj.id}"
        return format_html('<a href="{}">{} Products</a>', url, count)
    view_products_link.short_description = "Products"





@admin.register(Section_Product)
class SectionProductAdmin(admin.ModelAdmin):
    form = SectionProductAdminForm # Attach the validation form
    # --- UPDATED LIST DISPLAY ---
    # Added is_a_soup, need_soup, and not_ordered_alone to the columns
    

    def get_changelist_form(self, request, **kwargs):
        kwargs['form'] = SectionProductAdminForm
        return super().get_changelist_form(request, **kwargs)
    
    list_display = (
        'product_name', 'section', 'unit_price', 'stock_quantity', 
        'availability_status', 'last_updated_availability', 'is_strange', 'strange_value', 'is_a_soup', 'need_soup', 
        'not_ordered_alone', 'requires_pack', 'comes_with_pack', 'filling_value'
    )
    
    # --- UPDATED LIST EDITABLE ---
    # This allows you to toggle all logic flags directly from the list view
    list_editable = (
        'stock_quantity', 'availability_status', 'is_strange', 'strange_value','is_a_soup', 
        'need_soup', 'not_ordered_alone', 'requires_pack', 
        'comes_with_pack', 'filling_value'
    )

    list_filter = ('is_a_soup', 'need_soup', 'not_ordered_alone', 'availability_status', 'section__outlet', 'section')
    list_select_related = ('section',)
    search_fields = ('product_name', 'strange_value', 'section__name')

    list_per_page = 20
    
    readonly_fields = ('image_preview',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'product_name', 
                'section', 
                'description',
                'product_image', 
                'image_preview',
                'is_a_soup',           
                'need_soup',
                'not_ordered_alone' 
            )
        }),
        ('Pricing & Inventory', {
            'fields': (
                'unit_price', 
                'unit_of_measure', 
                'stock_quantity', 
                'availability_status'
            )
        }),
        ('Packaging Rules', {
            'fields': (
                'is_strange',
                'strange_value',
                'requires_pack', 
                'comes_with_pack',
                'filling_value',
            ),
            'description': 'Configure how this item should be packaged for delivery.'
        }),
    )

    def image_preview(self, obj):
        if obj and obj.product_image:
            return format_html(
                '<div style="margin-top: 10px;">'
                '<img src="{}" style="max-height: 200px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);" />'
                '</div>', 
                obj.product_image.url
            )
        return format_html('<span style="color: #888; font-style: italic;">No image uploaded yet</span>')
    
    image_preview.short_description = 'Image Preview'

# --- 2. PACK SIZING & TEMPLATES ---

@admin.register(Pack_Size_Config)
class PackSizeConfigAdmin(admin.ModelAdmin):
    list_display = ('get_size_name_display', 'base_price', 'availability','max_capacity')
    list_editable = ('base_price', 'max_capacity', 'availability')


# --- 3. THE "ORDER > PACK > ITEM" HIERARCHY ---

class OrderPackItemInline(admin.TabularInline):
    model = Order_Pack_Item
    extra = 0
    autocomplete_fields = ['product'] # Speeds up loading if you have thousands of products

class OrderPackInline(admin.TabularInline):
    model = Order_Pack
    extra = 0
    readonly_fields = ('total_pack_cost', 'total_item_cost')
    fields = ('pack_size', 'status', 'influence_value', 'total_item_cost', 'total_pack_cost')
    show_change_link = True # Adds a link to edit the specific pack and see its items

@admin.register(Order_Pack)
class OrderPackAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'pack_size', 'status', 'get_total_pack_cost', 'created_at')
    list_filter = ('status', 'pack_size')
    list_select_related = ('order', 'order__customer', 'order__customer__user_account', 'pack_size')
    inlines = [OrderPackItemInline]
    readonly_fields = ('get_total_pack_cost', 'get_total_item_cost')

    list_per_page = 30

    def order_link(self, obj):
        url = reverse("admin:luxa_crave_university_order_change", args=[obj.order.order_id])
        return format_html('<a href="{}">Order {}</a>', url, str(obj.order.order_id)[:8])
    order_link.short_description = "Parent Order"

    def get_total_pack_cost(self, obj):
        return f"₦{obj.total_pack_cost:,.2f}"
    get_total_pack_cost.short_description = "Total Cost"

    def get_total_item_cost(self, obj):
        return f"₦{obj.total_item_cost:,.2f}"
    get_total_item_cost.short_description = "Items Subtotal"

@admin.register(University_Order)
class UniversityOrderAdmin(admin.ModelAdmin):
    list_display = ('short_id', 'customer', 'status', 'get_delivery_fee', 'get_total_cost', 'order_date', 'total_physical_packs_db')
    list_filter = ('status', 'order_date')
    list_select_related = ('customer', 'customer__user_account')
    search_fields = ('order_id', 'customer__user_account__email', 'customer__first_name')

    ordering = ('-order_date',)
    
    # We add our two new custom HTML fields to the readonly list
    readonly_fields = ('delivery_details_html', 'order_manifest_html', 'get_delivery_fee', 'get_total_cost')
    
    inlines = [OrderPackInline] # Keep this if you still want to edit basic pack info

    list_per_page = 30

    # Organize the admin page into clean, readable sections
    fieldsets = (
        ('Order Tracking & Status', {
            'fields': ('status', 'get_total_cost', 'get_delivery_fee', 'used_daily_promo', 'wait_fee'),
        }),
        ('Delivery & Customer Routing', {
            'fields': ('delivery_details_html',),
        }),
        ('Complete Order Manifest', {
            'fields': ('order_manifest_html',),
            'description': 'A complete tabular breakdown of every pack, multiplier, and item inside this order.'
        }),
        ('Advanced / Manual Overrides', {
            'fields': ('location_category', 'building', 'building_block', 'room_number', 'extra_info', 'batch', 'total_physical_packs_db', 'terminal_payload'),
            'classes': ('collapse',), # Hides the raw data by default to keep it clean
        }),
    )

    def short_id(self, obj):
        return str(obj.order_id)[:8]
    short_id.short_description = "ID"

    def get_delivery_fee(self, obj):
        return f"₦{obj.delivery_fee:,.2f}"
    get_delivery_fee.short_description = "Delivery Fee"

    def get_total_cost(self, obj):
        return f"₦{obj.total_order_cost:,.2f}"
    get_total_cost.short_description = "Total Cost"

    # --- 1. CUSTOM PROXY & ROUTING DISPLAY ---
    def delivery_details_html(self, obj):
        customer = obj.customer
        crave_profile = getattr(customer, 'crave_profile', None)

        # --- NEW: SAFELY FETCH THE OUTLET ---
        outlet_name = "Unknown Outlet"
        first_pack = obj.packs.first()
        if first_pack:
            first_item = first_pack.items.first()
            if first_item and getattr(first_item, 'product', None) and getattr(first_item.product, 'section', None):
                outlet_name = first_item.product.section.outlet.name
        # ------------------------------------

        use_proxy = crave_profile and crave_profile.proxy_enabled and hasattr(crave_profile, 'default_proxy')

        # THE FIX: Added 'color: #000000;' to the master wrapper so all text defaults to black
        html = f"<div style='font-size: 14px; line-height: 1.6; color: #ff00ff;'>"
        html += f"<strong>Customer:</strong> {customer.first_name} {customer.last_name} ({customer.user_account.email})<br>"
        
        if use_proxy:
            proxy = crave_profile.default_proxy
            # THE FIX: Added explicit 'color: #000000;' inside the pink box
            html += f"<div style='margin-top: 10px; padding: 10px; background-color: #fdf2f8; border-left: 4px solid #db2777; border-radius: 4px; color: #000000;'>"
            html += f"<strong style='color: #db2777;'>🛡️ PROXY DELIVERY ENABLED</strong><br>"
            html += f"<strong>Proxy Name:</strong> {proxy.proxy_name}<br>"
            html += f"<strong>Proxy Gender:</strong> {proxy.proxy_gender.capitalize()}<br>"
            if proxy.proxy_seed_phrase_hash:
                html += f"<strong>Seed Phrase:</strong> <span style='font-family: monospace;'>{proxy.proxy_seed_phrase_hash}</span><br>"
            html += f"</div>"
        else:
            # THE FIX: Added explicit 'color: #000000;' inside the green box
            html += f"<div style='margin-top: 10px; padding: 10px; background-color: #f0fdf4; border-left: 4px solid #16a34a; border-radius: 4px; color: #000000;'>"
            html += f"<strong style='color: #16a34a;'>👤 DIRECT TO CUSTOMER</strong>"
            html += f"</div>"

        location = obj.location_category.name if obj.location_category else 'N/A'
        building = obj.building.name if obj.building else 'N/A'
        html += f"<div style='margin-top: 10px; color: #ff00ff;'>"

        # --- NEW: DISPLAY THE OUTLET ---
        html += f"<strong>Pickup Outlet:</strong> <span style='color: #2563eb; font-weight: bold;'>{outlet_name}</span><br>"
        html += f"<strong>Destination:</strong> {location}, {building} - Room {obj.room_number or 'N/A'}<br>"
        if obj.extra_info:
            html += f"<strong>Instructions:</strong> <span style='color: #ea580c;'>{obj.extra_info}</span>"
        html += "</div></div>"

        return format_html(html)
    delivery_details_html.short_description = "Customer & Delivery Routing"


    def save_model(self, request, obj, form, change):
        # 1. Save the University_Order normally first
        super().save_model(request, obj, form, change)
        
        # 2. Sync the Campus_Engine_Order
        if hasattr(obj, 'engine_view') and obj.engine_view:
            from django.utils import timezone
            engine = obj.engine_view
            terminal_statuses = ['delivered', 'completed', 'cancelled', 'refunded', 'pending_cancellation']
            
            if obj.status in terminal_statuses:
                # Map standard 'delivered' to the engine's 'completed' status
                if obj.status == 'delivered':
                    engine.status = 'completed'
                else:
                    # Cancelled, dumped, etc.
                    engine.status = obj.status
                
                # Stamp the completion time!
                if engine.status == 'completed' and not engine.completed_at:
                    engine.completed_at = timezone.now()
                
                engine.save(update_fields=['status', 'completed_at'])

        # 3. 🎯 THE BATCH BURN TRIGGER
        # Reach into the couriers model and trigger the batch check
        if getattr(obj, 'batch', None):
            try:
                obj.batch.check_batch_burn()
            except Exception as e:
                import logging
                logging.getLogger('luxa_brain').error(f"Admin Batch Burn Trigger Failed: {e}")

    # --- 2. CUSTOM NESTED TABLE FOR PACKS & ITEMS ---
    def order_manifest_html(self, obj):
        if not obj.packs.exists():
            return "<span style='color: #000000;'>No packs attached to this order.</span>"

        # THE FIX: Added explicit 'color: #000000;' to the master table and all header texts
        html = """
        <table style="width: 100%; border-collapse: collapse; text-align: left; background: white; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; color: #000000;">
            <thead>
                <tr style="background-color: #f3f4f6; border-bottom: 2px solid #d1d5db;">
                    <th style="padding: 12px; color: #ff00ff; font-weight: bold;">Pack Size</th>
                    <th style="padding: 12px; color: #ff00ff; font-weight: bold;">Multiplier</th>
                    <th style="padding: 12px; color: #ff00ff; font-weight: bold;">Items Included</th>
                    <th style="padding: 12px; color: #ff00ff; font-weight: bold;">Surcharges</th>
                    <th style="padding: 12px; color: #ff00ff; font-weight: bold; text-align: right;">Total Pack Cost</th>
                </tr>
            </thead>
            <tbody>
        """

        for pack in obj.packs.all():
            pack_name = pack.pack_size.get_size_name_display() if pack.pack_size else "Loose Bundle (No Pack)"
            
            # THE FIX: Explicitly forcing list items to be black
            items_list = "".join([
                f"<li style='margin-bottom: 4px; color: #000000;'><strong>{item.quantity}x</strong> {item.product.product_name}</li>" 
                for item in pack.items.all()
            ])
            
            html += f"""
            <tr style="border-bottom: 1px solid #e5e7eb; background-color: white;">
                <td style="padding: 12px; font-weight: 600; color: #000000;">{pack_name}</td>
                <td style="padding: 12px;"><span style="background: #dbeafe; color: #000000; padding: 2px 8px; border-radius: 12px; font-weight: bold; font-size: 12px;">x{pack.multiplier}</span></td>
                <td style="padding: 12px;"><ul style="margin: 0; padding-left: 20px; color: #000000; font-size: 13px;">{items_list}</ul></td>
                <td style="padding: 12px; color: #991b1b; font-size: 13px; font-weight: bold;">₦{pack.pack_surcharge:,.2f}</td>
                <td style="padding: 12px; text-align: right; font-weight: bold; color: #065f46;">₦{pack.total_pack_cost:,.2f}</td>
            </tr>
            """

        html += "</tbody></table>"
        return format_html(html)
    order_manifest_html.short_description = "Items Breakdown"

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        order = form.instance
        if order.status != 'ordering_mode':
            order.save()

@admin.register(Campus_Engine_Order)
class CampusEngineOrderAdmin(admin.ModelAdmin):
    list_display = ('get_order_number', 'status', 'assigned_campus_courier', 'get_customer', 'get_total_packs', 'assigned_at', 'in_transit_at', 'completed_at')
    list_filter = ('status',)
    list_editable = ('status',)  # Allows quick status overrides from the list view

    list_per_page = 30
    
    # Allows searching by the parent order number or the courier's username/email
    search_fields = (
        'raw_order__order_id', 
        'raw_order__order_number', 
        'assigned_campus_courier__user_account__username',
        'raw_order__customer__first_name',
        'raw_order__customer__last_name'
    )
    
    # Prevents loading thousands of records in a standard dropdown
    raw_id_fields = ('raw_order', 'assigned_campus_courier') 
    
    readonly_fields = ('engine_payload_pretty', 'display_data_preview')

    fieldsets = (
        ('Order Tracking & Assignment', {
            'fields': ('raw_order', 'status', 'assigned_campus_courier')
        }),
        ('Machine Interface Data (Read-Only)', {
            'fields': ('engine_payload_pretty', 'display_data_preview'),
            'classes': ('collapse',),
            'description': 'These fields are auto-generated JSON objects used by the external logistics engine and frontend UI.'
        }),
    )

    def get_order_number(self, obj):
        return obj.raw_order.order_number
    get_order_number.short_description = 'Order Number'
    get_order_number.admin_order_field = 'raw_order__order_number'

    def get_customer(self, obj):
        if obj.raw_order and obj.raw_order.customer:
            return f"{obj.raw_order.customer.first_name} {obj.raw_order.customer.last_name}"
        return 'Unknown'
    get_customer.short_description = 'Customer'

    def get_total_packs(self, obj):
        return obj.raw_order.total_physical_packs_db
    get_total_packs.short_description = 'Total Packs'

    def engine_payload_pretty(self, obj):
        """Pretty-prints the JSON payload saved in the database."""
        if obj.engine_payload:
            pretty_json = json.dumps(obj.engine_payload, indent=4)
            return format_html(
                '<pre style="background-color: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; line-height: 1.4;">{}</pre>', 
                pretty_json
            )
        return "-"
    engine_payload_pretty.short_description = "Engine Payload (Database JSON)"

    def display_data_preview(self, obj):
        """Shows the dynamically generated dictionary that the UI templates use."""
        try:
            data = obj.display_data
            # default=str handles UUIDs or custom objects that aren't natively JSON serializable
            pretty_json = json.dumps(data, indent=4, default=str) 
            return format_html(
                '<pre style="background-color: #f8f9fa; color: #212529; border: 1px solid #e9ecef; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; line-height: 1.4;">{}</pre>', 
                pretty_json
            )
        except Exception as e:
            return format_html('<span style="color: red; font-weight: bold;">Error rendering display data: {}</span>', str(e))
    display_data_preview.short_description = "UI Template Data (Live Preview)"    

# --- 4. CAMPUS PRESETS ---

class CampusPackPresetItemInline(admin.TabularInline):
    """Allows viewing and editing of the items inside a preset from the admin panel."""
    model = Campus_Pack_Preset_Item
    extra = 0
    autocomplete_fields = ['product']  # Adds a searchable dropdown for products

@admin.register(Campus_Pack_Preset)
class CampusPackPresetAdmin(admin.ModelAdmin):
    list_display = ('preset_name', 'get_customer_name', 'outlet', 'pack_size', 'get_current_total_price', 'created_at')
    list_filter = ('outlet', 'pack_size', 'created_at')
    
    # Allows searching by preset name or the customer's real name/email
    search_fields = (
        'preset_name', 
        'customer__customer__first_name', 
        'customer__customer__last_name', 
        'customer__customer__user_account__email'
    )
    
    inlines = [CampusPackPresetItemInline]
    readonly_fields = ('get_current_total_price',)

    fieldsets = (
        ('Preset Details', {
            'fields': ('customer', 'outlet', 'preset_name', 'pack_size')
        }),
        ('Live Valuation', {
            'fields': ('get_current_total_price',),
            'description': 'This total is calculated dynamically based on current vendor prices.'
        }),
    )

    def get_customer_name(self, obj):
        """Fetches the actual name from the deeply linked MAIN.Customer model."""
        if obj.customer and obj.customer.customer:
            return f"{obj.customer.customer.first_name} {obj.customer.customer.last_name}"
        return "Unknown Customer"
    get_customer_name.short_description = "Customer"

    def get_current_total_price(self, obj):
        """Formats the dynamically calculated price property."""
        return f"₦{obj.current_total_price:,.2f}"
    get_current_total_price.short_description = "Current Total Price"