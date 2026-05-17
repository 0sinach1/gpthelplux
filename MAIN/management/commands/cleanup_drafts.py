# MAIN/management/commands/cleanup_drafts.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.db.models import F
from MAIN.models import DraftOrder, Product

class Command(BaseCommand):
    help = 'Deletes draft orders older than 48 hours and restores their reserved stock'

    def handle(self, *args, **kwargs):
        # 1. Define the "Cut-off" time (Now minus 48 hours)
        # Example: If it's Friday 2:00 PM, cutoff is Wednesday 2:00 PM.
        cutoff_time = timezone.now() - timedelta(hours=48)
        
        # 2. Find all drafts created BEFORE the cutoff
        expired_drafts = DraftOrder.objects.filter(created_at__lte=cutoff_time)
        
        count = 0
        
        if not expired_drafts.exists():
            self.stdout.write("No expired drafts found.")
            return

        self.stdout.write(f"Found {expired_drafts.count()} expired drafts. Cleaning up...")

        for draft in expired_drafts:
            try:
                with transaction.atomic():
                    # A. RESTORE STOCK (If we reserved it)
                    if draft.stock_reserved:
                        for item in draft.items.all():
                            # Atomic update to avoid race conditions
                            Product.objects.filter(pk=item.product.id).update(
                                stock_quantity=F('stock_quantity') + item.quantity
                            )
                        self.stdout.write(f" - Returned stock for Draft {str(draft.id)[:8]}")

                    # B. DELETE THE DRAFT
                    draft.delete()
                    count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error cleaning draft {draft.id}: {e}"))
                
        self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} drafts.'))