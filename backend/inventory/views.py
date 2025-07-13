from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404

from warehouse.permissions import IsAdmin, IsWorker, IsAdminOrReadOnly, IsWorkerOrReadOnly
from .models import Supplier, Category, Location, Item, StockLevel, InventoryMovement
from .serializers import (
    SupplierSerializer, CategorySerializer, LocationSerializer, ItemSerializer,
    StockLevelSerializer, InventoryMovementSerializer, StockMovementSerializer,
    BulkStockMovementSerializer
)
from .services import InventoryService


class SupplierViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing suppliers.
    Admin: Full CRUD access
    Worker: Read-only access
    """
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAdminOrReadOnly]
    
    def get_queryset(self):
        queryset = Supplier.objects.filter(is_active=True)
        country = self.request.query_params.get('country')
        if country:
            queryset = queryset.filter(country__icontains=country)
        return queryset.order_by('name')


class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing product categories.
    Admin: Full CRUD access
    Worker: Read-only access
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class LocationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing warehouse locations.
    Admin: Full CRUD access
    Worker: Read-only access
    """
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsAdminOrReadOnly]
    
    def get_queryset(self):
        queryset = Location.objects.filter(is_active=True)
        zone = self.request.query_params.get('zone')
        location_type = self.request.query_params.get('type')
        
        if zone:
            queryset = queryset.filter(zone=zone)
        if location_type:
            queryset = queryset.filter(location_type=location_type)
            
        return queryset.order_by('zone', 'code')
    
    @action(detail=True, methods=['get'])
    def utilization(self, request, pk=None):
        """Get location utilization details"""
        location = self.get_object()
        stock_levels = StockLevel.objects.filter(location=location)
        
        data = {
            'location': LocationSerializer(location).data,
            'current_utilization': location.current_utilization,
            'capacity': location.capacity,
            'utilization_percentage': location.utilization_percentage,
            'stock_levels': StockLevelSerializer(stock_levels, many=True).data
        }
        
        return Response(data)


class ItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing inventory items.
    Admin & Worker: Full CRUD access
    """
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [IsWorkerOrReadOnly]
    
    def get_queryset(self):
        queryset = Item.objects.filter(is_active=True).select_related('category', 'supplier')
        
        # Filtering
        category = self.request.query_params.get('category')
        supplier = self.request.query_params.get('supplier')
        is_perishable = self.request.query_params.get('is_perishable')
        is_high_value = self.request.query_params.get('is_high_value')
        needs_reorder = self.request.query_params.get('needs_reorder')
        
        if category:
            queryset = queryset.filter(category__name=category)
        if supplier:
            queryset = queryset.filter(supplier__id=supplier)
        if is_perishable is not None:
            queryset = queryset.filter(is_perishable=is_perishable.lower() == 'true')
        if is_high_value is not None:
            queryset = queryset.filter(is_high_value=is_high_value.lower() == 'true')
        
        return queryset.order_by('name')
    
    @action(detail=True, methods=['get'])
    def reorder_check(self, request, pk=None):
        """Check if item needs reordering"""
        item = self.get_object()
        return Response({
            'item_id': item.item_id,
            'name': item.name,
            'total_stock': item.total_stock,
            'reorder_point': item.reorder_point,
            'needs_reorder': item.needs_reorder,
            'stock_levels': StockLevelSerializer(item.stock_levels.all(), many=True).data
        })
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get items with low stock that need reordering"""
        items = []
        for item in self.get_queryset():
            if item.needs_reorder:
                items.append(item)
        
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)


class StockLevelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing stock levels.
    Read-only access for all authenticated users.
    """
    queryset = StockLevel.objects.all()
    serializer_class = StockLevelSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = StockLevel.objects.select_related('item', 'location')
        
        # Filtering
        item_id = self.request.query_params.get('item_id')
        location_id = self.request.query_params.get('location_id')
        zone = self.request.query_params.get('zone')
        
        if item_id:
            queryset = queryset.filter(item__item_id=item_id)
        if location_id:
            queryset = queryset.filter(location__id=location_id)
        if zone:
            queryset = queryset.filter(location__zone=zone)
        
        return queryset.order_by('item__name', 'location__code')


class InventoryMovementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing inventory movements.
    Admin & Worker: Create/Read access
    Admin: Delete access
    """
    queryset = InventoryMovement.objects.all()
    serializer_class = InventoryMovementSerializer
    permission_classes = [IsWorkerOrReadOnly]
    
    def get_queryset(self):
        queryset = InventoryMovement.objects.select_related('item', 'location').order_by('-timestamp')
        
        # Filtering
        item_id = self.request.query_params.get('item_id')
        location_id = self.request.query_params.get('location_id')
        action = self.request.query_params.get('action')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        high_risk_only = self.request.query_params.get('high_risk')
        
        if item_id:
            queryset = queryset.filter(item__item_id=item_id)
        if location_id:
            queryset = queryset.filter(location__id=location_id)
        if action:
            queryset = queryset.filter(action=action)
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)
        
        return queryset
    
    def get_permissions(self):
        """
        Override permissions - only admins can delete movements
        """
        if self.action == 'destroy':
            self.permission_classes = [IsAdmin]
        return super().get_permissions()
    
    @action(detail=False, methods=['get'])
    def high_risk(self, request):
        """Get high-risk movements"""
        movements = []
        for movement in self.get_queryset():
            if movement.is_high_risk:
                movements.append(movement)
        
        serializer = self.get_serializer(movements, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsWorker])
    def stock_in(self, request):
        """Stock in operation"""
        serializer = StockMovementSerializer(data=request.data)
        if serializer.is_valid():
            try:
                movement = InventoryService.stock_in(
                    item_id=serializer.validated_data['item_id'],
                    location_id=serializer.validated_data['location_id'],
                    quantity=abs(serializer.validated_data['quantity']),  # Ensure positive
                    reference_id=serializer.validated_data.get('reference_id', ''),
                    notes=serializer.validated_data.get('notes', ''),
                    user=request.user.username
                )
                return Response(InventoryMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsWorker])
    def stock_out(self, request):
        """Stock out operation"""
        serializer = StockMovementSerializer(data=request.data)
        if serializer.is_valid():
            try:
                movement = InventoryService.stock_out(
                    item_id=serializer.validated_data['item_id'],
                    location_id=serializer.validated_data['location_id'],
                    quantity=abs(serializer.validated_data['quantity']),  # Ensure positive
                    reference_id=serializer.validated_data.get('reference_id', ''),
                    notes=serializer.validated_data.get('notes', ''),
                    user=request.user.username
                )
                return Response(InventoryMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsWorker])
    def transfer(self, request):
        """Stock transfer operation"""
        serializer = StockMovementSerializer(data=request.data)
        if serializer.is_valid():
            try:
                movements = InventoryService.stock_transfer(
                    item_id=serializer.validated_data['item_id'],
                    from_location_id=serializer.validated_data['location_id'],
                    to_location_id=serializer.validated_data['destination_location_id'],
                    quantity=abs(serializer.validated_data['quantity']),
                    reference_id=serializer.validated_data.get('reference_id', ''),
                    notes=serializer.validated_data.get('notes', ''),
                    user=request.user.username
                )
                return Response(InventoryMovementSerializer(movements, many=True).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsWorker])
    def adjustment(self, request):
        """Stock adjustment operation"""
        serializer = StockMovementSerializer(data=request.data)
        if serializer.is_valid():
            try:
                movement = InventoryService.stock_adjustment(
                    item_id=serializer.validated_data['item_id'],
                    location_id=serializer.validated_data['location_id'],
                    quantity_change=serializer.validated_data['quantity'],
                    reference_id=serializer.validated_data.get('reference_id', ''),
                    notes=serializer.validated_data.get('notes', ''),
                    user=request.user.username
                )
                return Response(InventoryMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsWorker])
    def bulk_movements(self, request):
        """Bulk inventory movements"""
        serializer = BulkStockMovementSerializer(data=request.data)
        if serializer.is_valid():
            try:
                movements = InventoryService.bulk_movements(
                    movements_data=serializer.validated_data['movements'],
                    user=request.user.username
                )
                return Response(InventoryMovementSerializer(movements, many=True).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)