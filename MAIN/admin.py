from django.contrib import admin
from .models import (
    Vendor, Customer, Category, Product, ProductImage,
    Order, OrderItem, Cart, CartItem, Wishlist, WishlistItem, Notification,
    ProcessedProductMedia, ProductTargetMesh, ProductColor, AdminNotification, 
    UserNotification, ProductVariant, ProductVariantImage, DraftOrder, 
    DraftOrderItem, EligibilityStagingArea, MasterOrder, Product3DTexture,
    KYCVerification
)
from luxa_crave.models import Crave_Student_Profile
from django.forms.widgets import TextInput
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
import os
# Register your models here.

# 1. Unregister the default User admin
admin.site.unregister(User)

# 2. Create your custom User Admin
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Optional: Limit rows per page (Pagination)
    list_per_page = 20 

    def get_queryset(self, request):
        qs = super().get_queryset(request)        
        return qs



# Register your models here.

# ============================================================================
# INLINE ADMIN CLASSES (Define all inlines before use)
# ============================================================================

class ProductImageInline(admin.StackedInline):
    """Inline admin for ProductImage - 3D model images"""
    model = ProductImage
    extra = 0
    fields = [
        'orthographicfront', 
        'orthographicleft', 
        'orthographicright', 
        'orthographicback', 
        'orthographictop', 
        'orthographicbottom', 
        'perspectivefront',
        'perspectiveback',
        'video360',
        'info_text', 
        'order',
    ]
    classes = ['collapse']
    verbose_name = "3D Model Image"
    verbose_name_plural = "3D Model Images"

class ProcessedProductMediaInline(admin.StackedInline):
    """Inline admin for ProcessedProductMedia - Final processed images"""
    model = ProcessedProductMedia
    extra = 0
    fields = [
        'final_main_image',
        'final_thumbimg1',
        'final_thumbimg2',
        'final_thumbimg3',
        'final_thumbimg4',
        'final_thumbimg5',
    ]
    classes = ['collapse']
    verbose_name = "Processed Media"
    verbose_name_plural = "Processed Media"

class ProductVariantInline(admin.TabularInline):
    """Inline admin for ProductVariant - Colors, sizes, etc."""
    model = ProductVariant
    extra = 1
    fields = ['variant_type', 'variant_value', 'is_available']
    verbose_name = "Variant"
    verbose_name_plural = "Variants (Colors, Sizes, etc.)"

class ProductVariantImageInline(admin.StackedInline):
    """Inline admin for ProductVariantImage - Images for each variant"""
    model = ProductVariantImage
    extra = 0
    fields = [
        'variant',
        'main_image',
        'thumbnail1',
        'thumbnail2',
        'thumbnail3',
        'thumbnail4',
        'thumbnail5',
        'order',
    ]
    classes = ['collapse']
    verbose_name = "Variant Image Set"
    verbose_name_plural = "Variant Image Sets"

    # for showing only the product's variants
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "variant":
            # 1. Try to get the Product ID from the URL (e.g. /admin/MAIN/product/123/change/)
            if request.resolver_match and request.resolver_match.kwargs.get('object_id'):
                product_id = request.resolver_match.kwargs.get('object_id')
                # 2. Filter the queryset to show ONLY variants linked to this specific product
                kwargs["queryset"] = ProductVariant.objects.filter(product_id=product_id)
            else:
                # 3. If we are on the "Add Product" page (no ID yet), show an empty list
                # (You can't link a variant to a product that doesn't exist yet)
                kwargs["queryset"] = ProductVariant.objects.none()
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class ProductTargetMeshInline(admin.TabularInline):
    """Inline admin for ProductTargetMesh - For 3D color customization"""
    model = ProductTargetMesh
    extra = 1
    fields = ['name']
    verbose_name = "Target Mesh"
    verbose_name_plural = "Target Meshes (for 3D color customization)"

class ProductColorInline(admin.TabularInline):
    """Inline admin for ProductColor - Colors for each mesh"""
    model = ProductColor
    extra = 1
    fields = ['target_mesh', 'name', 'color_hex']
    verbose_name = "Mesh Color"
    verbose_name_plural = "Mesh Colors"

class Product3DTextureInline(admin.TabularInline):
    model = Product3DTexture
    extra = 1

    # for showing only the product's variants
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "variant":
            # 1. Try to get the Product ID from the URL (e.g. /admin/MAIN/product/123/change/)
            if request.resolver_match and request.resolver_match.kwargs.get('object_id'):
                product_id = request.resolver_match.kwargs.get('object_id')
                # 2. Filter the queryset to show ONLY variants linked to this specific product
                kwargs["queryset"] = ProductVariant.objects.filter(product_id=product_id)
            else:
                # 3. If we are on the "Add Product" page (no ID yet), show an empty list
                # (You can't link a variant to a product that doesn't exist yet)
                kwargs["queryset"] = ProductVariant.objects.none()
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

# ============================================================================
# PRODUCT ADMIN (Main product management)
# ============================================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'vendor_link', 'category', 'price', 'stock_quantity', 'has_variants', 'is_approved', 'is_active', 'created_at']
    list_filter = ['has_variants', 'is_featured', 'is_available', 'is_approved', 'category', 'created_at']
    list_per_page = 30
    raw_id_fields = ('vendor',)
    search_fields = ['name', 'sku', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at', 'variants_link', 'target_meshes_link']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'sku', 'features', 'includeditems')
        }),
        ('Relationships', {
            'fields': ('vendor', 'category')
        }),
        ('Pricing', {
            'fields': ('price', 'compare_at_price')
        }),
        ('Images & Media', {
            'fields': ('main_image', 'model_3d_file')
        }),
        ('Inventory', {
            'fields': ('stock_quantity', 'is_available')
        }),
        ('Variants & Customization', {
            'fields': ('has_variants', 'is_color'),
            'description': 'has_variants: Enable if product has colors, sizes, etc. | is_color: Enable for 3D mesh color customization'
        }),
        ('Status', {
            'fields': ('is_featured', 'is_approved', 'is_active')
        }),
        ('Quick Links', {
            'fields': ('variants_link', 'target_meshes_link'),
            'classes': ('collapse',)
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_inlines(self, request, obj=None):
        """Dynamically show relevant inlines based on product configuration"""
        inlines = []
        
        # Always show processed media and 3D images
        inlines.append(ProcessedProductMediaInline)
        inlines.append(ProductImageInline)
        
        # Show variant-related inlines only if has_variants is True
        if obj and obj.has_variants:
            inlines.append(ProductVariantInline)
            inlines.append(ProductVariantImageInline)
            inlines.append(Product3DTextureInline)
        
        # Show target mesh inline only if is_color is True
        if obj and obj.is_color:
            inlines.append(ProductTargetMeshInline)
        
        return inlines

    def vendor_link(self, obj):
        """Create clickable link to vendor"""
        if obj.vendor:
            url = reverse('admin:MAIN_vendor_change', args=[obj.vendor.id])
            return format_html('<a href="{}">{}</a>', url, obj.vendor.business_name)
        return "-"
    vendor_link.short_description = "Vendor"
    vendor_link.admin_order_field = 'vendor__business_name'

    def variants_link(self, obj):
        """Create link to view all variants for this product"""
        if obj and obj.id:
            url = reverse('admin:MAIN_productvariant_changelist') + f'?product__id__exact={obj.id}'
            count = obj.variants.count()
            return format_html('<a href="{}">View {} Variant(s)</a>', url, count)
        return "Save product first"
    variants_link.short_description = "View Variants"

    def target_meshes_link(self, obj):
        """Create link to view all target meshes for this product"""
        if obj and obj.id:
            url = reverse('admin:MAIN_producttargetmesh_changelist') + f'?product__id__exact={obj.id}'
            count = obj.target_meshes.count()
            return format_html('<a href="{}">View {} Target Mesh(es)</a>', url, count)
        return "Save product first"
    target_meshes_link.short_description = "View Target Meshes"

# ============================================================================
# PRODUCT VARIANT ADMIN (Better organized with links)
# ============================================================================

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product_link', 'variant_type', 'variant_value', 'is_available', 'variant_images_link', 'created_at']
    list_filter = ['variant_type', 'is_available', 'created_at']
    search_fields = ['product__name', 'variant_value', 'variant_type']
    list_per_page = 25
    raw_id_fields = ('product',)
    list_select_related = ['product']

    def product_link(self, obj):
        """Create clickable link to product"""
        if obj.product:
            url = reverse('admin:MAIN_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = "Product"
    product_link.admin_order_field = 'product__name'

    def variant_images_link(self, obj):
        """Create link to view images for this variant"""
        if obj and obj.id:
            url = reverse('admin:MAIN_productvariantimage_changelist') + f'?variant__id__exact={obj.id}'
            count = obj.images.count()
            return format_html('<a href="{}">{} Image(s)</a>', url, count)
        return "-"
    variant_images_link.short_description = "Images"

# ============================================================================
# PRODUCT VARIANT IMAGE and PRODUCT VARIANT TEXTURES ADMIN
# ============================================================================

@admin.register(ProductVariantImage)
class ProductVariantImageAdmin(admin.ModelAdmin):
    list_display = ['product_link', 'variant_link', 'order', 'has_main_image', 'created_at']
    list_filter = ['variant__variant_type', 'created_at']
    search_fields = ['product__name', 'variant__variant_value']
    list_per_page = 25
    raw_id_fields = ('product', 'variant')
    list_select_related = ['product', 'variant']

    def product_link(self, obj):
        """Create clickable link to product"""
        if obj.product:
            url = reverse('admin:MAIN_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = "Product"
    product_link.admin_order_field = 'product__name'

    def variant_link(self, obj):
        """Create clickable link to variant"""
        if obj.variant:
            url = reverse('admin:MAIN_productvariant_change', args=[obj.variant.id])
            return format_html('<a href="{}">{}: {}</a>', url, obj.variant.variant_type, obj.variant.variant_value)
        return "-"
    variant_link.short_description = "Variant"
    variant_link.admin_order_field = 'variant__variant_type'

    def has_main_image(self, obj):
        """Check if main image exists"""
        return False if obj.main_image else False
    has_main_image.short_description = "Has Main Image"
    has_main_image.boolean = True

# ============================================================================
# PRODUCT TARGET MESH ADMIN (Better organized with links)
# ============================================================================

@admin.register(ProductTargetMesh)
class ProductTargetMeshAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_link', 'colors_count']
    list_filter = ['product']
    search_fields = ['name', 'product__name']
    inlines = [ProductColorInline]
    list_per_page = 25
    list_select_related = ['product']

    def product_link(self, obj):
        """Create clickable link to product"""
        if obj.product:
            url = reverse('admin:MAIN_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = "Product"
    product_link.admin_order_field = 'product__name'

    def colors_count(self, obj):
        """Show count of colors for this mesh"""
        count = obj.colors.count()
        if count > 0:
            url = reverse('admin:MAIN_productcolor_changelist') + f'?target_mesh__id__exact={obj.id}'
            return format_html('<a href="{}">{} Color(s)</a>', url, count)
        return "0 Colors"
    colors_count.short_description = "Colors"

# ============================================================================
# PRODUCT COLOR ADMIN
# ============================================================================

@admin.register(ProductColor)
class ProductColorAdmin(admin.ModelAdmin):
    list_display = ['color_hex', 'color_preview', 'target_mesh_link', 'name', 'product_link']
    list_filter = ['target_mesh', 'target_mesh__product']
    search_fields = ['name', 'color_hex', 'target_mesh__name', 'target_mesh__product__name']
    list_per_page = 25
    list_select_related = ['target_mesh', 'target_mesh__product']

    def target_mesh_link(self, obj):
        """Create clickable link to target mesh"""
        if obj.target_mesh:
            url = reverse('admin:MAIN_producttargetmesh_change', args=[obj.target_mesh.id])
            return format_html('<a href="{}">{}</a>', url, obj.target_mesh.name)
        return "-"
    target_mesh_link.short_description = "Target Mesh"
    target_mesh_link.admin_order_field = 'target_mesh__name'

    def product_link(self, obj):
        """Create clickable link to product"""
        if obj.target_mesh and obj.target_mesh.product:
            url = reverse('admin:MAIN_product_change', args=[obj.target_mesh.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.target_mesh.product.name)
        return "-"
    product_link.short_description = "Product"
    product_link.admin_order_field = 'target_mesh__product__name'

    def color_preview(self, obj):
        """Show color preview"""
        if obj.color_hex:
            return format_html(
                '<div style="width: 30px; height: 30px; background-color: {}; border: 1px solid #ccc; border-radius: 3px;"></div>',
                obj.color_hex
            )
        return "-"
    color_preview.short_description = "Preview"

# ============================================================================
# OTHER PRODUCT-RELATED ADMIN
# ============================================================================

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'product_link', 'order', 'info_text']
    list_filter = ['product']
    search_fields = ['product__name', 'info_text']
    list_per_page = 25
    raw_id_fields = ('product',)

    def product_link(self, obj):
        """Create clickable link to product"""
        if obj.product:
            url = reverse('admin:MAIN_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = "Product"
    product_link.admin_order_field = 'product__name'

# ============================================================================
# VENDOR, CUSTOMER, CATEGORY ADMIN
# ============================================================================

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'contact_person', 'official_email', 'is_verified', 'is_active', 'created_at',
        'official_phone', 'business_type', 'selling_category', 'instagramlink']
    list_filter = ['is_verified', 'is_active', 'created_at', 'country', 'business_type', 'selling_category']
    list_per_page = 20
    raw_id_fields = ('user_account',)
    search_fields = ['business_name', 'contact_person', 'official_email', 'business_license']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('business_name', 'contact_person', 'official_email', 'official_phone', 'business_type', 'selling_category', 'instagramlink', 'is_luxa_insider')
        }),
        ('Business Details', {
            'fields': ('business_license', 'tax_id', 'legal_document', 'total_sales')
        }),
        ('Visual', {
            'fields': ('image',)
        }),
        ('Address', {
            'fields': ('business_address', 'city', 'state', 'postal_code', 'country')
        }),
        ('Currency Settings', {
            'fields': ('currency_code',),
            'description': 'currency_code is the authoritative source for financial operations (ISO 4217). currency_symbol is automatically derived from currency_code and should not be manually edited.'
        }),
        ('Status', {
            'fields': ('is_verified', 'is_active', 'verification_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('User Account', {
            'fields': ('user_account',)
        }),
    )

# For editing customer info and also seeing their linked Crave Student Profile (if exists)
class CraveProfileInline(admin.StackedInline):
    model = Crave_Student_Profile
    can_delete = False
    verbose_name_plural = 'Crave Student Profile (Default University)'

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'is_verified', 'is_active', 'created_at', 'username', 'gender', 'promo_percentage', 'date_of_birth', 'profile_picture']
    list_filter = ['is_verified', 'is_active', 'newsletter_subscription', 'sms_notifications', 'created_at']
    raw_id_fields = ('user_account',)
    list_per_page = 20
    search_fields = ['first_name', 'last_name', 'email']
    readonly_fields = ['created_at', 'updated_at', 'last_login']
    list_editable = ['is_verified', 'is_active', 'gender']

    ordering = ('-created_at',)

    inlines = [CraveProfileInline]
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'username', 'gender', 'email', 'delivery_pin', 'phone_number', 'date_of_birth', 'profile_picture', 'social_media_platform', 'social_media_handle')
        }),
        ('Address', {
            'fields': ('address_line1', 'address_line2', 'city', 'state', 'postal_code', 'country')
        }),
        ('Customer Promo Information', {
            'fields': ('promo_percentage', 'promo_daily_total', 'promo_daily_counter', 'last_promo_date')
        }),
        ('Preferences', {
            'fields': ('newsletter_subscription', 'sms_notifications')
        }),
        ('Status', {
            'fields': ('is_active', 'is_verified', 'verification_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_login'),
            'classes': ('collapse',)
        }),
        ('User Account', {
            'fields': ('user_account',)
        }),
    )

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'is_featured', 'created_at']
    list_filter = ['is_active', 'is_featured', 'parent', 'created_at']
    search_fields = ['name', 'description']
    list_per_page = 25
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'parent')
        }),
        ('Visual', {
            'fields': ('image',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# ============================================================================
# APPROVE_KYC, REJECT_KYC AND KYC_ADMIN
# ============================================================================
@admin.action(description='✅ Approve Selected KYC')
def approve_kyc(modeladmin, request, queryset):
    for kyc in queryset:
        # 1. Mark KYC as Approved
        kyc.status = 'APPROVED'
        kyc.verified_at = timezone.now()
        kyc.verified_by = request.user
        kyc.save()

        # 2. Update Vendor Profile (if user is a vendor)
        if hasattr(kyc.user, 'vendor_profile'):
            vendor = kyc.user.vendor_profile
            vendor.is_verified = True
            vendor.save() 
            # Note: Your signals.py will automatically detect this change and send the "You're In!" email!

@admin.action(description='❌ Reject Selected KYC')
def reject_kyc(modeladmin, request, queryset):
    # Ideally you'd want a popup to enter a reason, but for now we just mark rejected
    queryset.update(status='REJECTED')

@admin.register(KYCVerification)
class KYCAdmin(admin.ModelAdmin):
    list_display = ['customer', 'id_type', 'status', 'submitted_at']
    list_filter = ['status', 'id_type']
    actions = [approve_kyc, reject_kyc]

    ordering = ('-submitted_at',)
    
    # Updated to use the new combined preview method
    readonly_fields = ['documents_preview', 'selfie_preview']

    def documents_preview(self, obj):
        # Helper function to generate HTML for a single document
        def get_preview_html(file_field, label):
            if not file_field:
                return f'<div style="width: 200px; padding: 10px; text-align: center; border: 1px dashed #ccc; border-radius: 4px; color: #777;">No {label} uploaded</div>'

            name, extension = os.path.splitext(file_field.name)
            extension = extension.lower()

            # Case A: Image
            if extension in ['.jpg', '.jpeg', '.png', '.webp']:
                return format_html(
                    '<div style="display: flex; flex-direction: column; align-items: center;">'
                    '<span style="font-weight: bold; margin-bottom: 5px;">{}</span>'
                    '<img src="{}" style="width: 200px; height: auto; border-radius: 4px; border: 1px solid #ccc; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" />'
                    '</div>',
                    label, file_field.url
                )
            
            # Case B: PDF
            elif extension == '.pdf':
                return format_html(
                    '<div style="display: flex; flex-direction: column; align-items: center;">'
                    '<span style="font-weight: bold; margin-bottom: 5px;">{}</span>'
                    '<iframe src="{}" width="200" height="200" style="border: 1px solid #ccc; border-radius: 4px;"></iframe>'
                    '<br><a href="{}" target="_blank" style="margin-top: 5px;">Open Full PDF</a>'
                    '</div>',
                    label, file_field.url, file_field.url
                )

            # Case C: Other Docs
            else:
                return format_html(
                    '<div style="display: flex; flex-direction: column; align-items: center;">'
                    '<span style="font-weight: bold; margin-bottom: 5px;">{}</span>'
                    '<a href="{}" target="_blank" style="background: #f0f0f0; padding: 15px 10px; border-radius: 4px; text-decoration: none; color: #333; border: 1px solid #ccc;">'
                    '📄 Download {}</a>'
                    '</div>',
                    label, file_field.url, extension.upper()
                )

        # Generate HTML for both front and back
        front_html = get_preview_html(obj.document_front, "Front")
        back_html = get_preview_html(obj.document_back, "Back")

        # Combine them using CSS Flexbox for a side-by-side layout
        return format_html(
            '<div style="display: flex; gap: 20px; align-items: flex-start; padding: 10px 0;">'
            '{}'
            '{}'
            '</div>',
            front_html, back_html
        )
    
    # This changes the label in the admin panel
    documents_preview.short_description = "Front and Back Document Preview"

    def selfie_preview(self, obj):
        if obj.selfie:
            return format_html('<img src="{}" style="width: 200px; height: auto; border-radius: 4px; border: 1px solid #ccc;" />', obj.selfie.url)
        return "-"


# ============================================================================
# ORDER ADMIN
# ============================================================================

class OrderInline(admin.TabularInline):
    model = Order
    extra = 0
    readonly_fields = ['vendor', 'total', 'status']
    can_delete = False

@admin.register(MasterOrder)
class MasterOrderAdmin(admin.ModelAdmin):
    list_display = ['public_order_id', 'customer', 'total_amount', 'status', 'payment_status', 'created_at']
    search_fields = ['public_order_id', 'customer__email']
    inlines = [OrderInline]

class OrderItemInline(admin.StackedInline):
    """Inline admin for OrderItem"""
    model = OrderItem
    extra = 0
    readonly_fields = ['subtotal', 'variant_display', 'quantity', 'price', 'variant_display', 'variants',] # Added read-only display
    
    # We use 'variant_display' for looking, and 'variants' for editing
    fields = ['product', 'quantity', 'price', 'variant_display', 'variants', 'subtotal']
    
    # filter_horizontal makes the M2M box usable
    filter_horizontal = ('variants',) 

    def variant_display(self, obj):
        """Read-only preview of selected variants"""
        if not obj.pk:
            return "-"
        return ", ".join([f"{v.variant_type}: {v.variant_value}" for v in obj.variants.all()])
    variant_display.short_description = "Selected Options"

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # ... (Keep your existing list_display and list_filter) ...
    list_display = ['order_number', 'customer', 'vendor', 'status', 'payment_status', 'total', 'created_at']
    list_filter = ['status', 'payment_status', 'created_at']
    list_per_page = 25
    search_fields = ['order_number', 'customer__first_name', 'customer__last_name', 'vendor__business_name']
    readonly_fields = ['payment_status' ,'order_number', 'created_at', 'updated_at', 'shipped_at', 'delivered_at', 'shipping_cost', 
                       'subtotal', 'tax', 'total', 'vendor_payout', 'delivery_type', 'delivery_fee', 'luxa_cut_amount', 'luxa_cut_percentage', 'shipping_address', 
                        'shipping_city', 'shipping_state', 'shipping_postal_code', 'shipping_country', 
                        ]
    inlines = [OrderItemInline]

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'order', 'product', 'quantity', 'variant_summary', 'price', 'subtotal']
    list_filter = ['order']
    list_per_page = 25
    search_fields = ['order__order_number', 'product__name']
    readonly_fields = ['price', 'subtotal', 'variant_summary', 'variants', 'order', 'product', 'quantity']
    filter_horizontal = ('variants',)

    def variant_summary(self, obj):
        """Display M2M variants as a comma-separated string"""
        # UPDATED: Now shows Type + Value (e.g., "Handle: Red")
        return ", ".join([f"{v.variant_type}: {v.variant_value}" for v in obj.variants.all()])
    variant_summary.short_description = "Variants"


# ============================================================================
# DRAFT & SYNC ORDER ADMIN (Internal System)
# ============================================================================

class DraftOrderItemInline(admin.TabularInline):
    model = DraftOrderItem
    extra = 0
    fields = ['product', 'quantity', 'variation_choices']
    readonly_fields = ['variation_choices'] # JSON fields can be risky to edit manually

@admin.register(DraftOrder)
class DraftOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'delivery_type', 'created_at']
    list_filter = ['status', 'delivery_type', 'created_at']
    search_fields = ['id', 'customer__email', 'customer__username']
    readonly_fields = ['id', 'created_at']
    inlines = [DraftOrderItemInline]
    
    fieldsets = (
        ('Order Info', {
            'fields': ('id', 'customer', 'status', 'delivery_type')
        }),
        ('Sync Data', {
            'fields': ('original_order_id', 'created_at')
        }),
    )

# @admin.register(LUXAOrder)
# class LUXAOrderAdmin(admin.ModelAdmin):
#     list_display = ['order_id', 'status', 'delivery_type', 'total_price', 'created_at', 'updated_at']
#     list_filter = ['status', 'delivery_type', 'created_at']
#     search_fields = ['order_id', 'customer_id']
#     readonly_fields = ['order_id', 'created_at', 'updated_at']
    
#     fieldsets = (
#         ('Core Identifiers', {
#             'fields': ('order_id', 'customer_id', 'order_source', 'assigned_courier')
#         }),
#         ('Status & Totals', {
#             'fields': ('status', 'delivery_type', 'same_day_eligibility', 'standard', 'total_price')
#         }),
#         ('JSON Data Blocks', {
#             'fields': ('products', 'vendors', 'product_configurations', 'pickup_locations', 'delivery_location'),
#             'classes': ('collapse',),
#             'description': 'Raw JSON data synchronized from the draft order.'
#         }),
#         ('Timestamps', {
#             'fields': ('created_at', 'updated_at')
#         }),
#     )

@admin.register(EligibilityStagingArea)
class EligibilityStagingAreaAdmin(admin.ModelAdmin):
    """
    Useful for debugging why a specific customer/product combo passed or failed checks.
    """
    list_display = ['order_id', 'customer_id', 'product_id', 'reason', 'created_at']
    list_filter = ['created_at']
    search_fields = ['order_id', 'reason']
    readonly_fields = ['order_id', 'customer_id', 'product_id', 'reason', 'created_at']

# ============================================================================
# CART ADMIN
# ============================================================================

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    # ... (Keep as is) ...
    list_display = ['__str__', 'customer', 'total_items', 'total_price', 'created_at']
    list_filter = ['created_at']
    list_per_page = 25
    search_fields = ['customer__first_name', 'customer__last_name', 'customer__email']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'cart', 'product', 'quantity', 'variant_summary', 'subtotal']
    list_filter = ['cart']
    list_per_page = 25
    search_fields = ['cart__customer__first_name', 'product__name']
    readonly_fields = ['subtotal']
    filter_horizontal = ('variants',)

    def variant_summary(self, obj):
        """Display M2M variants as a comma-separated string"""
        # UPDATED: Now shows Type + Value
        return ", ".join([f"{v.variant_type}: {v.variant_value}" for v in obj.variants.all()])
    variant_summary.short_description = "Variants"

# ============================================================================
# WISHLIST ADMIN
# ============================================================================

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'customer', 'total_items', 'created_at']
    list_filter = ['created_at']
    search_fields = ['customer__first_name', 'customer__last_name', 'customer__email']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 25

@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'wishlist', 'product', 'created_at']
    list_filter = ['wishlist', 'created_at']
    search_fields = ['wishlist__customer__first_name', 'product__name']
    list_per_page = 25
    readonly_fields = ['created_at']

# ============================================================================
# NOTIFICATION ADMIN
# ============================================================================

@admin.action(description='Mark selected notifications as read')
def mark_as_read(modeladmin, request, queryset):
    updated_count = queryset.update(is_read=True, read_at=timezone.now())
    modeladmin.message_user(request, f"{updated_count} notifications have been marked as read.")

@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'notification_type', 'message_preview', 'related_order', 'created_at', 'order_summary', 'order_link', 'is_read')
    list_filter = ('notification_type', 'is_read')
    list_per_page = 25
    ordering = ('-created_at',)
    readonly_fields = ('title', 'message', 'notification_type', 'order', 'product', 'created_at', 'read_at', 'order_link', 'order_summary')
    fieldsets = (
        ('Alert Details', {
            'fields': ('title', 'message', 'notification_type')
        }),
        ('Context', {
            'fields': ('order_link', 'order_summary', 'product'),
        }),
        ('Status', {
            'fields': ('is_read', 'created_at', 'read_at')
        }),
    )

    def message_preview(self, obj):
        if obj.message and len(obj.message) > 50:
            return obj.message[:50] + "..."
        return obj.message
    
    message_preview.short_description = "Message"
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(customer__isnull=True, vendor__isnull=True)
    
    def related_order(self, obj):
        if obj.order:
            return f"Order #{obj.order.order_number}"
        return "-"
    
    def order_link(self, obj):
        if obj.order:
            url = reverse('admin:MAIN_order_change', args=[obj.order.id])
            return format_html('<a class="button" href="{}">View Order #{}</a>', url, obj.order.order_number)
        return "-"
    order_link.short_description = "Order Link"

    def order_summary(self, obj):
        if obj.order:
            items = obj.order.items.all()[:3]
            summary = ", ".join([f"{item.quantity}x {item.product.name}" for item in items])
            if obj.order.items.count() > 3:
                summary += f" (+{obj.order.items.count() - 3} more)"
            return format_html(
                "<strong>Total:</strong> {}<br><strong>Items:</strong> {}", 
                obj.order.total, 
                summary
            )
        return "-"
    order_summary.short_description = "Order Details"

    actions = [mark_as_read]

@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'title', 'notification_type', 'created_at')
    list_filter = ('notification_type', 'created_at')
    list_per_page = 25
    search_fields = ('customer__first_name', 'vendor__business_name', 'title')
    readonly_fields = ('customer', 'vendor', 'title', 'message', 'notification_type', 'order', 'product', 'created_at', 'read_at')
    fieldsets = (
        ('Recipient Info', {
            'fields': ('customer', 'vendor')
        }),
        ('Message Content', {
            'fields': ('title', 'message', 'notification_type')
        }),
        ('Related Objects', {
            'fields': ('order', 'product'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'read_at')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).exclude(customer__isnull=True, vendor__isnull=True)

    def recipient(self, obj):
        if obj.vendor: return f"Vendor: {obj.vendor.business_name}"
        if obj.customer: return f"Customer: {obj.customer}"
        return "Unknown"
    
    actions = [mark_as_read]
