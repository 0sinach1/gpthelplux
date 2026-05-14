"""Regression tests for normalized product variants and cart selections."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.contrib.auth.models import User

from MAIN.models import Cart, CartItem, Category, Customer, Product, ProductVariant, Vendor


class ProductVariantTestCase(TestCase):
    """Shared fixtures for product variant tests."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.customer = Customer.objects.create(
            user_account=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            username="testuser",
        )

        vendor_user = User.objects.create_user(username="vendor", email="vendor@example.com")
        self.vendor = Vendor.objects.create(
            user_account=vendor_user,
            business_name="Test Vendor",
            official_email="vendor@example.com",
            business_address="123 Test St",
            city="Test City",
            state="Test State",
            postal_code="12345",
            country="Test Country",
        )

        self.category = Category.objects.create(name="Test Category", slug="test-category")
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            description="Test description",
            sku="TEST001",
            vendor=self.vendor,
            category=self.category,
            price=100.00,
            stock_quantity=10,
            main_image="products/test-product.jpg",
        )
        self.cart = Cart.objects.create(customer=self.customer)


class ProductVariantModelTest(ProductVariantTestCase):
    """Test normalized product variant behavior."""

    def test_product_variant_helpers_return_available_values(self):
        ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Red")
        ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Blue")
        ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Green", is_available=False)
        ProductVariant.objects.create(product=self.product, variant_type="size", variant_value="L")

        self.assertEqual(set(self.product.get_available_colors()), {"Red", "Blue"})
        self.assertEqual(set(self.product.get_available_sizes()), {"L"})

    def test_duplicate_variant_values_are_rejected_per_product_and_type(self):
        ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Red")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Red")

    def test_same_variant_value_is_allowed_for_different_types(self):
        ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Large")
        ProductVariant.objects.create(product=self.product, variant_type="size", variant_value="Large")

        self.assertEqual(ProductVariant.objects.filter(product=self.product, variant_value="Large").count(), 2)


class CartItemVariantSelectionTest(ProductVariantTestCase):
    """Test cart item behavior with the current many-to-many variant model."""

    def test_multiple_items_without_variants_are_allowed(self):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)

        self.assertEqual(CartItem.objects.filter(cart=self.cart, product=self.product).count(), 2)

    def test_cart_item_can_store_multiple_selected_variants(self):
        color = ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Red")
        size = ProductVariant.objects.create(product=self.product, variant_type="size", variant_value="L")
        item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        item.variants.add(color, size)

        self.assertEqual(set(item.variants.values_list("variant_value", flat=True)), {"Red", "L"})
        self.assertEqual(item.get_variant_description(), "Color: Red, Size: L")

    def test_different_variant_combinations_are_allowed(self):
        red = ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Red")
        blue = ProductVariant.objects.create(product=self.product, variant_type="color", variant_value="Blue")

        red_item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        red_item.variants.add(red)
        blue_item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        blue_item.variants.add(blue)

        self.assertEqual(CartItem.objects.filter(cart=self.cart, product=self.product).count(), 2)
