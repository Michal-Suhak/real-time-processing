from rest_framework import serializers
from .models import Supplier, Category, Location, Item, StockLevel, InventoryMovement


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class LocationSerializer(serializers.ModelSerializer):
    utilization_percentage = serializers.ReadOnlyField()
    
    class Meta:
        model = Location
        fields = '__all__'


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    total_stock = serializers.ReadOnlyField()
    needs_reorder = serializers.ReadOnlyField()
    
    class Meta:
        model = Item
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class StockLevelSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_id_display = serializers.CharField(source='item.item_id', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True)
    
    class Meta:
        model = StockLevel
        fields = '__all__'
        read_only_fields = ('last_updated',)


class InventoryMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_id_display = serializers.CharField(source='item.item_id', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True)
    is_high_risk = serializers.ReadOnlyField()
    
    class Meta:
        model = InventoryMovement
        fields = '__all__'
        read_only_fields = ('timestamp',)


class StockMovementSerializer(serializers.Serializer):
    """
    Serializer for stock movement operations (stock in/out/transfer/adjustment)
    """
    item_id = serializers.CharField()
    location_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    action = serializers.ChoiceField(choices=InventoryMovement.ACTION_CHOICES)
    reference_id = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    user = serializers.CharField(required=False, allow_blank=True)
    
    # For transfer operations
    destination_location_id = serializers.IntegerField(required=False)
    
    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity cannot be zero")
        return value
    
    def validate(self, data):
        action = data.get('action')
        
        # For stock_out, quantity should be negative
        if action == 'stock_out' and data.get('quantity', 0) > 0:
            data['quantity'] = -data['quantity']
        
        # For transfer, destination location is required
        if action == 'transfer' and not data.get('destination_location_id'):
            raise serializers.ValidationError("Destination location is required for transfer operations")
        
        return data


class BulkStockMovementSerializer(serializers.Serializer):
    """
    Serializer for bulk stock movement operations
    """
    movements = StockMovementSerializer(many=True)
    
    def validate_movements(self, value):
        if not value:
            raise serializers.ValidationError("At least one movement is required")
        if len(value) > 100:
            raise serializers.ValidationError("Maximum 100 movements allowed per bulk operation")
        return value