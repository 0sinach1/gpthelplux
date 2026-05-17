from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import University_Order, Campus_Engine_Order


@receiver(post_save, sender=Campus_Engine_Order)
def engine_order_trigger_sequence(sender, instance, created, **kwargs):
    """
    STRICT SEQUENCE:
    1. Wait for the Campus_Engine_Order to be saved.
    2. Reach back to the University_Order and lock the pack total.
    3. Trigger the assignment.
    """
    if created:
        # The Campus_Engine_Order (instance) exists, so we get the Order
        raw_order = instance.raw_order 

        if raw_order and raw_order.status == 'pending':
            # STEP 1: Calculate and lock the total in the DB
            current_total = raw_order.total_physical_packs
            raw_order.total_physical_packs_db = current_total
            
            # Save the volume to University_Order before triggering engine
            raw_order.save(update_fields=['total_physical_packs_db'])

            print(f"✅ [SEQUENCE LOCKED] Volume {raw_order.total_physical_packs_db} saved.")
            
            