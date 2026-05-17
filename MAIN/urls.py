from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("index/", views.index, name="index"), 
    path("productpage/", views.productpage, name="productpage"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("test/", views.base, name="base"),
    path("categories/", views.categories, name="categories"),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    path("vendor/<int:vendor_id>/", views.vendor_detail, name="vendor_detail"),
    path("customerpage/", views.customerpage, name="customerpage"),
    path("api/address/manage/", views.manage_address, name="manage_address"), # API
    path("api/address/set-default/", views.set_default_address, name="set_default_address"), # API
    path("editprofile/", views.editprofile, name="editprofile"),
    path("api/address/delete/", views.delete_address, name="delete_address"), # API
    path("cart/", views.cart, name="cart"),
    path("vendor-review/", views.vendrev, name="vendrev"),
    path("product3d/<slug:slug>/", views.product3d, name="product3d"),
    path("3d-products/", views.explore_3d_products, name="explore_3d_products"),
    path("vendash/", views.vendash, name="vendash"),
    path('vendor/<int:vendor_id>/add-product/', views.add_product, name='add_product'),
    path("productedit/<int:product_id>/", views.edit_product, name="edit_product"),
    path("productmanage/", views.manage_product, name="manage_product"),
    path("inbox/", views.inbox, name="inbox"),

    # COUNTDOWN PAGE
    path('crave/coming-soon/', views.crave_countdown, name='crave_countdown'),

    # KYC urls
    path("kyc/submit/", views.submit_kyc, name="submit_kyc"),
    path("kyc/info/", views.kyc_info, name="kyc_info"),
    
    # Cart actions
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<int:item_id>/", views.update_cart_item, name="update_cart_item"),
    path("cart/remove/<int:item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("cart/get-variants/<int:product_id>/", views.get_product_variants, name="get_product_variants"),
    path("cart/update-variants/<int:item_id>/", views.update_cart_item_variants, name="update_cart_item_variants"),

    # Checkout
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/create-order/", views.create_order, name="create_order"),

    # Wishlist
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/add/<int:product_id>/", views.add_to_wishlist, name="add_to_wishlist"),
    path("wishlist/remove/<int:product_id>/", views.remove_from_wishlist, name="remove_from_wishlist"),

    # Search
    path("search/", views.search, name="search"),

    # Orders
    path("orders/", views.customer_orders, name="customer_orders"),
    path("orders/<str:order_id>/", views.customer_order_detail, name="customer_order_detail"),
    path("vendor/orders/", views.vendor_product_orders, name="vendor_product_orders"),
    path("vendor/orders/<int:order_id>/", views.vendor_order_detail, name="vendor_order_detail"),
    # Delivery pin setup
    path('setup-pin/', views.setup_delivery_pin, name='setup_delivery_pin'),
    path('change-pin/', views.change_delivery_pin, name='change_delivery_pin'),
    path('pin/request-reset/', views.request_delivery_pin_reset, name='request_delivery_pin_reset'),
    path('pin/reset/<str:token>/', views.reset_delivery_pin, name='reset_delivery_pin'),

    # Notifications
    path("notification/read/<int:notification_id>/", views.mark_notification_read, name="mark_notification_read"),
    # The new polling endpoint
    path('api/check-notifications/', views.check_user_notifications, name='check_user_notifications'),
    path("notification/delete/<int:notification_id>/", views.delete_notification, name="delete_notification"),

    # Product management
    path("product/delete/<int:product_id>/", views.delete_product, name="delete_product"),
    path("product/suspend/<int:product_id>/", views.suspend_product, name="suspend_product"),

    # Order Integration Paths
    # Create a fresh draft (Entry point)
    path("order-draft/create/", views.order_create_form_view, name="order_create_form"),
    # View/Edit an existing draft (The UUID is crucial here!)
    path("order-draft/create/<uuid:draft_id>/", views.order_create_form_view, name="order_edit_form"),
    # --- DISPATCH & GALLERY ---
    path('order-draft/prompt/<uuid:draft_id>/', views.order_dispatch_prompt, name='order_dispatch_prompt'),
    path('order-draft/saved-drafts/', views.saved_orders_list, name='saved_orders_list'),
    # eligibility check 
    path('order-eligibility/<uuid:order_id>/', views.order_eligibility_view, name='order_eligibility'),
    path('order-resolve/<uuid:order_id>/', views.handle_eligibility_failure, name='handle_eligibility_failure'),
    # Delete order
    path('order-draft/delete-draft/<uuid:draft_id>/', views.delete_draft, name='delete_draft'),
    # Proceed to checkout from draft
    path('order-draft/checkout/<uuid:draft_id>/', views.proceed_to_checkout, name='proceed_to_checkout'),
]
