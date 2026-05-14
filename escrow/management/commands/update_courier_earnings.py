from django.core.management.base import BaseCommand
from decimal import Decimal
from django.db.models import Sum
from couriers.models import Courier
from escrow.models import Wallet, WalletTransaction

class Command(BaseCommand):
    help = 'Calculates and updates the total_earnings field for all couriers based on ₦200 and ₦250 wallet deposits.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("🚀 Starting Courier Earnings Calculation..."))
        
        couriers = Courier.objects.select_related('user_account').all()
        updated_count = 0
        total_system_payouts = Decimal('0.00')
        target_amounts = [Decimal('200.00'), Decimal('250.00')]

        for courier in couriers:
            user = courier.user_account
            
            # Find their COURIER (Earnings) wallet
            wallet = Wallet.objects.filter(user=user, wallet_type='COURIER').first()
            
            if not wallet:
                # If they don't have a courier wallet, set to 0
                courier.total_earnings = Decimal('0.00')
                courier.save(update_fields=['total_earnings'])
                self.stdout.write(f"⚠️  Skipped @{user.username}: No COURIER wallet found. Set to ₦0.00")
                continue
                
            # Sum the matched transactions
            earnings_agg = WalletTransaction.objects.filter(
                wallet=wallet,
                amount__in=target_amounts,
                transaction_type__in=['CREDIT', 'PURCHASE_RELEASE'] 
            ).aggregate(total=Sum('amount'))
            
            total_earned = earnings_agg['total'] or Decimal('0.00')
            
            # Save to the new field
            courier.total_earnings = total_earned
            courier.save(update_fields=['total_earnings'])
            
            updated_count += 1
            total_system_payouts += total_earned
            
            self.stdout.write(self.style.SUCCESS(f"✅ Updated @{user.username}: ₦{total_earned:,.2f}"))

        self.stdout.write(self.style.WARNING("-" * 40))
        self.stdout.write(self.style.SUCCESS(f"🎉 DONE! Successfully updated {updated_count} couriers."))
        self.stdout.write(self.style.SUCCESS(f"💰 Total earnings validated across platform: ₦{total_system_payouts:,.2f}"))