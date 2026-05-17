import random
import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction

# Adjust imports to match your project apps
from MAIN.models import Product, Customer, MasterOrder, Order, OrderItem, LUXAOrder, Vendor

# # Try importing the engine; skip if it fails (so script doesn't crash)
# try:
#     from decision_engine.engine_core import DecisionEngine
# except ImportError:
#     DecisionEngine = None

User = get_user_model()

class Command(BaseCommand):
    help = 'Populates the database with random orders and triggers the Courier Engine.'

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, nargs='?', default=7, help='Number of orders to create')

    def handle(self, *args, **options):
        num_orders = options['total']
        self.stdout.write(self.style.WARNING(f"🚀 Starting generation of {num_orders} random orders..."))

        # 1. FETCH PREREQUISITES
        products = list(Product.objects.filter(stock_quantity__gt=0))
        if not products:
            self.stdout.write(self.style.ERROR("❌ Error: No products found with stock > 0. Please create products first."))
            return

        # 2. CREATE DUMMY CUSTOMER
        user, _ = User.objects.get_or_create(username="TestCustomer", defaults={'email': 'test@luxa.ng'})
        customer, _ = Customer.objects.get_or_create(user_account=user, defaults={
            'first_name': 'Test', 
            'last_name': 'Buyer', 
            'phone_number': '08012345678'
        })

        # 3. DEFINE FAKE LOCATIONS (Lagos)
        LOCATIONS = [
            {'address': '123 Admiralty Way', 'city': 'Lekki', 'lat': 6.45, 'lng': 3.45},
            {'address': '45 Isaac John', 'city': 'Ikeja', 'lat': 6.58, 'lng': 3.35},
            {'address': '101 Victoria Island', 'city': 'VI', 'lat': 6.42, 'lng': 3.42},
            {'address': 'Banana Island Road', 'city': 'Ikoyi', 'lat': 6.46, 'lng': 3.44},
        ]

        # 4. LOOP TO CREATE ORDERS
        created_count = 0
        
        for i in range(num_orders):
            try:
                loc = random.choice(LOCATIONS)
                
                with transaction.atomic():
                    # --- A. PICK RANDOM DATA ---
                    selected_products = random.sample(products, k=random.randint(1, 3))
                    
                    # --- B. PREPARE VENDOR GROUPS ---
                    vendor_groups = {}
                    for prod in selected_products:
                        if prod.vendor not in vendor_groups:
                            vendor_groups[prod.vendor] = []
                        vendor_groups[prod.vendor].append({'product': prod, 'quantity': random.randint(1, 3)})

                    # --- C. CREATE MASTER ORDER ---
                    master_public_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
                    GLOBAL_DELIVERY_FEE = Decimal('250.00')
                    
                    master_order = MasterOrder.objects.create(
                        public_order_id=master_public_id,
                        customer=customer,
                        total_amount=Decimal('0.00'),
                        delivery_fee=GLOBAL_DELIVERY_FEE,
                        payment_status='paid',
                        is_kyc_verified=True
                    )

                    grand_total = Decimal('0.00')
                    sub_order_index = 1
                    
                    # Payloads for LUXAOrder
                    all_products_payload = {}
                    all_vendors_payload = {}
                    all_pickup_payload = {}
                    all_configs_payload = {}  # <--- [NEW] Initialize Config Payload
                    
                    # --- D. PROCESS VENDORS ---
                    for vendor, items in vendor_groups.items():
                        subtotal = Decimal('0.00')
                        
                        for item in items:
                            p = item['product']
                            qty = item['quantity']
                            subtotal += p.price * qty
                            
                            p_id = str(p.id)
                            all_products_payload[p_id] = {
                                'name': p.name,
                                'quantity': qty,
                                'price': float(p.price),
                                'image': p.main_image.url if p.main_image else ""
                            }
                            
                            # --- [NEW] GENERATE RANDOM CONFIGS ---
                            # This simulates the user selecting options on the frontend
                            all_configs_payload[p_id] = {
                                'Color': random.choice(['Midnight Blue', 'Matte Black', 'Silver', 'Rose Gold']),
                                'Size': random.choice(['M', 'L', 'XL', 'XXL']),
                                'Material': random.choice(['Cotton', 'Polyester', 'Leather'])
                            }

                            # Fake pickup lat/lng for engine
                            all_pickup_payload[p_id] = {
                                'address': vendor.business_address,
                                'latitude': 6.50 + (random.random() * 0.1),
                                'longitude': 3.30 + (random.random() * 0.1)
                            }

                        all_vendors_payload[str(vendor.id)] = {
                            'business_name': vendor.business_name,
                            'address': vendor.business_address,
                            'phone': vendor.official_phone
                        }

                        Order.objects.create(
                            master_order=master_order,
                            order_number=f"{master_public_id}-{sub_order_index}",
                            customer=customer,
                            vendor=vendor,
                            subtotal=subtotal,
                            total=subtotal,
                            delivery_type='standard_delivery',
                            payment_status='paid',
                            shipping_city=loc['city']
                        )
                        grand_total += subtotal
                        sub_order_index += 1

                    master_order.total_amount = grand_total + GLOBAL_DELIVERY_FEE
                    master_order.save()

                    # --- E. CREATE LUXAORDER (With Configs) ---
                    is_cancelled = random.random() < 0.2
                    status = "pending_cancellation" if is_cancelled else "Pending Assignment"

                    luxa_order = LUXAOrder.objects.create(
                        order_source=master_order,
                        order_id=master_public_id,
                        customer_id=str(customer.id),
                        delivery_type='standard_delivery',
                        status=status,
                        total_price=master_order.total_amount,
                        products=all_products_payload,
                        vendors=all_vendors_payload,
                        product_configurations=all_configs_payload, # <--- [NEW] Pass the configs here
                        pickup_locations=all_pickup_payload,
                        delivery_location={
                            'address': loc['address'],
                            'city': loc['city'],
                            'latitude': loc['lat'],
                            'longitude': loc['lng']
                        }
                    )
                    
                    created_count += 1
                    self.stdout.write(f"   Created Order {master_public_id} ({status})")


            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to create order {i}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\n✨ Done! Created {created_count} orders. Check your Courier Dashboard."))