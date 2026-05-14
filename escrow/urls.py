from django.urls import path
from . import views

urlpatterns = [
    # Payment and Wallet Operations
    path('withdraw/', views.withdraw_funds, name='withdraw_funds'),
    path('link-bank/', views.link_bank_account, name='link_bank_account'),
    path('webhook/', views.paystack_webhook, name='paystack_webhook'),
    # Wallet Security Paths
    path('security/pin/', views.validate_wallet_pin, name='validate_wallet_pin'),
    path('security/forgot-pin/', views.request_pin_reset, name='request_pin_reset'),
    path('security/reset-pin/<str:token>/', views.verify_pin_reset, name='verify_pin_reset'),
    path('security/change/', views.change_wallet_pin, name='change_wallet_pin'),
    # Wallet Dashboard Paths
    path('dashboard/', views.wallet_dashboard, name='wallet_dashboard'),
    path('set-active-bank/', views.set_active_bank, name='set_active_bank'),
    path('delete-bank/', views.delete_bank_account, name='delete_bank_account'),
    # Admin Escrow Management Dashboard
    path('admin/dashboard/', views.escrow_management_dashboard, name='escrow_admin_dashboard'),
]