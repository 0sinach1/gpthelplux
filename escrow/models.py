from django.db import models
from django.db.models import CheckConstraint, Q
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.hashers import make_password, check_password
import uuid

class Wallet(models.Model):
    class WalletType(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer Personal'
        VENDOR = 'VENDOR', 'Vendor Business'
        COURIER = 'COURIER', 'Courier Earnings'
        COURIER_ADVANCE = 'COURIER_ADVANCE', 'Advance Payout account to get the food'
        ADMIN = 'ADMIN', 'Admin (Platform)'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallets')
    wallet_type = models.CharField(max_length=20, choices=WalletType.choices, default=WalletType.CUSTOMER)
    currency = models.CharField(max_length=3, default='NGN')
    paystack_recipient_code = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        help_text="The Paystack code (RCP_xxx) for this user's bank account."
    )
    
    # The 3 Buckets
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    locked_escrow = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    pending_clearing = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'wallet_type'] # One user, one wallet of each type
        constraints = [
            # This ensures the database REJECTS any save that makes balance negative
            CheckConstraint(condition=Q(available_balance__gte=0), name='available_balance_non_negative'),
            CheckConstraint(condition=Q(locked_escrow__gte=0), name='locked_escrow_non_negative'),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.wallet_type} ({self.currency})"

class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'Deposit'),
        ('PURCHASE_LOCK', 'Purchase (Escrow Lock)'),
        ('PURCHASE_RELEASE', 'Purchase (Vendor Credit)'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('REFUND', 'Refund'),
        ('CREDIT', 'Credit'),
    )

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    # Amount can be positive (credit) or negative (debit)
    amount = models.DecimalField(max_digits=12, decimal_places=2) 
    
    # Snapshot of balance AFTER this transaction (for auditing)
    running_balance = models.DecimalField(max_digits=12, decimal_places=2) 
    
    description = models.CharField(max_length=255)
    
    # Critical for security: Store the Paystack Reference or Order ID here
    reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=50, null=True, blank=True, unique=True) 
    
    timestamp = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        # 1. Check if this is a brand new transaction being created
        is_new_transaction = self.pk is None
        
        # 2. Save the transaction to the database normally first
        super().save(*args, **kwargs)
        
        # 3. The Auto-Updater Logic
        if is_new_transaction:
            # Check if this receipt belongs to a Courier's earnings wallet
            if self.wallet.wallet_type == 'COURIER':
                # Check if it is actually adding money (Credit/Release) and not a penalty or withdrawal
                if self.transaction_type in ['CREDIT', 'PURCHASE_RELEASE'] and self.amount > 0:
                    user = self.wallet.user
                    
                    # Safely check if the user is actually a courier
                    if hasattr(user, 'courier_profile'):
                        courier = user.courier_profile
                        
                        # Increment their total earnings
                        courier.total_earnings += self.amount
                        
                        # Save ONLY the total_earnings field to prevent locking the whole model
                        courier.save(update_fields=['total_earnings'])

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"

# Wallet security model
class WalletSecurity(models.Model):
    """
    Stores security details (PIN) linked to the User, 
    so it applies to BOTH Customer and Vendor wallets.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet_security')
    pin_hash = models.CharField(max_length=128)
    failed_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)
        self.save()

    def check_pin(self, raw_pin):
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return f"Security for {self.user.username}"

class BankAccount(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100) # e.g. "GTBank"
    bank_code = models.CharField(max_length=10)  # e.g. "058"
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=200) # e.g. "MOSES ..."
    
    # CRITICAL: This is what you need to send money via API
    paystack_recipient_code = models.CharField(max_length=100, help_text="RCP code from Paystack")
    
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('wallet', 'account_number', 'bank_code')

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"
