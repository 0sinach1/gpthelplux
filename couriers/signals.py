from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from MAIN.models import MasterOrder, LUXAOrder
from luxa_crave.models import University_Order
from .models import DeliveryBatch
from django.core.mail import mail_admins, send_mail
from django.core.signing import TimestampSigner
from django.urls import reverse
from django.conf import settings
from escrow.models import Wallet, WalletTransaction
from escrow.services import process_courier_payout
from decimal import Decimal

@receiver(post_save, sender=MasterOrder)
def sync_master_to_luxa(sender, instance, created, **kwargs):
    """
    Handles the Genesis Logic:
    1. Awaiting Validation (Gatekeeper)
    2. Pending Cancellation (Pocket)
    3. Restore (3-Step Re-Lock)
    """
    # 1. Locate the internal engine worker
    luxa_order = instance.synchronized_order.first()
    if not luxa_order:
        return

    # Use a transaction to ensure database integrity during complex re-batching
    with transaction.atomic():
        
        # --- TRACK A: THE GATEKEEPER ---
        if instance.status == 'awaiting_validation':
            luxa_order.status = 'completed'
            luxa_order.save()
            _check_batch_burn(luxa_order.batch)

        # --- TRACK B: THE CANCELLATION POCKET ---
        elif instance.status == 'pending_cancellation':
            luxa_order.status = 'pending_cancellation'
            luxa_order.save()
            _check_batch_burn(luxa_order.batch)

        # --- TRACK C: THE RESTORE (3-Step Hierarchy) ---
        elif instance.status == 'shipped': # Courier manually set to 'In Transit'
            _handle_order_restoration(luxa_order, instance.courier)


def _handle_order_restoration(luxa_order, courier):
    """
    Implements the 3-Step Hierarchy:
    Step 1: Original Batch (if Assigned)
    Step 2: Any current Active Batch (Assigned/Forming)
    Step 3: Brand New Batch (Hard Locked to Assigned)
    """
    original_batch = luxa_order.batch
    
    # STEP 1: Check Original Home
    if original_batch and original_batch.status == 'assigned':
        luxa_order.status = 'assigned'
        luxa_order.save()
        return

    # STEP 2: Check for ANY other Active Work
    active_batch = DeliveryBatch.objects.filter(
        courier=courier, 
        status__in=['assigned', 'forming']
    ).first()

    if active_batch:
        luxa_order.batch = active_batch
        luxa_order.status = 'assigned'
        luxa_order.save()
        # Ensure the batch is marked 'assigned' to lock the courier
        if active_batch.status == 'forming':
            active_batch.status = 'assigned'
            active_batch.save()
        return

    # STEP 3: The Fresh Hard Lock
    new_batch = DeliveryBatch.objects.create(
        courier=courier,
        status='assigned' # Hard Lock immediately
    )
    luxa_order.batch = new_batch
    luxa_order.status = 'assigned'
    luxa_order.save()


def _check_batch_burn(batch):
    """
    The Batch Burn Rule:
    If all orders are 'completed' or 'pending_cancellation', the batch is BURNED.
    """
    if not batch:
        return

    unfinished_exists = batch.orders.exclude(
        status__in=['completed', 'pending_cancellation']
    ).exists()

    if not unfinished_exists:
        batch.status = 'completed' # The Burn
        batch.save()
