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
        from django.contrib.auth import get_user_model
        from escrow.models import Wallet, WalletTransaction
        from decimal import Decimal
        import uuid

        # 1. Get the User (Replace with your email)
        User = get_user_model()
        user = User.objects.get(email="emmanuelgtaa@gmail.com") 

        # 2. Get the Wallet (Customer or Vendor)
        wallet = Wallet.objects.get(user=user, wallet_type='CUSTOMER') 

        # 3. Add Funds (Update Balance)
        amount = Decimal("80000000.00")
        wallet.available_balance += amount
        wallet.save()

        # 4. Create Transaction (THIS triggers the Signal -> Notification + Email)
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='DEPOSIT',
            amount=amount,
            running_balance=wallet.available_balance,
            reference=f"TEST-{uuid.uuid4().hex[:6].upper()}",
            description="Manual Deposit Test via Console"
        )

        print(f"Deposit Successful! New Balance: {wallet.available_balance}")