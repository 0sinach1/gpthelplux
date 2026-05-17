from django.urls import path
from . import views

urlpatterns = [
    # courier dashboard
    path('app/', views.courier_dashboard, name='courier_dashboard'),
    path('modal/order/<str:order_id>/', views.get_order_details_snippet, name='get_order_details'),
    path('modal/newbatch/', views.get_new_batches_fragment, name='get_batch_details'),
    path('modal/activebatch/', views.get_active_batch_fragment, name='get_active-batch'),
    path('modals/returnorders', views.get_returns_fragment, name='get_returns_fragment'),

    path('courier_reg/', views.register, name='courier_registration'),
    path('courier_upg/', views.courier_upgrade, name='courier_upgrade'),
    path('courier_login/', views.login_view, name="courierlogin"),
    path('logout/', views.logout_view, name="courierlogout"),
    path('verify-email/<uidb64>/<token>/', views.verify_courier_email, name='verify_courier_email'), # Verfiy courier email
    path('verify-daily-key/', views.verify_daily_key, name='verify_daily_key'),
    path('monitor_login/', views.admin_key_monitor_login, name='monitor_login'),
    path('key_monitor/', views.admin_key_monitor, name='key_monitor'),
    path('monitor_logout/', views.admin_key_monitor_logout, name='monitor_logout'),
    path('check-state/', views.check_courier_state, name='check_courier_state'),
    path('advance-wallet-balance/', views.get_advance_courier_wallet_balance, name='get_advance_courier_wallet_balance'),

    # Campus availability management for couriers
    path('campus_availability/', views.campus_availability_manager, name='campus_availability_manager'),

    # Scavenger Protocol Endpoint
    # path('api/claim-scavenger/', views.claim_scavenger_order_view, name='claim_scavenger_order_view'),

    # Interceptor Protocol Endpoints
    path('api/interceptor/pings/', views.api_get_interceptor_pings, name='api_get_interceptor_pings'),
    path('api/interceptor/resolve/', views.api_resolve_ping, name='api_resolve_ping'),
    path('api/update-interceptor-outlet/', views.update_interceptor_outlet, name='update_interceptor_outlet'),

    # courier status toggle and sweep trigger
    path('toggle_status/', views.toggle_courier_status, name='toggle_courier_status'),
    # path('trigger-sweep/', views.trigger_executioner_sweep, name='trigger_sweep'),

    # View for handling customer pin verification after delivery
    path('verify-pin/<str:order_id>/', views.courier_verify_pin, name='courier_verify_pin'),
    # AJAX endpoint to fetch current load
    path('api/batch-action/', views.courier_batch_action, name='courier_batch_action'),
    path('api/order-action/<str:order_id>/', views.courier_order_action_view, name='courier_order_action'),

    #Views for shift scheduling and exemption requests
    # path('api/schedule-shifts/', views.schedule_shifts_api, name='api_schedule_shifts'),
    # path('api/request-exemption/', views.request_exemption_api, name='api_request_exemption'),

    # Admin views for managing couriers and their access logs
    path('admin/manager/', views.admin_escrow_manager, name='admin_escrow_manager'),

    # Admin APIs
    # path('api/tollbooth-transit/', views.tollbooth_transit_api, name='api_tollbooth_transit'),
    # path('api/check-pending-ping/', views.check_pending_ping, name='api_check_pending_ping'),
    # path('api/respond-ping/', views.respond_ping, name='api_respond_ping'),
    path('admin/api/search-couriers/', views.escrow_search_user, name='escrow_search_user'),
    path('escrow/api/global-ledger/', views.escrow_global_transactions, name='escrow_global_transactions'),
    path('escrow/api/manual-txn/', views.escrow_manual_transaction, name='escrow_manual_transaction'),
    path('escrow/api/order-medic/', views.escrow_order_medic, name='escrow_order_medic'),
    path('escrow/api/campus-orders/', views.escrow_campus_orders_api, name='escrow_campus_orders_api'),
    path('escrow/api/campus-order/<uuid:order_id>/', views.escrow_campus_order_details, name='escrow_campus_order_details'),
    path('escrow/api/user-autocomplete/', views.escrow_user_autocomplete, name='escrow_user_autocomplete'),
    path('escrow/api/delivery-batches/', views.escrow_delivery_batches_api, name='escrow_delivery_batches_api'),
    path('escrow/api/delivery-batch/<int:batch_id>/', views.escrow_batch_details_api, name='escrow_batch_details_api'),
    path('escrow/api/reassign-batch/', views.escrow_reassign_batch_api, name='escrow_reassign_batch_api'),
    path('escrow/api/reassign-single-order/', views.escrow_reassign_single_order_api, name='escrow_reassign_single_order_api'),
    path('escrow/api/wallet-directory/', views.escrow_wallet_directory_api, name='escrow_wallet_directory_api'),
    path('escrow_platform_earnings_api/', views.escrow_platform_earnings_api, name='escrow_platform_earnings_api'),
]