from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from escrow.models import Wallet, WalletTransaction
from MAIN.models import Order, Vendor, MasterOrder  # Added MasterOrder

class Command(BaseCommand):
    help = 'Repairs wallet balances: Creates missing wallets, fixes missed payouts, and resyncs locks.'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING WALLET REPAIR SYSTEM (MASTER ORDER COMPATIBLE) ---")

        ACTIVE_STATUSES = ['pending', 'processing', 'shipped', 'in_transit']
        COMPLETED_STATUS = 'delivered'

        with transaction.atomic():
            # ====================================================
            # STEP 1: BACKFILL MISSING VENDOR WALLETS
            # ====================================================
            self.stdout.write("\n1. Checking for vendors without wallets...")
            
            all_vendors = Vendor.objects.all()
            wallets_created = 0
            
            for vendor in all_vendors:
                wallet, created = Wallet.objects.get_or_create(
                    user=vendor.user_account,
                    wallet_type='VENDOR',
                    defaults={
                        'currency': 'NGN',
                        'available_balance': 0,
                        'pending_clearing': 0
                    }
                )
                if created:
                    wallets_created += 1

            self.stdout.write(self.style.SUCCESS(f"Step 1 Complete: {wallets_created} missing wallets created."))

            # ====================================================
            # STEP 2: FIX MISSING PAYOUTS (Retroactive Pay)
            # ====================================================
            # Note: This logic remains valid because vendors are paid based on Sub-Orders
            self.stdout.write("\n2. Checking for 'Delivered' orders that were never paid out...")
            
            delivered_orders = Order.objects.filter(status=COMPLETED_STATUS)
            payouts_fixed = 0
            
            for order in delivered_orders:
                # The reference we EXPECT to see if they were paid
                expected_ref = f"EARN-{order.order_number}"
                
                # If this transaction doesn't exist, they weren't paid.
                if not WalletTransaction.objects.filter(reference=expected_ref).exists():
                    if order.vendor:
                        vendor_wallet = Wallet.objects.get(
                            user=order.vendor.user_account, 
                            wallet_type='VENDOR'
                        )
                        
                        # Calculate what they should have been paid
                        # Uses vendor_payout (new system) or subtotal (old system)
                        payout_amount = order.vendor_payout if order.vendor_payout > 0 else order.subtotal
                        
                        # Credit the Vendor
                        vendor_wallet.available_balance += payout_amount
                        vendor_wallet.save()
                        
                        # Create the Missing Transaction Record
                        WalletTransaction.objects.create(
                            wallet=vendor_wallet,
                            transaction_type='PURCHASE_RELEASE',
                            amount=payout_amount,
                            running_balance=vendor_wallet.available_balance,
                            reference=expected_ref,
                            description=f"Retroactive Payout for Order #{order.order_number}"
                        )
                        payouts_fixed += 1
                        self.stdout.write(f"   -> Paid {order.vendor.business_name} for Order {order.order_number} (₦{payout_amount})")

            self.stdout.write(self.style.SUCCESS(f"Step 2 Complete: {payouts_fixed} missing payouts processed."))

            # ====================================================
            # STEP 3: RESYNC ESCROW & PENDING (The Clean Slate)
            # ====================================================
            self.stdout.write("\n3. Resyncing Locked Escrow and Pending Balances...")
            
            # A. Wipe all locks to 0.00 first (Clean Slate)
            Wallet.objects.all().update(locked_escrow=0, pending_clearing=0)
            
            # --- VENDOR SIDE (Pending Clearing) ---
            # Group active Sub-Orders by vendor
            vendors_pending = Order.objects.filter(status__in=ACTIVE_STATUSES)
            vendor_totals = {} 
            
            for order in vendors_pending:
                if order.vendor:
                    v_user_id = order.vendor.user_account.id
                    # New system uses vendor_payout, old might use subtotal
                    amount = order.vendor_payout if order.vendor_payout and order.vendor_payout > 0 else order.subtotal
                    
                    if v_user_id not in vendor_totals: vendor_totals[v_user_id] = Decimal('0.00')
                    vendor_totals[v_user_id] += amount
            
            # Apply Vendor Updates
            for user_id, total in vendor_totals.items():
                Wallet.objects.filter(user_id=user_id, wallet_type='VENDOR').update(pending_clearing=total)
            
            self.stdout.write(f"   -> Updated pending balances for {len(vendor_totals)} vendors.")

            # --- CUSTOMER SIDE (Locked Escrow) ---
            # [CRITICAL FIX]: We must sum Sub-Orders (Products) AND MasterOrders (Delivery Fee)
            
            customer_totals = {}

            # 1. Sum Active Sub-Orders (The Products)
            # We iterate to ensure we get the right user ID mapping
            active_sub_orders = Order.objects.filter(status__in=ACTIVE_STATUSES).select_related('customer__user_account')
            
            for order in active_sub_orders:
                c_user_id = order.customer.user_account.id
                if c_user_id not in customer_totals: customer_totals[c_user_id] = Decimal('0.00')
                
                # order.total in the new system excludes delivery fee, which is correct here
                customer_totals[c_user_id] += order.total

            # 2. Sum Active MasterOrders (The Global Delivery Fee)
            # A MasterOrder is "Active" if it's not Delivered/Cancelled/Refunded
            active_masters = MasterOrder.objects.exclude(
                status__in=['delivered', 'cancelled', 'refunded']
            ).select_related('customer__user_account')

            for master in active_masters:
                c_user_id = master.customer.user_account.id
                if c_user_id not in customer_totals: customer_totals[c_user_id] = Decimal('0.00')
                
                # Add the global delivery fee (usually ₦250) to the lock
                customer_totals[c_user_id] += master.delivery_fee

            # Apply Customer Updates
            for user_id, total in customer_totals.items():
                Wallet.objects.filter(
                    user_id=user_id, 
                    wallet_type='CUSTOMER'
                ).update(locked_escrow=total)

            self.stdout.write(f"   -> Updated locked escrow for {len(customer_totals)} customers.")
            self.stdout.write(self.style.SUCCESS("Step 3 Complete: Balances synced (including Master Order fees)."))
            self.stdout.write(self.style.SUCCESS("\n--- REPAIR SUCCESSFUL ---"))