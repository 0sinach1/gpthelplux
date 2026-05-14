import threading
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from escrow.models import Wallet
from decimal import Decimal

class Command(BaseCommand):
    help = 'Simulates concurrent withdrawals to test database locking'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        
        # 1. SETUP: Create a user with exactly 10,000 Naira
        user, _ = User.objects.get_or_create(username='stress_tester', email='stress@test.com')
        wallet, _ = Wallet.objects.get_or_create(user=user, wallet_type='CUSTOMER')
        
        wallet.available_balance = Decimal("10000.00")
        wallet.save()
        
        self.stdout.write(f"Starting Balance: {wallet.available_balance}")

        # 2. THE ATTACK: Launch 20 threads at once
        # Each thread tries to withdraw 1,000 Naira.
        # If locking works: Final balance should be 0 (10 successful, 10 failed).
        # If locking FAILS: Final balance might be negative, or we lose track.
        
        threads = []
        errors = []

        def attack_wallet():
            try:
                with transaction.atomic():
                    # LOCK THE ROW
                    w = Wallet.objects.select_for_update().get(pk=wallet.pk)
                    
                    amount_to_withdraw = Decimal("1000.00")
                    
                    if w.available_balance >= amount_to_withdraw:
                        # SIMULATE PROCESSING DELAY
                        # This forces threads to wait in line. If locking is broken, they will read old data here.
                        import time
                        time.sleep(0.1) 
                        
                        w.available_balance -= amount_to_withdraw
                        w.save()
                    else:
                        errors.append("Insufficient Funds (Correctly Blocked)")
            except Exception as e:
                errors.append(str(e))

        self.stdout.write("🚀 Launching 20 concurrent withdrawal threads...")
        
        for i in range(20):
            t = threading.Thread(target=attack_wallet)
            threads.append(t)
            t.start()

        # Wait for all to finish
        for t in threads:
            t.join()

        # 3. VERIFY RESULTS
        wallet.refresh_from_db()
        self.stdout.write(f"Final Balance: {wallet.available_balance}")
        self.stdout.write(f"Blocked Attempts: {len(errors)}")

        if wallet.available_balance == 0 and len(errors) == 10:
             self.stdout.write(self.style.SUCCESS("✅ TEST PASSED: Locking prevented double-spending!"))
        elif wallet.available_balance < 0:
             self.stdout.write(self.style.ERROR("❌ TEST FAILED: Balance went negative! Locking is broken."))
        else:
             self.stdout.write(self.style.WARNING(f"⚠️ TEST INCONCLUSIVE. Balance: {wallet.available_balance}"))