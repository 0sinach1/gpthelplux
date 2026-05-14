from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from luxa_crave.models import University_Order
from .models import Wallet, WalletTransaction
from MAIN.models import Vendor, Notification, Order
from django.core.mail import send_mail
from django.db import transaction
from decimal import Decimal

User = get_user_model() # Fixed fee for campus deliveries

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        # Create a Customer Wallet automatically
        Wallet.objects.create(user=instance, wallet_type=Wallet.WalletType.CUSTOMER)
        # You can also create a Vendor wallet here if you want everyone to have 

@receiver(post_save, sender=Vendor)
def create_vendor_wallet(sender, instance, created, **kwargs):
    if created:
        # Check if a wallet already exists to avoid duplicates (safety check)
        if not Wallet.objects.filter(user=instance.user_account, wallet_type=Wallet.WalletType.VENDOR).exists():
            Wallet.objects.create(
                user=instance.user_account,
                wallet_type=Wallet.WalletType.VENDOR,
                currency='NGN' # Optional: Default currency
            )

# TRACK ORDER STATUS PRE-SAVE
@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Order.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

# --- 3. TRANSACTION NOTIFICATIONS (Comprehensive) ---
@receiver(post_save, sender=WalletTransaction)
def notify_wallet_transaction(sender, instance, created, **kwargs):
    """
    Triggers a notification AND email for ALL wallet transaction types:
    - Deposit, Withdrawal, Escrow Lock, Vendor Credit, Refund.
    """
    if created:
        wallet = instance.wallet
        user = wallet.user
        
        # 1. Determine Profile Recipient
        customer_recipient = None
        vendor_recipient = None

        if wallet.wallet_type == Wallet.WalletType.VENDOR:
            if hasattr(user, 'vendor_profile'):
                vendor_recipient = user.vendor_profile
        else:
            if hasattr(user, 'customer_profile'):
                customer_recipient = user.customer_profile

        if not customer_recipient and not vendor_recipient:
            return

        # 2. Prepare Message Details
        amount_val = abs(instance.amount)
        formatted_amount = f"₦{amount_val:,.2f}"
        
        title = ""
        message = ""
        email_subject = ""
        
        # --- TYPE A: DEPOSIT (Money In) ---
        if instance.transaction_type == 'DEPOSIT':
            title = "Wallet Funded"
            email_subject = f"💰 Deposit Confirmed: {formatted_amount}"
            message = f"Success! Your wallet has been credited with {formatted_amount}. Ref: {instance.reference}"

        # --- TYPE B: WITHDRAWAL (Money Out) ---
        elif instance.transaction_type == 'WITHDRAWAL':
            title = "Withdrawal Successful"
            email_subject = f"↘ Withdrawal Sent: {formatted_amount}"
            message = f"Debit Alert: {formatted_amount} has been sent to your bank account. Ref: {instance.reference}"

        # --- TYPE C: PURCHASE_LOCK (Customer Pays - Money Locked) ---
        elif instance.transaction_type == 'PURCHASE_LOCK':
            title = "Payment Secured (Escrow)"
            email_subject = f"🔒 Payment Secured: {formatted_amount}"
            message = f"We have secured {formatted_amount} for your order. Funds are held safely until delivery. Ref: {instance.reference}"

        # --- TYPE D: PURCHASE_RELEASE (Vendor Earns - Money Released) ---
        elif instance.transaction_type == 'PURCHASE_RELEASE':
            title = "Earnings Released"
            email_subject = f"💸 You got paid! {formatted_amount} Credited"
            message = f"Great news! Earnings of {formatted_amount} from a completed order have been released to your wallet."

        # --- TYPE E: REFUND (Money Returned) ---
        elif instance.transaction_type == 'REFUND':
            title = "Refund Processed"
            email_subject = f"↩️ Refund Received: {formatted_amount}"
            message = f"A refund of {formatted_amount} has been credited back to your wallet. Ref: {instance.reference}"

        else:
            return # Ignore unknown types

        # 3. Create In-App Notification (Dashboard)
        Notification.objects.create(
            title=title,
            message=message,
            notification_type='payment',
            customer=customer_recipient,
            vendor=vendor_recipient,
            is_read=False
        )

        # 4. Send Email (Inbox)
        try:
            send_mail(
                subject=email_subject,
                message=message,
                from_email='Luxa Support <thebrandluxa@gmail.com>',
                recipient_list=[user.email],
                fail_silently=True 
            )
        except Exception as e:
            print(f"⚠️ Failed to send transaction email: {e}")

# --- 4. ESCROW LOGIC (The Money Mover) ---
# --- ESCROW LOGIC (Status Changes Only) ---
# In MAIN/signals.py

@receiver(post_save, sender=Order)
def manage_escrow_balances(sender, instance, created, **kwargs):
    """
    Handles financial movements based on Order Lifecycle.
    """
    if kwargs.get('raw', False) or created:
        return

    with transaction.atomic():
        customer_wallet = None
        vendor_wallet = None
        
        # Safe Get Wallets
        if instance.customer:
             # Use filter().first() to avoid crash if wallet missing
            customer_wallet = Wallet.objects.filter(
                user=instance.customer.user_account, 
                wallet_type=Wallet.WalletType.CUSTOMER
            ).first()
            
        if instance.vendor:
            vendor_wallet = Wallet.objects.filter(
                user=instance.vendor.user_account, 
                wallet_type=Wallet.WalletType.VENDOR
            ).first()

        # SCENARIO: STATUS CHANGES
        if instance._old_status != instance.status:
            
            # --- DEFINE THE SPLIT ---
            # 1. Total (What Customer Paid)
            total_amount = instance.total 
            
            # 2. Vendor Share (What Vendor Gets) -> Subtotal - Fees
            # Use vendor_payout if available, otherwise fallback to subtotal (legacy safety)
            vendor_share = instance.vendor_payout if (instance.vendor_payout and instance.vendor_payout > 0) else instance.subtotal
            
            # 3. Luxa Share (What stays in Paystack Balance)
            # We don't need to 'send' this anywhere, we just DON'T send it to the vendor.
            # platform_share = total_amount - vendor_share 

            # --- CASE 1: DELIVERED (Release Funds) ---
            if instance.status == 'delivered': 
                txn_ref = f"EARN-{instance.order_number}"

                # --- [THE FIX] 2. CHECK IF ALREADY PAID ---
                if WalletTransaction.objects.filter(reference=txn_ref).exists():
                    print(f"ℹ️ Skipping duplicate payment for {txn_ref}")
                    return
                
                # A. Customer Side: Unlock the FULL amount they paid
                if customer_wallet:
                    # 1. Unlock the Sub-Order Total (The Vendor's Products)
                    if customer_wallet.locked_escrow >= total_amount:
                        customer_wallet.locked_escrow -= total_amount
                    
                    # 2. [THE FIX] RELEASE THE GLOBAL DELIVERY FEE (The 250)
                    # We check if this is the LAST item in the Master Order.
                    if instance.master_order:
                        master = instance.master_order
                        
                        # Check for any siblings that are NOT 'delivered', 'cancelled', or 'refunded'
                        # We exclude the current instance.id because it's technically still 'processing' until this saves
                        pending_siblings = master.sub_orders.exclude(
                            id=instance.id
                        ).exclude(
                            status__in=['delivered', 'cancelled', 'refunded']
                        ).exists()

                        if not pending_siblings:
                            # No other active items exist. This is the last one.
                            # Release the Global Delivery Fee (250) from Locked Escrow.
                            # (It disappears from the user's wallet effectively becoming Platform Revenue)
                            if customer_wallet.locked_escrow >= master.delivery_fee:
                                customer_wallet.locked_escrow -= master.delivery_fee
                                
                                WalletTransaction.objects.create(
                                    wallet=customer_wallet,
                                    transaction_type='PURCHASE_RELEASE',
                                    amount=Decimal('0.00'), # Neutral on Available Balance
                                    running_balance=customer_wallet.available_balance,
                                    reference=f"FEE-{master.public_order_id}",
                                    description=f"Platform Delivery Fee Cleared (₦{master.delivery_fee} released from Escrow)"
                                )

                    customer_wallet.save()
                
                # B. Vendor Side: Credit ONLY the Vendor Share
                if vendor_wallet:
                    # Clear pending (if any exists)
                    if vendor_wallet.pending_clearing >= vendor_share:
                        vendor_wallet.pending_clearing -= vendor_share
                    else:
                        vendor_wallet.pending_clearing = Decimal('0.00')
                    
                    # ✅ THE FIX: Credit 'vendor_share', NOT 'total_amount'
                    vendor_wallet.available_balance += vendor_share
                    vendor_wallet.save()

                    # --- [NEW] INCREMENT VENDOR SALES COUNT ---
                    if instance.vendor:
                        instance.vendor.total_sales += 1
                        instance.vendor.save(update_fields=['total_sales'])
                    # ------------------------------------------

                    # Log the Payout
                    WalletTransaction.objects.create(
                        wallet=vendor_wallet,
                        transaction_type='PURCHASE_RELEASE',
                        amount=vendor_share, # <--- Logs the correct split amount
                        running_balance=vendor_wallet.available_balance,
                        reference=f"EARN-{instance.order_number}",
                        description=f"Earnings Released for Order #{instance.order_number} (Fees Deducted)"
                    )
                    
                    # Optional: Log the Platform Fee (for Admin Records only)
                    # You usually don't need a wallet transaction for this unless you have a 'Company Wallet'

            # --- CASE 2: CANCELLED (Refund Customer) ---
            # Triggers when status switches to 'cancelled' AND not yet marked refunded
            elif (instance.status == 'cancelled' or instance.status == 'refunded') and instance.payment_status != 'refunded':
                
                # 1. CALL REFUND SERVICE
                # We import inside function to avoid circular imports
                from escrow.services import refund_order
                
                refund_result = refund_order(instance.id)
                
                if refund_result['verified']:
                    amount_refunded = refund_result['refunded_amount']

                    # 2. UPDATE PAYMENT STATUS
                    # Update directly to avoid triggering signals again
                    Order.objects.filter(pk=instance.pk).update(payment_status='refunded')

                    # 3. CREATE SYSTEM NOTIFICATION
                    Notification.objects.create(
                        title="Refund Processed",
                        message=f"₦{amount_refunded:,.2f} has been refunded to your wallet for Order #{instance.order_number}.",
                        notification_type='system',
                        customer=instance.customer,
                        vendor=None,
                        order=instance
                    )

                    # 4. SEND APOLOGY EMAIL
                    if instance.customer and instance.customer.user_account.email:
                        subject = f"Refund Processed: Order #{instance.order_number}"
                        message = (
                            f"Hi {instance.customer.first_name},\n\n"
                            f"We are writing to confirm that a refund of ₦{amount_refunded:,.2f} for Order #{instance.order_number} "
                            f"has been processed successfully.\n\n"
                            f"This refund was initiated because the order was cancelled. We sincerely apologize for any inconvenience this may have caused.\n\n"
                            f"The funds have been returned to your Luxa Wallet and are available for immediate use or withdrawal.\n\n"
                            f"Best regards,\n"
                            f"The Luxa Team"
                        )
                        
                        try:
                            send_mail(
                                subject=subject,
                                message=message,
                                from_email='Luxa Support <thebrandluxa@gmail.com>',
                                recipient_list=[instance.customer.user_account.email],
                                fail_silently=True
                            )
                            print(f"📧 Refund Email Sent to {instance.customer.user_account.email}")
                        except Exception as e:
                            print(f"⚠️ Failed to send refund email: {e}")                    

# --- 1. TRACK CRAVE ORDER STATUS PRE-SAVE ---
@receiver(pre_save, sender=University_Order)
def track_crave_order_status_change(sender, instance, **kwargs):
    """Remembers the old status before the order saves."""
    if instance.pk:
        try:
            old_instance = University_Order.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except University_Order.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


# --- 2. EXECUTE ESCROW MOVEMENTS ON SAVE ---
@receiver(post_save, sender='luxa_crave.University_Order') 
def manage_crave_escrow_balances(sender, instance, created, **kwargs):
    """
    Handles financial movements for Crave Campus Orders.
    """

    if kwargs.get('raw', False) or created:
        return

    with transaction.atomic():
        customer_wallet = None
        
        if instance.customer:
            customer_wallet = Wallet.objects.filter(
                user=instance.customer.user_account, 
                wallet_type=Wallet.WalletType.CUSTOMER
            ).first()

        # STATUS CHANGE DETECTED
        if hasattr(instance, '_old_status') and instance._old_status != instance.status:
            
            total_amount = instance.total_order_cost

            # --- CASE 1: DELIVERED (Release Funds & Pay Courier) ---
            if instance.status == 'delivered': 
                txn_ref = f"EARN-CRAVE-{instance.order_number}"

                # Check if already paid to prevent double-charging
                if WalletTransaction.objects.filter(reference=txn_ref).exists():
                    return
                
                # A. Customer Side: Unlock the amount. 
                if customer_wallet and customer_wallet.locked_escrow >= total_amount:
                    customer_wallet.locked_escrow -= total_amount
                    customer_wallet.save()
                    
                    WalletTransaction.objects.create(
                        wallet=customer_wallet,
                        transaction_type='PURCHASE_RELEASE',
                        amount=Decimal('0.00'), # Neutral on Available Balance
                        running_balance=customer_wallet.available_balance,
                        reference=txn_ref,
                        description=f"Payment completed for Campus Order #{instance.order_number}"
                    )

                # B. Courier Side: Dynamic Payout Based on Pack Volume
                if hasattr(instance, 'engine_view') and instance.engine_view.assigned_campus_courier:
                    courier_profile = instance.engine_view.assigned_campus_courier
                    
                    # NOTE: Earnings go to the main COURIER wallet
                    courier_wallet = Wallet.objects.filter(
                        user=courier_profile.user_account, 
                        wallet_type=Wallet.WalletType.COURIER
                    ).first()
                    
                    if courier_wallet:
                        pack_count = instance.total_physical_packs_db
                        FLAT_FEE = Decimal('200.00') # 200 flat fee for campus deliveries

                        # --- THE NEW BREAD PAYOUT PATCH ---
                        # 1. Find out how many 'large_bread' items are in this order
                        large_bread_count = 0
                        for pack in instance.packs.all():
                            for item in pack.items.all():
                                if getattr(item.product, 'strange_value', '') == 'large_bread':
                                    # Multiply by item quantity AND the pack's multiplier
                                    large_bread_count += (item.quantity * getattr(pack, 'multiplier', 1))

                        # 2. Calculate effective packs
                        # Subtract 1 courion for every large bread so the courier is only paid for 1, not 2.
                        adjusted_pack_count = pack_count - large_bread_count
                        
                        # Failsafe: Ensure they get paid for at least 1 pack no matter what
                        effective_packs = max(1, adjusted_pack_count)

                        # Calculate final payout
                        courier_fee = effective_packs * FLAT_FEE
                        
                        # Added bread count to the description
                        bread_note = f" (adjusted for {large_bread_count} large breads)" if large_bread_count > 0 else ""

                        # --- NEW: ROUTE THE HAZARD PAY TO THE COURIER ---
                        if getattr(instance, 'wait_fee', False):
                            courier_fee += Decimal('300.00')
                            receipt_description = f"Campus Delivery Payout ({effective_packs} payable packs){bread_note} (+ ₦300 Rush Hour Wait Fee): #{instance.order_number}"
                        else:
                            receipt_description = f"Campus Delivery Payout ({effective_packs} payable packs){bread_note}: #{instance.order_number}"

                        courier_wallet.available_balance += courier_fee
                        courier_wallet.save()
                        
                        WalletTransaction.objects.create(
                            wallet=courier_wallet,
                            transaction_type='CREDIT',
                            amount=courier_fee,
                            running_balance=courier_wallet.available_balance,
                            reference=f"COURIER-CRAVE-{instance.order_number}",
                            description=receipt_description
                        )

                        # --- ADMIN PLATFORM EARNINGS TRACKER ---
                        admin_wallet = Wallet.objects.filter(wallet_type=Wallet.WalletType.ADMIN).first()
                        if admin_wallet:
                            # 1. Customer paid the delivery fee. We subtract what we just paid the courier.
                            cust_delivery_fee = instance.delivery_fee or Decimal('0.00')
                            platform_profit = cust_delivery_fee - courier_fee
                            
                            # 2. Add the net profit to the Admin's Vault
                            admin_wallet.available_balance += platform_profit
                            admin_wallet.save(update_fields=['available_balance'])
                            
                            # 3. Generate the Profit Receipt
                            WalletTransaction.objects.create(
                                wallet=admin_wallet,
                                transaction_type='CREDIT' if platform_profit >= 0 else 'DEBIT',
                                amount=platform_profit,
                                running_balance=admin_wallet.available_balance,
                                reference=f"PROFIT-CRAVE-{instance.order_number}",
                                description=f"Crave Profit (Customer Fee ₦{cust_delivery_fee} - Courier Fee ₦{courier_fee}): #{instance.order_number}"
                            )

            # --- CASE 2: CANCELLED (Refund Customer & Clawback Advance) ---
            elif instance.status == 'cancelled':
                from escrow.services import refund_university_order
                
                refund_result = refund_university_order(instance.order_id) 
                
                if refund_result.get('verified'):
                    amount_refunded = refund_result['refunded_amount']

                    # This guarantees background workers instantly ignore this order
                    if hasattr(instance, 'engine_view') and instance.engine_view:
                        instance.engine_view.status = 'cancelled'
                        instance.engine_view.save(update_fields=['status'])

                    # 1. Create In-App Notification for Customer
                    from MAIN.models import Notification
                    Notification.objects.create(
                        title="Campus Order Refunded",
                        message=f"₦{amount_refunded:,.2f} has been refunded to your wallet for Crave Order #{instance.order_number}.",
                        notification_type='system',
                        customer=instance.customer,
                        vendor=None
                    )

                    # 2. Send Professional Apology Email (IN A BACKGROUND THREAD)
                    if instance.customer and instance.customer.user_account.email:
                        customer_email = instance.customer.user_account.email
                        customer_name = instance.customer.user_account.first_name or "Valued Customer"
                        
                        subject = f"Notice of Cancellation - Luxa Crave Order #{instance.order_number}"
                        message = (
                            f"Dear {customer_name},\n\n"
                            f"We sincerely apologize, but we were unable to fulfill your recent campus delivery (Order #{instance.order_number}) and it has been cancelled.\n\n"
                            f"We understand how frustrating it is to expect a delivery and be disappointed. Please know that a full refund of ₦{amount_refunded:,.2f} has already been credited back to your Luxa Wallet.\n\n"
                            "Our team is actively monitoring these cancellations to ensure better service in the future. We deeply appreciate your patience and hope to serve you better next time.\n\n"
                            "Warm regards,\n"
                            "The Luxa Customer Success Team"
                        )
                        
                        # --- THE FIX: Threading ---
                        import threading
                        from django.core.mail import send_mail
                        
                        def send_cancel_email_bg():
                            try:
                                send_mail(
                                    subject=subject,
                                    message=message,
                                    from_email='Luxa Support <thebrandluxa@gmail.com>',
                                    recipient_list=[customer_email],
                                    fail_silently=True, 
                                )
                            except Exception as e:
                                print(f"Failed to send cancellation email: {e}")
                        
                        # Fire and forget! The server moves on instantly.
                        threading.Thread(target=send_cancel_email_bg).start()

                # --- NEW: LOYALTY PROMO CLAWBACK ---
                if getattr(instance, 'used_daily_promo', False):
                    customer_profile = instance.customer
                    from django.utils import timezone
                    today = timezone.localdate()
                    
                    # Only refund courions if the order was placed TODAY.
                    if customer_profile.last_promo_date == today:
                        order_courions = getattr(instance, 'total_physical_packs_db', 0)
                        new_counter = max(0, customer_profile.promo_daily_counter - order_courions)
                        
                        customer_profile.promo_daily_counter = new_counter
                        customer_profile.save(update_fields=['promo_daily_counter'])
                        print(f"🔄 Promo Clawback: Returned {order_courions} courions to {customer_profile.user_account.username}'s daily allowance.")

                # 3. Clawback (Debit) the advance from the Courier
                # If the order was already batched, it means the courier was already paid in advance!
                if instance.batch:
                    # Safely calculate the food cost
                    delivery_fee = instance.delivery_fee or Decimal('0.00')
                    food_cost_advanced = instance.total_order_cost - delivery_fee
                    
                    if food_cost_advanced > 0:
                        # Grab the specific courier attached to this batch
                        batch_courier_user = instance.batch.courier.user_account
                        
                        # [THE FIX] Query the ADVANCE wallet specifically using the batch_courier_user
                        courier_advance_wallet = Wallet.objects.filter(
                            user=batch_courier_user, 
                            wallet_type=Wallet.WalletType.COURIER_ADVANCE
                        ).first()

                        if courier_advance_wallet:
                            # Debit the money back from the courier's advance
                            courier_advance_wallet.available_balance -= food_cost_advanced
                            courier_advance_wallet.save()
                            
                            WalletTransaction.objects.create(
                                wallet=courier_advance_wallet,
                                transaction_type='DEBIT',
                                amount=-abs(food_cost_advanced), # Ensures it logs as a negative debit
                                running_balance=courier_advance_wallet.available_balance, # [THE FIX] Logs correct balance
                                reference=f"CLAWBACK-{instance.order_id}",
                                description=f"Clawback: Order #{instance.order_number} was cancelled."
                            )

# --- 3. SAFETY NET: CATCH DATABASE DELETIONS ---
@receiver(pre_delete, sender='luxa_crave.University_Order')
def emergency_refund_on_order_deletion(sender, instance, **kwargs):
    """
    If an Admin forcefully deletes an order from the database, this guarantees
    the customer is refunded and the courier's advanced food money is clawed back.
    """
    # If the order is already 'delivered', 'cancelled', or 'refunded', 
    # the money has already been settled, so we do nothing.
    if instance.status not in ['delivered', 'cancelled', 'refunded']:
        from escrow.services import refund_university_order
        
        try:
            with transaction.atomic():
                # 1. Refund the Customer
                refund_result = refund_university_order(instance.order_id)
                
                if refund_result.get('verified'):
                    amount_refunded = refund_result['refunded_amount']

                    # Notify Customer of the emergency cancellation
                    from MAIN.models import Notification
                    Notification.objects.create(
                        title="Order System Deletion",
                        message=f"₦{amount_refunded:,.2f} has been refunded. Your order #{instance.order_number} was removed by the system.",
                        notification_type='system',
                        customer=instance.customer,
                        vendor=None
                    )
                
                # 2. Clawback from Courier (If they already received the advance)
                if instance.batch:
                    food_cost_advanced = instance.total_order_cost - instance.delivery_fee
                    
                    if food_cost_advanced > 0:
                        courier_wallet = Wallet.objects.filter(
                            user=instance.batch.courier.user_account, 
                            wallet_type=Wallet.WalletType.COURIER_ADVANCE # REFUND THE MONIES FROM THE COURIER'S ADVANCE PAYOUT WALLET
                        ).first()
                        
                        if courier_wallet:
                            # Debit the money back from the courier
                            courier_wallet.available_balance -= food_cost_advanced
                            courier_wallet.save()
                            
                            WalletTransaction.objects.create(
                                wallet=courier_wallet,
                                transaction_type='DEBIT',
                                amount=food_cost_advanced,
                                running_balance=courier_wallet.available_balance,
                                reference=f"CLAWBACK-DEL-{instance.order_id}",
                                description=f"Clawback: Order #{instance.order_number} was deleted from the system."
                            )
        except Exception as e:
            # Log the error but don't stop the deletion
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Emergency refund failed during deletion of Order {instance.order_id}: {str(e)}")
