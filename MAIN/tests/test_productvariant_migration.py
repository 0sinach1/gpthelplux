"""
Tests for ProductVariant migration idempotency and unique constraint behavior.

These tests ensure:
1. Migration can be run multiple times without errors
2. Unique constraint works correctly with nullable variant fields
3. Data integrity is maintained during migration
"""

from django.test import TestCase, TransactionTestCase
from django.core.management import call_command
from django.db import IntegrityError, transaction
from MAIN.models import Product, ProductVariant, Cart, CartItem, Customer, Vendor, Category
from django.contrib.auth.models import User


class ProductVariantMigrationTest(TransactionTestCase):
    """Test migration idempotency and data integrity"""
    
    def setUp(self):
        """Set up test data"""
        # Create user and customer
        self.user = User.objects.create_user(username='testuser', email='test@example.com')
        self.customer = Customer.objects.create(
            user_account=self.user,
            first_name='Test',
            last_name='User',
            email='test@example.com',
            username='testuser'
        )
        
        # Create vendor
        vendor_user = User.objects.create_user(username='vendor', email='vendor@example.com')
        self.vendor = Vendor.objects.create(
            user_account=vendor_user,
            business_name='Test Vendor',
            official_email='vendor@example.com',
            business_address='123 Test St',
            city='Test City',
            state='Test State',
            postal_code='12345',
            country='Test Country'
        )
        
        # Create category
        self.category = Category.objects.create(
            name='Test Category',
            slug='test-category'
        )
        
        # Create product with CSV variants
        self.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            description='Test description',
            sku='TEST001',
            vendor=self.vendor,
            category=self.category,
            price=100.00,
            stock_quantity=10,
            available_colors='Red,Blue,Green',
            available_sizes='S,M,L,XL'
        )
    
    def test_migration_idempotency(self):
        """Test that migration can be run multiple times without errors"""
        # Ensure we're at the right migration state
        call_command('migrate', 'MAIN', '0020', verbosity=0)
        
        # Run data migration first time
        call_command('migrate', 'MAIN', '0021', verbosity=0)
        first_count = ProductVariant.objects.count()
        
        # Run data migration again - should be idempotent
        call_command('migrate', 'MAIN', '0021', verbosity=0)
        second_count = ProductVariant.objects.count()
        
        # Count should be the same (idempotent)
        self.assertEqual(first_count, second_count)
        self.assertGreater(first_count, 0, "ProductVariant rows should be created")
    
    def test_csv_to_productvariant_migration(self):
        """Test that CSV data is correctly migrated to ProductVariant"""
        call_command('migrate', 'MAIN', '0021', verbosity=0)
        
        # Check colors
        color_variants = ProductVariant.objects.filter(
            product=self.product,
            variant_type='color',
            is_available=True
        )
        self.assertEqual(color_variants.count(), 3)
        
        color_values = set(color_variants.values_list('variant_value', flat=True))
        expected_colors = {'Red', 'Blue', 'Green'}
        self.assertEqual(color_values, expected_colors)
        
        # Check sizes
        size_variants = ProductVariant.objects.filter(
            product=self.product,
            variant_type='size',
            is_available=True
        )
        self.assertEqual(size_variants.count(), 4)
        
        size_values = set(size_variants.values_list('variant_value', flat=True))
        expected_sizes = {'S', 'M', 'L', 'XL'}
        self.assertEqual(size_values, expected_sizes)
    
    def test_variant_normalization(self):
        """Test that variant values are normalized correctly"""
        # Create product with messy CSV data
        product = Product.objects.create(
            name='Messy Product',
            slug='messy-product',
            description='Test',
            sku='MESSY001',
            vendor=self.vendor,
            category=self.category,
            price=50.00,
            available_colors='  red  ,  BLUE  ,green  ',
            available_sizes='  s  ,  M  ,  l  '
        )
        
        call_command('migrate', 'MAIN', '0021', verbosity=0)
        
        # Colors should be title case
        colors = ProductVariant.objects.filter(
            product=product,
            variant_type='color'
        ).values_list('variant_value', flat=True)
        self.assertIn('Red', colors)
        self.assertIn('Blue', colors)
        self.assertIn('Green', colors)
        
        # Sizes should be uppercase
        sizes = ProductVariant.objects.filter(
            product=product,
            variant_type='size'
        ).values_list('variant_value', flat=True)
        self.assertIn('S', sizes)
        self.assertIn('M', sizes)
        self.assertIn('L', sizes)


class CartItemUniqueConstraintTest(TestCase):
    """Test unique constraint behavior with nullable variant fields"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', email='test@example.com')
        self.customer = Customer.objects.create(
            user_account=self.user,
            first_name='Test',
            last_name='User',
            email='test@example.com',
            username='testuser'
        )
        
        vendor_user = User.objects.create_user(username='vendor', email='vendor@example.com')
        self.vendor = Vendor.objects.create(
            user_account=vendor_user,
            business_name='Test Vendor',
            official_email='vendor@example.com',
            business_address='123 Test St',
            city='Test City',
            state='Test State',
            postal_code='12345',
            country='Test Country'
        )
        
        self.category = Category.objects.create(name='Test Category', slug='test-category')
        
        self.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            description='Test',
            sku='TEST001',
            vendor=self.vendor,
            category=self.category,
            price=100.00,
            stock_quantity=10
        )
        
        self.cart = Cart.objects.create(customer=self.customer)
    
    def test_multiple_items_without_variants(self):
        """Test that multiple items without variants can be added to cart"""
        # Should allow multiple items with NULL variants
        item1 = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color=None,
            size=None,
            quantity=1
        )
        
        item2 = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color=None,
            size=None,
            quantity=2
        )
        
        # Both items should exist
        self.assertEqual(CartItem.objects.filter(cart=self.cart, product=self.product).count(), 2)
    
    def test_unique_constraint_with_variants(self):
        """Test that items with same variants cannot be duplicated"""
        # Create item with variants
        CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color='Red',
            size='L',
            quantity=1
        )
        
        # Should raise IntegrityError when trying to create duplicate
        with self.assertRaises(IntegrityError):
            CartItem.objects.create(
                cart=self.cart,
                product=self.product,
                color='Red',
                size='L',
                quantity=1
            )
    
    def test_different_variants_allowed(self):
        """Test that items with different variants are allowed"""
        item1 = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color='Red',
            size='L',
            quantity=1
        )
        
        item2 = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color='Blue',
            size='M',
            quantity=1
        )
        
        # Both should exist
        self.assertEqual(CartItem.objects.filter(cart=self.cart, product=self.product).count(), 2)
    
    def test_null_vs_empty_string(self):
        """Test that NULL and empty string are handled correctly"""
        # NULL values should be allowed multiple times
        item1 = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color=None,
            size=None,
            quantity=1
        )
        
        item2 = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            color=None,
            size=None,
            quantity=1
        )
        
        self.assertEqual(CartItem.objects.filter(cart=self.cart, product=self.product).count(), 2)

