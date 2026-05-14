def execute_order_restore(order_id, courier_profile):
    """
    Executes the 3-Way Hierarchy Restore Logic for cancelled orders.
    Prevents the Decision Engine from double-booking by forcing hard-locks.
    """
    from couriers.models import DeliveryBatch
    from django.db import transaction
    from .network_providers import NetworkOrderResolver
    import uuid

    # 1. Resolve the order using your existing Network Resolver
    order, network = NetworkOrderResolver.get_order_by_id(order_id)
    if not order:
        return {"status": "error", "error": "Order not found"}

    with transaction.atomic():
        # Lock the raw order to prevent race conditions
        if network == 'campus':
            from luxa_crave.models import University_Order
            # FIXED: Safely query using order_id instead of id
            raw_order = University_Order.objects.select_for_update().get(order_id=order_id)
            old_batch = raw_order.batch
            engine_order = raw_order.engine_view
        elif network == 'standard':
            from MAIN.models import LUXAOrder
            # FIXED: LUXAOrder uses order_id as its primary key, so .id does not exist!
            raw_order = LUXAOrder.objects.select_for_update().get(order_id=order_id)
            old_batch = raw_order.batch

        target_batch = None

        # --- WAY 1: ORIGINAL HOME ---
        # If the original batch is still actively in transit, return it there.
        if old_batch and old_batch.status == 'in_transit':
            target_batch = old_batch

        # --- WAY 2: MIGRATION ---
        # Original batch is gone, but courier has another active batch we can piggyback on.
        if not target_batch:
            active_batch = DeliveryBatch.objects.filter(
                courier=courier_profile,
                status__in=['forming', 'assigned', 'in_transit']
            ).order_by('-created_at').first()
            
            if active_batch:
                target_batch = active_batch

        # --- WAY 3: FRESH HARD LOCK ---
        # Courier is empty-handed. Create a new bag and lock it instantly.
        if not target_batch:
            target_batch = DeliveryBatch.objects.create(
                courier=courier_profile,
                status='assigned',  # CRITICAL: Skips 'forming' so the Engine ignores it
                batch_id=f"BCH-RES-{uuid.uuid4().hex[:8].upper()}"
            )

        # --- APPLY THE RESTORE ---
        # Inherit the exact status of whatever batch we just dropped it into
        new_raw_status = 'in_transit' if target_batch.status == 'in_transit' else 'processing'
        new_courier_status = 'shipped' if target_batch.status == 'in_transit' else 'assigned'

        if network == 'campus':
            raw_order.batch = target_batch
            raw_order.status = new_raw_status
            raw_order.save(update_fields=['batch', 'status'])
            
            engine_order.status = new_courier_status
            engine_order.assigned_campus_courier = courier_profile
            engine_order.save(update_fields=['status', 'assigned_campus_courier'])
            
            # Recalculate Bag Volume
            from django.db.models import Sum
            agg = University_Order.objects.filter(batch=target_batch).aggregate(total=Sum('total_physical_packs_db'))
            target_batch.total_volume = agg['total'] or 0
            target_batch.save(update_fields=['total_volume'])

        elif network == 'standard':
            raw_order.batch = target_batch
            # Using assigned instead of shipped for the initial state of restored standard orders
            raw_order.status = new_courier_status 
            raw_order.assigned_courier = courier_profile
            raw_order.save(update_fields=['batch', 'status', 'assigned_courier'])

            # Sync with MasterOrder to ensure consistency
            if raw_order.order_source:
                raw_order.order_source.status = 'pending' if new_courier_status == 'assigned' else 'shipped'
                raw_order.order_source.save(update_fields=['status'])

        return {"status": "success", "message": f"Order restored to Batch {target_batch.batch_id[-6:]}"}    