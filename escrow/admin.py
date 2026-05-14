from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
	list_display = (
		'user',
		'user__first_name',
		'user__last_name',
		'wallet_type',
		'currency',
		'available_balance',
		'locked_escrow',
		'pending_clearing',
		'created_at',
	)
	list_filter = ('wallet_type', 'currency')
	search_fields = ('user__email', 'user__username')
	readonly_fields = ('currency', 'created_at')
	list_select_related = ('user',)
	list_per_page = 25

	ordering = ('-created_at',)

	def user(self, obj):
		# Return the customer's or vendor's profile object when available so
		# the admin's related-object icon links to the profile change page.
		if not getattr(obj, 'user_id', None):
			return '-'
		user = obj.user
		# Prefer returning the profile instance so Django admin links to it
		if obj.wallet_type == 'VENDOR':
			if hasattr(user, 'vendor_profile') and user.vendor_profile:
				return user.vendor_profile
		else:
			if hasattr(user, 'customer_profile') and user.customer_profile:
				return user.customer_profile
		# Fallback to the User object
		return user
	user.short_description = 'User'
	user.admin_order_field = 'user__email'


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
	list_display = (
		'reference',
		'wallet_link',
		'transaction_type',
		'amount',
		'running_balance',
		'timestamp',
	)
	list_filter = ('transaction_type', 'wallet__wallet_type')
	search_fields = ('reference', 'description', 'wallet__user__email')
	readonly_fields = ('reference', 'wallet_link', 'transaction_type', 'amount', 'timestamp', 'running_balance')
	list_select_related = ('wallet', 'wallet__user')
	list_per_page = 25

	ordering = ('-timestamp',)

	def wallet_link(self, obj):
		if not getattr(obj, 'wallet_id', None):
			return '-'
		url = reverse('admin:escrow_wallet_change', args=[obj.wallet_id])
		return format_html('<a href="{}">{}</a>', url, str(obj.wallet))
	wallet_link.short_description = 'Wallet'
	wallet_link.admin_order_field = 'wallet__user__email'

	# Removing add funtionality for extra security
	def has_add_permission(self, request):
		return False


