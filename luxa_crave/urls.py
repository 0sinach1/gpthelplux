
from django.urls import path, include
from . import views
from django.conf import settings             # <-- Add this import
from django.conf.urls.static import static   # <-- Add this import

urlpatterns = [
    # Auth URLs
    path('login/', views.crave_login, name='crave_login'),
    path('logout/', views.crave_logout, name='crave_logout'),

    # App URLs
    path('uni-select/', views.crave_entry, name='crave_entry'),
    path('dashboard/', views.crave_dashboard, name='crave_dashboard'),
    path('', views.crave_dashboard, name='crave_dashboard'),  # Default to entry point
    path('section-select/', views.crave_outlet_sections, name='crave_outlet_sections'),
    path('outlet/<int:outlet_id>/', views.outlet_terminal, name='outlet_terminal'), # URL pattern for outlet terminal
    path('settings/<int:profile_id>/', views.profile_settings_page, name='profile_settings'),
    path('api/update-settings/', views.update_settings, name='update_settings'),
    path('checkout/', views.crave_checkout, name='crave_checkout'), # URL pattern for checkout page
    
    # API Endpoints
    path('validate-pack/', views.validate_pack_integrity, name='validate_pack'),
    path('api/update-proxy/', views.update_proxy, name='update_proxy'),
    path('api/toggle-proxy-status/', views.toggle_proxy_status, name='toggle_proxy_status'),
    path('api/update-customer-address/', views.update_customer_address, name='update_customer_address'), # API endpoint for updating customer address
    path('api/get-preset/<int:preset_id>/', views.get_pack_preset, name='get_pack_preset'), # API endpoint for fetching preset details
    path('api/save-preset/', views.save_pack_preset, name='save_pack_preset'), # API endpoint for saving presets
    path('api/delete-preset/<int:preset_id>/', views.delete_pack_preset, name='delete_pack_preset'), # API endpoint for deleting presets
    path('api/get-order/<str:order_id>/', views.get_order_details, name='get_order_details'), # API endpoint for fetching order details
    path('api/get-active-orders-status/', views.get_active_orders_status, name='get_active_orders_status'),
    path('api/checkout-validation/', views.checkout_bag_validation, name='checkout_bag_validation'),
    path('api/check-wallet-balance/', views.check_wallet_balance_api, name='check_wallet_balance_api'),

    # API endpoint for processing the checkout form submission, creating the order, checking stock, locking funds, and returning success or specific errors back to the frontend
    path('api/create-campus-order/', views.create_campus_order, name='create_campus_order'),

    # API endpoint to validate the preferred courier username entered by the user in the checkout page before allowing them to proceed with the order
    path('api/validate-preferred-courier/', views.validate_preferred_courier, name='validate_preferred_courier'),
    path('api/check-ping/<int:ping_id>/', views.check_ping_status, name='check_ping_status'),

    # GOOGLE OAUTH URL
    path('accounts/', include('allauth.urls')),
]

# --- NEW: TELL THE SUBDOMAIN HOW TO SERVE IMAGES LOCALLY ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)