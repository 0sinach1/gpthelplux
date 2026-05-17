
def manage_draft_stock(draft, action):
    """
    Handles reserving and releasing stock for Draft Orders.
    action: 'reserve' (Deduct Stock) | 'release' (Return Stock)
    """
    # Import inside function to avoid circular imports if placed in utils
    from .models import Product
    from django.db import transaction

    with transaction.atomic():
        if action == 'reserve':
            # Only reserve if we haven't already
            if not draft.stock_reserved:
                # Lock rows to prevent race conditions
                for item in draft.items.select_related('product').all():
                    product = Product.objects.select_for_update().get(pk=item.product.id)
                    
                    if product.stock_quantity >= item.quantity:
                        product.stock_quantity -= item.quantity
                        product.save()
                    else:
                        # Fail safe: If one item is out of stock, we stop here.
                        # Ideally, you'd raise an error to catch in the view.
                        raise ValueError(f"Insufficient stock for {product.name}")
                
                draft.stock_reserved = True
                draft.save()

        elif action == 'release':
            # Only release if we are currently holding stock
            if draft.stock_reserved:
                for item in draft.items.select_related('product').all():
                    product = Product.objects.select_for_update().get(pk=item.product.id)
                    
                    product.stock_quantity += item.quantity
                    product.save()
                
                draft.stock_reserved = False
                draft.save()