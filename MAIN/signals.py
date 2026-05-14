from django.db.models.signals import post_save, pre_save, post_delete
from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from django.core.mail import mail_admins, send_mail
from django.db.models import Count, Q 
from .models import Order, Notification, Customer, Vendor, Product, ProductColor, ProductVariant, MasterOrder, KYCVerification 
from django.conf import settings
from django.utils import timezone
from django.core.signing import TimestampSigner
from django.urls import reverse
from escrow.services import process_courier_payout

# --- 1. NEW CUSTOMER SIGNUP (Admin Alert) ---
@receiver(post_save, sender=Customer)
def notify_new_customer(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title=f"New Customer: {instance.full_name}",
            message=f"Email: {instance.user_account.email} has registered.",
            notification_type='system',
            customer=None, # Admin Alert
            vendor=None
        )

# --- 2. NEW VENDOR REGISTRATION (Admin Alert) ---
@receiver(post_save, sender=Vendor)
def notify_new_vendor(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            title=f"New Vendor: {instance.business_name}",
            message=f"Owner: {instance.user_account.email}. Please review application.",
            notification_type='system',
            customer=None, # Admin Alert
            vendor=None
        )

# Vendor approved and verified check
# --- TRACK VENDOR APPROVAL (Pre-Save) ---
@receiver(pre_save, sender=Vendor)
def track_vendor_approval(sender, instance, **kwargs):
    """
    Checks if a vendor is being transitioned to 'Approved' state.
    State: is_active=True AND is_verified=True.
    """
    if instance.pk: # Only check on updates, not initial creation
        try:
            old_vendor = Vendor.objects.get(pk=instance.pk)
            
            # Define "Approved" state: Active AND Verified
            was_approved = old_vendor.is_active and old_vendor.is_verified
            is_approved = instance.is_active and instance.is_verified

            # Detect transition from "Not Approved" -> "Approved"
            if is_approved and not was_approved:
                # Set a temporary flag on the object to trigger the email in post_save
                instance._just_approved = True
                
                # Auto-set verification date if the admin didn't manually pick one
                if not instance.verification_date:
                    instance.verification_date = timezone.now()

        except Vendor.DoesNotExist:
            pass

# --- SEND APPROVAL EMAIL (Post-Save) ---
@receiver(post_save, sender=Vendor)
def send_vendor_approval_email(sender, instance, created, **kwargs):
    """
    Sends the welcome email only if the '_just_approved' flag was set in pre_save.
    """
    # Check for the temporary flag
    if hasattr(instance, '_just_approved') and instance._just_approved:
        
        subject = f"🎉 You're In! Vendor Application Approved"
        message = (
            f"Hi {instance.business_name},\n\n"
            f"Congratulations! Your application to become a vendor on Luxa has been approved.\n\n"
            f"Your account is now active and verified. You can log in to your dashboard to start listing products and managing your store.\n\n"
            f"Login here: https://luxa.ng/login/\n\n" 
            f"Welcome to the family!\n"
            f"The Luxa Team"
        )
        
        try:
            # We prioritize official_email, fallback to user login email
            recipient = instance.official_email or instance.user_account.email
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=True
            )
            print(f"📧 Vendor Approval Email Sent: {recipient}")
        except Exception as e:
            print(f"⚠️ Failed to send vendor approval email: {e}")


# --- 3. NEW PRODUCT ADDED (Admin Alert) ---
@receiver(post_save, sender=Product)
def notify_new_product(sender, instance, created, **kwargs):
    if created:
        vendor_name = instance.vendor.business_name if instance.vendor else "Unknown"
        Notification.objects.create(
            title=f"New Product: {instance.name}", 
            message=f"Vendor: {vendor_name} | SKU: {instance.sku} | Price: {instance.price}",
            notification_type='product',
            product=instance,
            customer=None, # Admin Alert
            vendor=None
        )

# --- 4. ORDER STATUS TRACKER ---
@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Order.objects.get(pk=instance.pk)
            instance._old_status = old.status

            if old.status != instance.status:
                # Mark as 'Unread' for customer so they see the badge again
                instance.customer_seen = False

        except Order.DoesNotExist:
            instance._old_status = None


@receiver(post_save, sender=Order)
def send_order_email_notifications(sender, instance, created, **kwargs):
    """
    Centralized Email Handler:
    1. Sends 'Order Confirmed' email when order is created.
    2. Sends 'Status Update' email when status changes (Shipped, Delivered).
    """
    
    # 1. Get Recipient Email Safely
    try:
        recipient_email = instance.customer.user_account.email
        if not recipient_email: return
    except AttributeError:
        return 

    subject = None
    message = None
    
    # --- SCENARIO A: NEW ORDER CREATED ---
    # REMOVED: We now handle this in 'send_master_order_confirmation' below.
    # if created: ... (Deleted)

    # --- SCENARIO B: STATUS UPDATE ---
    # This runs only when the status changes (e.g. Processing -> Shipped)
    if hasattr(instance, '_old_status') and instance._old_status != instance.status:
        
        # 1. Shipped / In-Transit
        if instance.status in ['shipped', 'in_transit']:
            subject = f"🚚 Order #{instance.order_number} is on the way!"
            message = (
                f"Hi {instance.customer.first_name},\n\n"
                f"Great news! Your order #{instance.order_number} has been dispatched and is currently in transit.\n\n"
                f"You can track its progress in your dashboard.\n\n"
                f"Thank you for shopping with Luxa."
            )

        # 2. Delivered
        elif instance.status == 'delivered':
            subject = f"✅ Order #{instance.order_number} Delivered"
            message = (
                f"Hi {instance.customer.first_name},\n\n"
                f"Your order #{instance.order_number} has been successfully delivered.\n\n"
                f"Please confirm you have received the items in good condition.\n\n"
                f"We hope you enjoy your purchase!"
            )

    # --- SEND THE EMAIL ---
    if subject and message:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=True
            )
            print(f"📧 Email Sent ({'Created' if created else instance.status}): {recipient_email}")
        except Exception as e:
            print(f"⚠️ Failed to send email: {e}")

# --- 5. ORDER EVENTS (Dual Notifications: Admin + User) ---
@receiver(post_save, sender=Order)
def notify_order_events(sender, instance, created, **kwargs):
    
    vendor_name = instance.vendor.business_name if instance.vendor else 'Unknown'
    customer_name = instance.customer.full_name if instance.customer else 'Guest'

    # EVENT A: NEW ORDER
    if created:
        # 1. Admin Alert (Popup)
        Notification.objects.create(
            title=f"🔔 New Order: {instance.order_number}",
            message=f"Customer: {customer_name} | Vendor: {vendor_name} | Total: {instance.total}",
            notification_type='order',
            order=instance,
            customer=None, # None = Admin
            vendor=None
        )

        # 2. Customer Notification (Inbox)
        Notification.objects.create(
            title="Order Placed Successfully",
            message=f"Your order {instance.order_number} has been placed. Status: {instance.status}",
            notification_type='order',
            order=instance,
            customer=instance.customer, # Linked to Customer
            vendor=None
        )

        # 3. Vendor Notification (Inbox)
        if instance.vendor:
            Notification.objects.create(
                title="New Sale!",
                message=f"You have a new order {instance.order_number} from {customer_name}.",
                notification_type='order',
                order=instance,
                customer=None,
                vendor=instance.vendor # Linked to Vendor
            )

    # EVENT B: STATUS CHANGE
    elif hasattr(instance, '_old_status') and instance._old_status != instance.status:
        # 1. Admin Alert
        Notification.objects.create(
            title=f"Order Update: {instance.order_number}",
            message=f"Status changed: {instance._old_status} -> {instance.status}",
            notification_type='order',
            order=instance,
            customer=None,
            vendor=None
        )

        # 2. Customer Notification
        Notification.objects.create(
            title="Order Status Updated",
            message=f"Order {instance.order_number} is now {instance.status}.",
            notification_type='order',
            order=instance,
            customer=instance.customer,
            vendor=None
        )

        # 3. Vendor Notification
        if instance.vendor:
            Notification.objects.create(
                title="Order Status Updated",
                message=f"Order {instance.order_number} changed to {instance.status}.",
                notification_type='order',
                order=instance,
                customer=None,
                vendor=instance.vendor
            )

# --- 6. ORDER DELETION (System-Wide Alert) ---
@receiver(post_delete, sender=Order)
def notify_order_deletion(sender, instance, **kwargs):
    """
    Alerts Admin, Customer, and Vendor when an order is permanently deleted.
    NOTE: We cannot link 'order=instance' because the ID no longer exists.
    """
    
    # 1. Admin Alert (Popup)
    Notification.objects.create(
        title=f"⚠️ Order Deleted: {instance.order_number}",
        message=f"Order was permanently removed. Previous status: {instance.status}",
        notification_type='system',
        customer=None,
        vendor=None
    )

    # 2. Customer Alert (Inbox)
    # We check if customer exists (in case the deletion was caused by deleting the customer)
    if instance.customer:
        Notification.objects.create(
            title="Order Cancelled & Removed",
            message=f"Your order #{instance.order_number} has been cancelled and removed from the system. If this was a mistake, please contact support.",
            notification_type='order',
            customer=instance.customer, # Send to Customer
            vendor=None,
            order=None # Order is gone, so no link
        )

    # 3. Vendor Alert (Inbox)
    if instance.vendor:
        Notification.objects.create(
            title="Order Removed",
            message=f"Order #{instance.order_number} has been removed from your dashboard.",
            notification_type='order',
            customer=None,
            vendor=instance.vendor, # Send to Vendor
            order=None
        )

# --- 7. ALLAUTH USER SIGNUP HOOK ---
@receiver(user_signed_up)
def create_customer_profile_oauth(request, user, **kwargs):
    try:
        existing_customer = Customer.objects.filter(email=user.email).first()
        if existing_customer:
            existing_customer.user_account = user
            existing_customer.first_name = user.first_name
            existing_customer.last_name = user.last_name
            existing_customer.save()
        else:
            Customer.objects.get_or_create(
                user_account=user,
                defaults={
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                }
            )
    except Exception as e:
        print(f"Error: {str(e)}")

# --- 8. SYNC 3D MESH COLORS ---
@receiver(post_save, sender=ProductColor)
def sync_mesh_color_to_variant(sender, instance, created, **kwargs):
    if not instance.target_mesh: return
    dynamic_type = instance.target_mesh.name.title() 
    dynamic_value = instance.name
    ProductVariant.objects.update_or_create(
        mesh_color_source=instance,
        defaults={
            'product': instance.target_mesh.product,
            'variant_type': dynamic_type,
            'variant_value': dynamic_value,
            'is_available': True
        }
    )

# --- 9. MASTER ORDER SYNC LOGIC ---

# DOWNSTREAM: Payment (Master -> Children)
@receiver(post_save, sender=MasterOrder)
def sync_payment_to_children(sender, instance, **kwargs):
    """
    If MasterOrder is marked PAID, automatically mark all sub-orders as PAID.
    """
    if instance.payment_status == 'paid':
        # Efficiently update all children without triggering individual save signals loop
        # unless you want specific signals to fire for children.
        # Using .update() is faster but bypasses 'post_save' on children.
        # If you need child signals (like vendor notifications), loop instead.
        instance.sub_orders.exclude(payment_status='paid').update(payment_status='paid')

# --- A. MASTER -> CHILD SYNC (The "Waterfall") ---
@receiver(post_save, sender=MasterOrder)
def cascade_status_to_sub_orders(sender, instance, created, **kwargs):
    """
    When MasterOrder status changes, push updates to child Vendor Orders.
    Crucial for 'delivered' status to trigger Vendor Payouts.
    """
    if created:
        return

    # Map Master statuses to Child statuses
    # We skip 'awaiting_validation' and 'pending_cancellation' because 
    # the individual Order model doesn't support them.
    status_map = {
        'processing': 'processing',
        'shipped': 'shipped', 
        'delivered': 'delivered', # <--- The Money Trigger
        'cancelled': 'cancelled',
    }

    target_status = status_map.get(instance.status)

    if target_status:
        # We iterate and .save() instead of .update() 
        # This ensures that any signals attached to the Child Order (like Payouts) actually fire.
        for order in instance.sub_orders.all():
            if order.status != target_status:
                order.status = target_status
                order.save() 
                print(f"   ↳ Synced Sub-Order {order.order_number} to {target_status}")

# --- B. CHILD -> MASTER SYNC (The "Vice Versa" Logic) ---
@receiver(post_save, sender=Order)
def update_master_order_status(sender, instance, created, **kwargs):
    """
    If ALL child orders are 'delivered', mark Master as 'delivered'.
    If ALL are 'cancelled', mark Master 'cancelled'.
    """
    master = instance.master_order
    if not master:
        return

    # Prevent Recursion: If Master is already the status we want, stop.
    if master.status == instance.status:
        return

    all_orders = master.sub_orders.all()
    
    # Check if ALL orders match the current status (e.g. all delivered)
    if all(o.status == instance.status for o in all_orders):
        # We accept the child's status for the master
        # (But we map 'shipped' -> 'shipped' just to be safe)
        if instance.status in ['delivered', 'cancelled', 'shipped']:
            master.status = instance.status
            master.save()
            print(f"   ▲ All children {instance.status}. Updated Master {master.public_order_id}")


# --- 10. MASTER ORDER EMAIL NOTIFICATIONS ---

@receiver(pre_save, sender=MasterOrder)
def track_master_payment_status(sender, instance, **kwargs):
    """
    Tracks the previous payment status so we know when it changes to 'paid'.
    """
    if instance.pk:
        try:
            old = MasterOrder.objects.get(pk=instance.pk)
            instance._old_payment_status = old.payment_status
        except MasterOrder.DoesNotExist:
            instance._old_payment_status = None
    else:
        instance._old_payment_status = None

@receiver(post_save, sender=MasterOrder)
def send_master_order_confirmation(sender, instance, created, **kwargs):
    """
    Sends ONE single confirmation email when the Master Order is marked as PAID.
    """
    # Check if payment just transitioned to 'paid'
    was_paid = getattr(instance, '_old_payment_status', None) == 'paid'
    is_paid = instance.payment_status == 'paid'

    # Send only if it IS paid, and WAS NOT paid before (to avoid duplicates)
    if is_paid and not was_paid:
        try:
            recipient_email = instance.customer.user_account.email
            subject = f"🎉 Order Confirmed! (#{instance.public_order_id})"
            
            message = (
                f"Hi {instance.customer.first_name},\n\n"
                f"Thank you for your order! We have received your payment and are processing it.\n\n"
                f"Order ID: #{instance.public_order_id}\n"
                f"Total Paid: ₦{instance.total_amount:,.2f}\n"
                f"Shipments: {instance.sub_orders.count()} vendor package(s)\n\n"
                f"You will receive individual updates as we ship your items.\n\n"
                f"Track your full order details here: https://luxa.ng/orders/{instance.public_order_id}/\n\n"
                f"Best regards,\nThe Luxa Team"
            )
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=True
            )
            print(f"📧 Master Order Confirmation Sent: {recipient_email}")
        except Exception as e:
            print(f"⚠️ Failed to send Master Order email: {e}")

@receiver(post_delete, sender=ProductColor)
def delete_linked_variant(sender, instance, **kwargs):
    ProductVariant.objects.filter(mesh_color_source=instance).delete()

# --- 11. KYC CHECK MAILS ---
@receiver(pre_save, sender=KYCVerification)
def track_previous_status(sender, instance, **kwargs):
    """
    Before saving, check what the status IS right now 
    so we can compare it later.
    """
    try:
        # Get the version currently in the DB
        old_instance = KYCVerification.objects.get(pk=instance.pk)
        instance._old_status = old_instance.status
    except KYCVerification.DoesNotExist:
        # This is a new object (creation), so no "old" status
        instance._old_status = None

@receiver(post_save, sender=KYCVerification)
def send_kyc_status_email(sender, instance, created, **kwargs):
    """
    After saving, if the status changed, send an email and notifications to customer.
    Plus, notify admin on new submissions.
    """
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status

    # If status didn't change, do nothing
    if old_status == new_status:
        return

    # Prepare Email Data
    user_email = instance.customer.user_account.email
    subject = ""
    message = ""

    # NOTIFICATION SEND TO ADMIN ON KYC CREATION
    if created:
        Notification.objects.create(
            title=f"New KYC Submission: {instance.full_name_on_id}",
            message=f"Owner: {instance.customer.user_account.email}. Please review application.",
            notification_type='system',
            customer=None, # Admin Alert
            vendor=None
        )

    if new_status == 'APPROVED':
        subject = "🎉 Identity Verified - Luxa.ng"
        message = (
            f"Hello {instance.full_name_on_id},\n\n"
            "Great news! Your identity verification documents have been APPROVED.\n"
            "You can now enjoy faster order processing and secure delivery.\n\n"
            "Thank you for choosing Luxa."
        )

        # Create Notification
        Notification.objects.create(
            title=f"KYC Approved as {instance.full_name_on_id}",
            message=f"Owner: {instance.customer.user_account.email}. Thank you for completing your KYC verification.",
            notification_type='order',
            customer=instance.customer,
            vendor=None
        )

        # MAKE THE CUSTOMER VERIFIED
        if not instance.customer.is_verified:
            instance.customer.is_verified = True
            instance.customer.save(update_fields=['is_verified'])

    elif new_status == 'REJECTED':
        subject = "⚠️ Action Required: Identity Verification Update"
        reason = instance.rejection_reason or "Document clarity issues"
        message = (
            f"Hello {instance.full_name_on_id},\n\n"
            "We reviewed your identity documents, but unfortunately, we could not verify them.\n"
            f"Reason: {reason}\n\n"
            "Please log in to your dashboard and re-upload clear copies of your ID.\n"
            "http://127.0.0.1:8000/kyc/submit/" 
        )

        # Create Notification
        Notification.objects.create(
            title=f"KYC Rejected as {instance.full_name_on_id}",
            message=f"The KYC application for {instance.customer.user_account.email} was rejected. Please review application.",
            notification_type='order',
            customer=instance.customer,
            vendor=None
        )

    # Send the email if we have a message
    if message:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            fail_silently=True, # Prevents crashing if email settings aren't perfect yet
        )


# --- 12. CHECK MASTER STATUS CHANGE FOR CUSTOMER VERIFICATION AND COURIER PAYOUT
@receiver(pre_save, sender=MasterOrder)
def track_master_status_change(sender, instance, **kwargs):
    """
    Tracks the previous status so we can detect transitions.
    """
    if instance.pk:
        try:
            old = MasterOrder.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except MasterOrder.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


# --- TRIGGER PAYOUT (Post-Save) ---
@receiver(post_save, sender=MasterOrder)
def trigger_courier_payout_main(sender, instance, created, **kwargs):
    """
    Triggers the financial transaction only when status TRANSITIONS to 'delivered'.
    """
    # 1. Get the old status (set by the pre_save signal above)
    old_status = getattr(instance, '_old_status', None)

    # 2. Check for the specific transition
    # Logic: It IS 'delivered' now, but it WAS NOT 'delivered' before.
    if instance.status == 'delivered' and old_status != 'delivered':
        
        print(f"💰 Status changed to DELIVERED for #{instance.public_order_id}. Processing Payout...")
        
        # 3. Call the Service
        process_courier_payout(instance.id)

