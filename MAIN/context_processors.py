from .models import Notification
from .models import Category

def notification_counts(request):
    """
    Returns unread counts for Inbox and Wallet to be used in all templates.
    """
    if not request.user.is_authenticated:
        return {}

    inbox_count = 0
    wallet_count = 0

    # 1. Filter notifications based on user type (Vendor vs Customer)
    qs = Notification.objects.filter(is_read=False)
    
    if hasattr(request.user, 'vendor_profile'):
        qs = qs.filter(vendor=request.user.vendor_profile)
    elif hasattr(request.user, 'customer_profile'):
        qs = qs.filter(customer=request.user.customer_profile)
    else:
        qs = qs.none()

    # 2. Calculate Counts
    # Inbox Badge: Shows total unread messages
    inbox_count = qs.count()

    # Wallet Badge: Shows unread 'payment' related messages
    wallet_count = qs.filter(notification_type='payment').count()

    return {
        'inbox_unread_count': inbox_count,
        'wallet_unread_count': wallet_count,
    }
    
def global_context(request):
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
    return {
        'unread_notification_count': unread_count,
        'nav_categories': Category.objects.all(),
    }