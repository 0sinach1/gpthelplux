
from django.test import TestCase
from decimal import Decimal
from django.contrib.auth.models import User
from .models import Wallet  # Import from your wallets app
from MAIN.models import Customer, Vendor, Order # Import from your main app

# Import the service function we just wrote
from .services import step_3_complete_delivery, step_1_checkout_lock

class WalletSystemStressTest(TestCase):
    def setUp(self):
        # 1. Create Base Users
        self.user_cust = User.objects.create_user(username="buyer", email="b@test.com", password="pw")
        self.user_vend = User.objects.create_user(username="seller", email="s@test.com", password="pw")

        # 2. Create Profiles (REQUIRED by your models)
        self.customer_profile = Customer.objects.create(
            user_account=self.user_cust,
            first_name="John", last_name="Doe", email="b@test.com"
        )
        self.vendor_profile = Vendor.objects.create(
            user_account=self.user_vend,
            business_name="Super Shop", official_email="s@test.com",
            currency_code="NGN"
        )

        # 3. Setup Wallets (Fund the customer)
        c_wallet, _ = Wallet.objects.get_or_create(
            user=self.user_cust, 
            wallet_type=Wallet.WalletType.CUSTOMER
        )
        c_wallet.available_balance = Decimal("20000.00")
        c_wallet.save()

        Wallet.objects.get_or_create(
            user=self.user_vend, 
            wallet_type=Wallet.WalletType.VENDOR
        )

        # 4. Create an Order
        self.order = Order.objects.create(
            customer=self.customer_profile,
            vendor=self.vendor_profile,
            subtotal=Decimal("10000.00"),
            total=Decimal("10000.00"),
            shipping_address="Lagos", shipping_city="Ikeja", 
            shipping_state="Lagos", shipping_postal_code="100001",
            status='delivered' # Start as delivered for the success test
        )

    def test_security_cancelled_order_payout(self):
        """
        Scenario: A user cancelled the order, but a bug tries to pay the vendor anyway.
        """
        # 1. Lock funds initially (Step 1)
        # Note: step_1 usually takes the User object directly
        step_1_checkout_lock(self.user_cust, self.order.total, self.order.id)

        # 2. Set Order to CANCELLED (Use the lowercase key from your model)
        self.order.status = 'cancelled'
        self.order.save()

        # 3. Attempt to payout (Step 3) - SHOULD FAIL
        try:
            step_3_complete_delivery(self.order.id)
            print("❌ FAILURE: The system paid out a cancelled order!")
        except ValueError as e:
            print(f"✅ PASSED: System blocked cancelled order. Error: {e}")

        # 4. Verify balances
        v_wallet = Wallet.objects.get(user=self.user_vend, wallet_type='VENDOR')
        self.assertEqual(v_wallet.available_balance, Decimal("0.00"))

    def test_idempotency_double_payout(self):
        """
        Scenario: The function runs twice (network glitch). 
        Vendor should only get paid ONCE.
        """
        # 1. Lock funds
        step_1_checkout_lock(self.user_cust, self.order.total, self.order.id)
        
        # 2. Ensure order is valid
        self.order.status = 'delivered'
        self.order.save()

        # 3. Run Step 3 TWICE
        step_3_complete_delivery(self.order.id) # First time
        step_3_complete_delivery(self.order.id) # Second time (Should be ignored)

        # 4. Verify Vendor Balance is 10,000 (not 20,000)
        v_wallet = Wallet.objects.get(user=self.user_vend, wallet_type='VENDOR')
        self.assertEqual(v_wallet.available_balance, Decimal("10000.00"))
        print("✅ PASSED: Double payout prevented.")