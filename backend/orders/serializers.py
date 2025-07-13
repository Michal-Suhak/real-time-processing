from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal

from .models import Customer, Order, OrderItem, OrderStatus, PickingTask


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ('created_at',)


class OrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_id_display = serializers.CharField(source='item.item_id', read_only=True)
    is_fully_picked = serializers.ReadOnlyField()
    is_fully_packed = serializers.ReadOnlyField()
    
    class Meta:
        model = OrderItem
        fields = '__all__'
        read_only_fields = ('total_price',)
    
    def validate(self, data):
        """Validate order item data"""
        if data.get('picked_quantity', 0) > data.get('quantity', 0):
            raise serializers.ValidationError("Picked quantity cannot exceed ordered quantity")
        
        if data.get('packed_quantity', 0) > data.get('picked_quantity', 0):
            raise serializers.ValidationError("Packed quantity cannot exceed picked quantity")
        
        return data


class OrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    order_items = OrderItemSerializer(many=True, read_only=True)
    is_overdue = serializers.ReadOnlyField()
    total_items = serializers.ReadOnlyField()
    
    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
    
    def validate(self, data):
        """Validate order data"""
        required_date = data.get('required_date')
        if required_date and required_date < timezone.now():
            raise serializers.ValidationError("Required date cannot be in the past")
        
        total_value = data.get('total_value')
        if total_value and total_value <= 0:
            raise serializers.ValidationError("Total value must be positive")
        
        return data


class OrderStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatus
        fields = '__all__'
        read_only_fields = ('timestamp',)


class PickingTaskSerializer(serializers.ModelSerializer):
    order_id_display = serializers.CharField(source='order.order_id', read_only=True)
    item_name = serializers.CharField(source='order_item.item.name', read_only=True)
    item_id_display = serializers.CharField(source='order_item.item.item_id', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True)
    is_completed = serializers.ReadOnlyField()
    
    class Meta:
        model = PickingTask
        fields = '__all__'
        read_only_fields = ('created_at',)
    
    def validate(self, data):
        """Validate picking task data"""
        quantity_to_pick = data.get('quantity_to_pick', 0)
        quantity_picked = data.get('quantity_picked', 0)
        
        if quantity_picked > quantity_to_pick:
            raise serializers.ValidationError("Picked quantity cannot exceed quantity to pick")
        
        return data


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer for creating orders with items
    """
    customer_id = serializers.CharField()
    priority = serializers.ChoiceField(choices=Order.PRIORITY_CHOICES, default='normal')
    required_date = serializers.DateTimeField(required=False)
    currency = serializers.CharField(max_length=3, default='USD')
    notes = serializers.CharField(required=False, allow_blank=True)
    
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        help_text="List of items with item_id, quantity, and unit_price"
    )
    
    def validate_items(self, value):
        """Validate order items"""
        if not value:
            raise serializers.ValidationError("At least one item is required")
        
        for item_data in value:
            if not all(k in item_data for k in ['item_id', 'quantity', 'unit_price']):
                raise serializers.ValidationError("Each item must have item_id, quantity, and unit_price")
            
            if item_data['quantity'] <= 0:
                raise serializers.ValidationError("Item quantity must be positive")
            
            if Decimal(str(item_data['unit_price'])) <= 0:
                raise serializers.ValidationError("Item unit price must be positive")
        
        return value


class OrderStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating order status
    """
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate_status(self, value):
        """Validate status transition"""
        order = self.context.get('order')
        if not order:
            return value
        
        current_status = order.status
        
        # Define valid status transitions
        valid_transitions = {
            'pending': ['confirmed', 'cancelled'],
            'confirmed': ['processing', 'cancelled'],
            'processing': ['picking', 'cancelled'],
            'picking': ['packed', 'cancelled'],
            'packed': ['shipped'],
            'shipped': ['delivered'],
            'delivered': ['returned'],
            'cancelled': [],  # Cannot transition from cancelled
            'returned': []    # Cannot transition from returned
        }
        
        if value not in valid_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f"Cannot transition from {current_status} to {value}"
            )
        
        return value


class PickingTaskAssignSerializer(serializers.Serializer):
    """
    Serializer for assigning picking tasks
    """
    assigned_to = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True)


class PickingTaskUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating picking task progress
    """
    quantity_picked = serializers.IntegerField(min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_quantity_picked(self, value):
        """Validate picked quantity"""
        task = self.context.get('task')
        if task and value > task.quantity_to_pick:
            raise serializers.ValidationError("Picked quantity cannot exceed quantity to pick")
        return value


class OrderFilterSerializer(serializers.Serializer):
    """
    Serializer for order filtering parameters
    """
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES, required=False)
    priority = serializers.ChoiceField(choices=Order.PRIORITY_CHOICES, required=False)
    customer_id = serializers.CharField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    overdue_only = serializers.BooleanField(required=False)


class OrderReportSerializer(serializers.Serializer):
    """
    Serializer for order reports
    """
    total_orders = serializers.IntegerField()
    orders_by_status = serializers.DictField()
    orders_by_priority = serializers.DictField()
    completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_order_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_orders = serializers.IntegerField()
    pending_picking_tasks = serializers.IntegerField()