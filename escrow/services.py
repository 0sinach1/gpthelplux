from decimal import Decimal
from django.db import transaction, IntegrityError
from .models import Wallet, WalletTransaction
from MAIN.models import Order
from django.conf import settings

# Helper to ensure we grab the right wallet
def get_wallet(user, wallet_type):
    return Wallet.objects.select_for_update().get(
        user=user, 
        wallet_type=wallet_type
    )

# ---------------------------------------------------------
# FEE CALCULATION SERVICE FOR MAIN LUXA ORDERS
# Centralizes all order fee logic in escrow app
# ---------------------------------------------------------
def calculate_and_apply_order_fees(order, subtotal, include_delivery=True):
    """
    Args:
        include_delivery (bool): If False, forces delivery fee to 0 (For Sub-Orders).
    """
    from .fee_calculator import calculate_vendor_payout, BASE_DELIVERY_FEE
    
    # Logic: Sub-orders usually have 0 fee because Master pays the global fee
    delivery_fee = BASE_DELIVERY_FEE if include_delivery else Decimal('0.00')
    
    vendor_payout, luxa_cut_amount, luxa_cut_percentage = calculate_vendor_payout(subtotal)
    total = subtotal + delivery_fee
    
    order.delivery_fee = delivery_fee
    order.luxa_cut_percentage = luxa_cut_percentage
    order.luxa_cut_amount = luxa_cut_amount
    order.vendor_payout = vendor_payout
    order.total = total
    order.shipping_cost = Decimal('0.00')
    
    return {
        'delivery_fee': delivery_fee,
        'luxa_cut_percentage': luxa_cut_percentage,
        'luxa_cut_amount': luxa_cut_amount,
        'vendor_payout': vendor_payout,
        'total': total,
    }

def lock_master_order_funds(customer_user, master_order):
    """
    Locks the AGGREGATE amount (All Products + 1 Global Fee) from Customer wallet.
    """
    with transaction.atomic():
        # Reuse your existing helper
        customer_wallet = get_wallet(customer_user, Wallet.WalletType.CUSTOMER)

        if customer_wallet.available_balance < master_order.total_amount:
            raise ValueError(f"Insufficient funds. Required: ₦{master_order.total_amount}")

        # Debit Customer (Move to Locked)
        customer_wallet.available_balance -= master_order.total_amount
        customer_wallet.locked_escrow += master_order.total_amount
        customer_wallet.save()

        # Log Transaction
        WalletTransaction.objects.create(
            wallet=customer_wallet,
            transaction_type='PURCHASE_LOCK',
            amount=-master_order.total_amount,
            running_balance=customer_wallet.available_balance,
            reference=f"{master_order.public_order_id}-LOCK",
            description=f"Payment for Order #{master_order.public_order_id}"
        )

# --- COURIER PAYOUT SERVICE FOR MAIN LUXA ORDERS ---
def process_courier_payout(master_order_id):
    """
    Credits the Courier's wallet when a MasterOrder is verified delivered.
    This is called by signals.py when status changes to 'delivered'.
    """
    from MAIN.models import MasterOrder
    # We import internally to avoid circular dependency errors
    
    with transaction.atomic():
        try:
            # 1. Get the Master Order
            master = MasterOrder.objects.get(id=master_order_id)
            
            # 2. Find the Courier (via the linked Logistics Order)
            # Assuming MasterOrder has a reverse relation 'synchronized_order'
            luxa_order = master.synchronized_order.first()
            
            if not luxa_order or not luxa_order.assigned_courier:
                print(f"⚠️ Payout Skipped: No courier assigned to MasterOrder #{master.public_order_id}")
                return

            courier_profile = luxa_order.assigned_courier
            courier_user = courier_profile.user_account

            # 4. Check Idempotency (Has this specific order already been paid for?)
            # We use a unique reference string: "PAYOUT-{Order_ID}"
            txn_ref = f"PAYOUT-{master.public_order_id}"
            
            if WalletTransaction.objects.filter(reference=txn_ref).exists():
                print(f"ℹ️ Payout Skipped: Courier already paid for #{master.public_order_id}")
                return

            # 5. Credit the Wallet
            # Using get_wallet ensures we lock the row for safety
            wallet = get_wallet(courier_user, Wallet.WalletType.COURIER)
            
            wallet.available_balance += settings.COURIER_FEE
            wallet.save()

            # 6. Create Transaction Record
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='CREDIT',
                amount=settings.COURIER_FEE,
                running_balance=wallet.available_balance,
                reference=txn_ref,
                description=f"Delivery Payout: #{master.public_order_id}"
            )
            
            print(f"💰 PAID ₦{settings.COURIER_FEE} to {courier_user.email} for Order #{master.public_order_id}")
            
            return True

        except Exception as e:
            print(f"❌ Courier Payout Failed: {str(e)}")
            return False


# ---------------------------------------------------------
# STEP 2: START DELIVERY (Vendor Awareness)
# Vendor Pending Balance shows the order payout (after Luxa cut).
# ---------------------------------------------------------
def step_2_start_delivery(vendor, vendor_share, order_id):
    """
    Updates vendor's pending balance when order starts delivery.
    
    Args:
        vendor: User object (the vendor's user account)
        vendor_share: The amount the vendor will receive (after Luxa cut)
                      Should be order.vendor_payout, NOT order.total
        order_id: The order ID for reference
    """
    with transaction.atomic():
        # Get Vendor's BUSINESS Wallet
        vendor_wallet = get_wallet(vendor, Wallet.WalletType.VENDOR)

        # UPDATE: Pending Balance Increases
        # Note: This is the ACTUAL payout amount (subtotal - luxa_cut)
        # NOT the full order total
        vendor_wallet.pending_clearing += vendor_share
        vendor_wallet.save()

# ---------------------------------------------------------
# STEP 3: COMPLETION (Settlement)
# "Money removed from Customer Locked... Vendor receives payout."
# Luxa retains: delivery_fee + luxa_cut_amount
# ---------------------------------------------------------
def step_3_complete_delivery(order_id):
    transaction_ref = f"EARN-{order_id}"

    # 1. OPTIMIZATION: Quick check before locking DB rows
    if WalletTransaction.objects.filter(reference=transaction_ref).exists():
        return

    try:
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id)
            except Order.DoesNotExist:
                raise ValueError("Order does not exist")

            if order.status == 'cancelled': 
                raise ValueError("Security Alert: Attempted to settle a cancelled order.")
            if order.status != 'delivered':
                return 
            if WalletTransaction.objects.filter(reference=transaction_ref).exists():
                return 

            customer_user = order.customer.user_account 
            vendor_user = order.vendor.user_account
            
            # Sub-Order Totals
            # Note: In new system, order.total usually equals order.subtotal (no fee)
            total_amount_to_release = order.total 
            vendor_share = order.vendor_payout if order.vendor_payout else order.subtotal

            # --- EXECUTE TRANSFERS ---

            customer_wallet = get_wallet(customer_user, Wallet.WalletType.CUSTOMER)
            vendor_wallet = get_wallet(vendor_user, Wallet.WalletType.VENDOR)

            # A. Deduct the Product Cost from Locked Escrow
            customer_wallet.locked_escrow -= total_amount_to_release
            
            # B. [FIX] CLEAN UP MASTER FEE
            # If this is the Master Order, we need to handle the flat delivery fee (₦250).
            # We check if there are any other 'active' orders in this master batch.
            # If this is the LAST active order being delivered, we deduct the Global Fee 
            # from locked_escrow so it doesn't get stuck there forever.
            if order.master_order:
                master = order.master_order
                # Check for other items that are NOT delivered/cancelled
                pending_siblings = master.sub_orders.exclude(
                    id=order.id
                ).exclude(
                    status__in=['delivered', 'cancelled', 'refunded']
                ).exists()

                if not pending_siblings:
                    # No more pending shipments. The Master Order is effectively done.
                    # Remove the Global Delivery Fee from Locked Escrow (It is now Revenue).
                    if customer_wallet.locked_escrow >= master.delivery_fee:
                        customer_wallet.locked_escrow -= master.delivery_fee
                        # Optional: Log this as "Platform Fee Release" if you want detailed accounting

            customer_wallet.save()

            # C. Credit Vendor
            vendor_wallet.pending_clearing -= vendor_share
            vendor_wallet.available_balance += vendor_share
            vendor_wallet.save()

            # Log...
            WalletTransaction.objects.create(
                wallet=vendor_wallet,
                transaction_type='PURCHASE_RELEASE',
                amount=vendor_share,
                running_balance=vendor_wallet.available_balance,
                reference=transaction_ref,
                description=f"Sales revenue for Order #{order.order_number}"
            )
    except IntegrityError:
        # This catches the specific "Duplicate Key" error from the Admin double-save
        print(f"ℹ️ Payment skipped: Transaction {transaction_ref} already recorded.")
        return

# ---------------------------------------------------------
# REFUND SERVICE (with verification)
# Returns full amount to customer, removes vendor pending expectation
# Verifies refund before allowing status update to 'refunded'
# ---------------------------------------------------------
def refund_order(order_id):
    refund_ref = f"REFUND-{order_id}"
    
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            raise ValueError("Order does not exist")
        
        # Idempotency check...
        existing = WalletTransaction.objects.filter(reference=refund_ref).first()
        if existing: return {'success': True, 'verified': True}
        
        customer_user = order.customer.user_account
        vendor_user = order.vendor.user_account
        
        # Calculate Base Refund (The Sub-Order total)
        refund_amount = order.total
        
        c_wallet = get_wallet(customer_user, Wallet.WalletType.CUSTOMER)

        # [UPDATED] FEE HANDLING LOGIC
        if order.master_order:
            master = order.master_order
            
            # 1. Are there other active siblings? (Processing/Shipped/Delivered)
            # We exclude 'cancelled'/'refunded' to see what's left.
            active_siblings = master.sub_orders.exclude(id=order.id).exclude(status__in=['cancelled', 'refunded'])
            
            if not active_siblings.exists():
                # CASE A: TOTAL CANCELLATION
                # Everything else is cancelled. Refund the delivery fee too.
                refund_amount += master.delivery_fee
            
            else:
                # CASE B: PARTIAL CANCELLATION (Mixed Bag)
                # Some items are still active. Check if they are ALL 'delivered'.
                non_delivered_active = active_siblings.exclude(status='delivered').count()
                
                if non_delivered_active == 0:
                    # TRAPPED FEE SCENARIO:
                    # All other items are 'Delivered'. The fee was waiting for THIS item.
                    # Since this item is now cancelled, we must CAPTURE the fee (Platform keeps it),
                    # otherwise it stays locked forever.
                    if c_wallet.locked_escrow >= master.delivery_fee:
                        c_wallet.locked_escrow -= master.delivery_fee
                        
                        # Log the Fee Capture (Silent Transaction)
                        WalletTransaction.objects.create(
                            wallet=c_wallet,
                            transaction_type='PURCHASE_RELEASE',
                            amount=Decimal('0.00'),
                            running_balance=c_wallet.available_balance,
                            reference=f"FEE-CLEANUP-{master.public_order_id}",
                            description=f"Delivery Fee Finalized (Remaining items delivered)"
                        )

        vendor_share = order.vendor_payout if order.vendor_payout else order.subtotal
        
        # 1. Unlock Customer Money
        amt_to_unlock = min(refund_amount, c_wallet.locked_escrow)
        c_wallet.locked_escrow -= amt_to_unlock
        c_wallet.available_balance += refund_amount
        c_wallet.save()

        # 2. Remove Vendor Pending Expectation
        v_wallet = get_wallet(vendor_user, Wallet.WalletType.VENDOR)
        if v_wallet.pending_clearing >= vendor_share:
            v_wallet.pending_clearing -= vendor_share
            v_wallet.save()
        
        # 3. Log
        WalletTransaction.objects.create(
            wallet=c_wallet,
            transaction_type='REFUND',
            amount=refund_amount,
            running_balance=c_wallet.available_balance,
            reference=refund_ref,
            description=f"Refund for Order #{order.order_number}"
        )
        
        return {
            'success': True,
            'refunded_amount': refund_amount,
            'verified': True,
            'transaction_ref': refund_ref
        }

# ---------------------------------------------------------
# DEPRECATED: step_4_abort_delivery (kept for backward compatibility)
# Use refund_order() instead for new code
# ---------------------------------------------------------
def step_4_abort_delivery(order_id):
    """
    Deprecated: Use refund_order() instead.
    Kept for backward compatibility with existing code.
    """
    return refund_order(order_id)


# ---------------------------------------------------------
# LUXA CRAVE CAMPUS SERVICES
# ---------------------------------------------------------

def lock_university_order_funds(customer_user, university_order):
    """
    Locks the total amount (Food + Pack + Delivery Fee) from the Customer's wallet 
    for a Crave Campus Order.
    """
    with transaction.atomic():
        customer_wallet = get_wallet(customer_user, Wallet.WalletType.CUSTOMER)
        total_cost = university_order.total_order_cost

        if customer_wallet.available_balance < total_cost:
            raise ValueError(f"Insufficient funds. Required: ₦{total_cost:,.2f}")

        # Debit Customer (Move from Available to Locked)
        customer_wallet.available_balance -= total_cost
        customer_wallet.locked_escrow += total_cost
        customer_wallet.save()

        # Log Transaction
        WalletTransaction.objects.create(
            wallet=customer_wallet,
            transaction_type='PURCHASE_LOCK',
            amount=-total_cost,
            running_balance=customer_wallet.available_balance,
            reference=f"{university_order.order_number}-LOCK",
            description=f"Payment secured for Campus Order #{university_order.order_number}"
        )
        return True

def refund_university_order(order_id):
    """
    Refunds a cancelled Crave Campus Order.
    Returns the locked funds back to the customer's available balance.
    """
    from luxa_crave.models import University_Order # Import here to avoid circular imports
    refund_ref = f"REFUND-{order_id}"
    
    with transaction.atomic():
        try:
            order = University_Order.objects.select_for_update().get(pk=order_id)
        except University_Order.DoesNotExist:
            raise ValueError("Order does not exist")
        
        # Idempotency check: Ensure we haven't already refunded this
        existing = WalletTransaction.objects.filter(reference=refund_ref).first()
        if existing: 
            return {'success': True, 'verified': True, 'refunded_amount': order.total_order_cost}
        
        customer_user = order.customer.user_account
        refund_amount = order.total_order_cost
        
        c_wallet = get_wallet(customer_user, Wallet.WalletType.CUSTOMER)

        # Unlock Customer Money
        amt_to_unlock = min(refund_amount, c_wallet.locked_escrow)
        c_wallet.locked_escrow -= amt_to_unlock
        c_wallet.available_balance += refund_amount
        c_wallet.save()

        # Log Transaction
        WalletTransaction.objects.create(
            wallet=c_wallet,
            transaction_type='REFUND',
            amount=refund_amount,
            running_balance=c_wallet.available_balance,
            reference=refund_ref,
            description=f"Refund for Campus Order #{order.order_number}"
        )
        
        return {
            'success': True,
            'refunded_amount': refund_amount,
            'verified': True,
            'transaction_ref': refund_ref
        }

def advance_payout_courier_for_batch(batch_id):
    """
    Pays the courier IN ADVANCE for the food cost of all valid orders in a batch.
    Calculates per-order to support VIP Fast Lane injections into already-paid batches.
    """
    from couriers.models import DeliveryBatch
    from escrow.models import Wallet, WalletTransaction
    from decimal import Decimal
    from django.db import transaction
    
    with transaction.atomic():
        try:
            batch = DeliveryBatch.objects.select_for_update().get(pk=batch_id)
        except DeliveryBatch.DoesNotExist:
            return {'success': False, 'error': 'Batch does not exist.'}
            
        # Retrieve all orders in this batch that are NOT cancelled
        orders = batch.campus_orders.exclude(status__in=['cancelled', 'pending_cancellation'])
        
        if not orders.exists():
            return {'success': False, 'error': 'No valid orders in this batch to advance.'}
            
        courier_user = batch.courier.user_account
        
        # Assuming get_wallet is imported in this file
        c_wallet = get_wallet(courier_user, Wallet.WalletType.COURIER_ADVANCE)
        
        total_advance_paid_now = Decimal('0.00')
        
        for order in orders:
            # CHANGED TO get the reference of both the order and the batch id so new couriers can be paid again
            order_payout_ref = f"ORDER-ADV-{order.pk}-B-{batch.pk}"
            
            # Check if THIS specific order has already been paid out
            if not WalletTransaction.objects.filter(reference=order_payout_ref).exists():
                food_cost = Decimal(str(order.total_order_cost)) - Decimal(str(order.delivery_fee))
                
                if food_cost > 0:
                    total_advance_paid_now += food_cost
                    
                    # Update balance incrementally
                    c_wallet.available_balance += food_cost
                    c_wallet.save(update_fields=['available_balance'])
                    
                    # Log the transaction PER ORDER for perfect ledger clarity
                    WalletTransaction.objects.create(
                        wallet=c_wallet,
                        transaction_type='CREDIT', 
                        amount=food_cost,
                        running_balance=c_wallet.available_balance,
                        reference=order_payout_ref,
                        description=f"Advance payout for Order {order.order_number[-8:]}"
                    )
                    
        return {
            'success': True,
            'paid_amount': total_advance_paid_now,
            'message': 'Payouts processed for unpaid orders.'
        }    
    