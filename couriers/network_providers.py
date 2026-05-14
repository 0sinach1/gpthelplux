from django.db.models import Prefetch
from MAIN.models import LUXAOrder
from luxa_crave.models import Campus_Engine_Order, University_Order

class BaseNetworkProvider:
    """The Blueprint for all future networks."""
    def get_buckets(self, courier):
        return {'new': [], 'transit': [], 'history': [], 'returns': []}

class StandardNetworkProvider(BaseNetworkProvider):
    def get_data(self, courier):
        # --- THE FIX ---
        # We define a custom Prefetch to exclude cancelled orders.
        # This prevents cancelled orders from showing up when you call batch.orders.all()
        valid_orders_prefetch = Prefetch(
            'orders', 
            queryset=LUXAOrder.objects.exclude(status__in=['pending_cancellation', 'cancelled'])
        )

        from couriers.models import DeliveryBatch
        
        batches = DeliveryBatch.objects.filter(
            courier=courier,
            orders__isnull=False 
        ).distinct().prefetch_related(
            valid_orders_prefetch, # <-- Replaced the string 'orders' with the Prefetch object
            'orders__order_source__customer',
            'orders__order_source__sub_orders' 
        ).order_by('-created_at')
        

        for batch in batches:
            for order in batch.orders.all():
                # Manually forcing the Standard layout here
                addr_str = "No Address"
                if order.delivery_location:
                    if isinstance(order.delivery_location, dict):
                        addr_str = order.delivery_location.get('address', "No Address")
                    else:
                        addr_str = order.delivery_location.address
                order.is_standard_data = {
                    "customer_name": order.order_source.customer.full_name,
                    "delivery_location": addr_str,
                    "order_id": order.order_id,
                    "authorized_photo": order.order_source.customer.profile_picture.url if order.order_source.customer.profile_picture else None,
                    "internal_id": order.order_id,
                    "Volume": getattr(order, 'volume', 1) 
                }

        return {
            'new': batches.filter(status='assigned'),
            'transit': batches.filter(status='in_transit'),
            'history': batches.filter(status='completed')[:10],
            # Cancelled orders safely go to the 'returns' bucket
            'returns': LUXAOrder.objects.filter(
                assigned_courier=courier, 
                status__in=['pending_cancellation', 'cancelled']
            ),
            'forming': batches.filter(status='forming'),
        }
    

    def get_prefetch_requirements(self):
        """Instructions for Standard E-commerce orders"""
        return [
            Prefetch('orders', queryset=LUXAOrder.objects.exclude(
                status__in=['pending_cancellation', 'cancelled']
            ).select_related('order_source', 'order_source__customer'))
        ]
    
    @staticmethod
    def activate_transit(batch):
        """Updates all LUXA orders in a batch to shipped status."""
        if hasattr(batch, 'orders'):
            for luxa_order in batch.orders.all():
                luxa_order.status = 'shipped'
                luxa_order.save()
                if luxa_order.order_source:
                    luxa_order.order_source.status = 'shipped'
                    luxa_order.order_source.save()

    def get_manifest_context(self, order):
        # Standard orders use the default order items list
        return {
            "order": order, 
            "is_campus": False,
            "template": "couriers/snippets/standard_manifest.html"
        } # Future proof        }




class CampusNetworkProvider(BaseNetworkProvider):
    def get_data(self, courier):
        from couriers.models import DeliveryBatch
        from luxa_crave.models import Campus_Engine_Order
        
        # --- THE FIX ---
        # Same logic: filter out the cancelled campus orders from the batch
        valid_campus_orders_prefetch = Prefetch(
            'campus_orders', 
            queryset=University_Order.objects.exclude(status__in=['pending_cancellation', 'cancelled'])
        )

        batches = DeliveryBatch.objects.filter(
            courier=courier,
            campus_orders__isnull=False
        ).distinct().prefetch_related(
            valid_campus_orders_prefetch, # <-- Applied the Prefetch object
            'campus_orders__customer', 
            'campus_orders__building', 
            'campus_orders__location_category', 
            'campus_orders__engine_view' 
        ).order_by('-created_at')

        return {
            'new': batches.filter(status='assigned'),
            'transit': batches.filter(status='in_transit'),
            'history': batches.filter(status='completed')[:10],
            'forming': batches.filter(status='forming'),
            'returns': Campus_Engine_Order.objects.filter(
                assigned_campus_courier=courier, 
                status__in=['pending_cancellation', 'cancelled']
            ),
        }
    
    def get_prefetch_requirements(self):
        """Instructions for Campus Food/Package orders"""
        # Note: 'campus_orders' is the related_name in your DeliveryBatch model
        return [
            Prefetch('campus_orders', queryset=University_Order.objects.select_related(
                'customer', 
                'building', 
                'location_category'
            ).prefetch_related('engine_view'))
        ]
    

    @staticmethod
    def activate_transit(courier_profile):
        """
        Updates all campus engine orders AND their parent 
        University_Orders to 'shipped'.
        """   
        # 1. Fetch the 'Engine' link orders
        campus_engine_orders = Campus_Engine_Order.objects.filter(
            assigned_campus_courier=courier_profile,
            status='assigned' # Only pick orders that haven't moved yet
        ).select_related('raw_order') # Optimization

        for engine_order in campus_engine_orders:
            # A. Update the Engine/Link status
            engine_order.status = 'shipped' 
            engine_order.save()
            
            # B. Update the ACTUAL University Order (The "Raw" Order)
            if engine_order.raw_order:
                engine_order.raw_order.status = 'in_transit'
                engine_order.raw_order.save() # <--- CRITICAL: Must save the raw_order
                
        return True
    
    def get_manifest_context(self, order):
        # Fetch the engine order which contains the bundle logic
        engine_obj = Campus_Engine_Order.objects.filter(raw_order=order).first()
        
        # Debug print to your terminal (remove before launch)
        if engine_obj:
            print(f"DEBUG: Found Engine Order for {order.order_id}")
        else:
            print(f"DEBUG: No Engine Order found for {order.order_id}")

        return {
            "order": order,
            "is_campus": True,
            "data": engine_obj.display_data if engine_obj else {},
            "template": "couriers/snippets/campus_manifest.html"
        }

class NetworkOrderResolver:
    @staticmethod
    def get_order_by_id(order_id):
        """
        Modular resolver: Checks all networks to find the correct order object.
        Returns: (order_object, network_type)
        """
        # 1. Check Standard Network
        standard_order = LUXAOrder.objects.filter(order_id=order_id).select_related('order_source__customer').first()
        if standard_order:
            return standard_order, 'standard'

        # 2. Check Campus Network
        campus_order = University_Order.objects.filter(order_id=order_id).select_related('customer', 'building').first()
        if campus_order:
            return campus_order, 'campus'

        # 3. Add future networks here (e.g., Grocery, Pharmacy)
        
        return None, None