from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models

from .models import Customer, Order, OrderItem, OrderStatus, PickingTask
from .serializers import (
    CustomerSerializer, OrderSerializer, OrderItemSerializer, 
    OrderStatusSerializer, PickingTaskSerializer, OrderCreateSerializer,
    OrderStatusUpdateSerializer, PickingTaskAssignSerializer,
    PickingTaskUpdateSerializer, OrderFilterSerializer, OrderReportSerializer
)
from .services import OrderService
from warehouse.permissions import IsAdmin, IsWorker, IsAdminOrWorker


class CustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customers
    """
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, IsAdminOrWorker]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['country', 'is_active']
    search_fields = ['name', 'customer_id', 'email', 'contact_person']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    lookup_field = 'customer_id'
    
    def get_permissions(self):
        """
        Admin: Full CRUD access
        Worker: Read-only access
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsAdmin]
        else:
            permission_classes = [IsAuthenticated, IsAdminOrWorker]
        
        return [permission() for permission in permission_classes]
    
    @action(detail=True, methods=['get'])
    def orders(self, request, customer_id=None):
        """Get all orders for a customer"""
        customer = self.get_object()
        orders = Order.objects.filter(customer=customer)
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing orders
    """
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsAdminOrWorker]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'customer']
    search_fields = ['order_id', 'customer__name', 'notes']
    ordering_fields = ['created_at', 'required_date', 'total_value']
    ordering = ['-created_at']
    lookup_field = 'order_id'
    
    def get_permissions(self):
        """
        Admin: Full CRUD access
        Worker: Read and update access (status changes)
        """
        if self.action in ['create', 'destroy']:
            permission_classes = [IsAuthenticated, IsAdmin]
        else:
            permission_classes = [IsAuthenticated, IsAdminOrWorker]
        
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter orders based on query parameters"""
        queryset = Order.objects.select_related('customer').prefetch_related('order_items')
        
        # Apply custom filters
        status_filter = self.request.query_params.get('status')
        priority_filter = self.request.query_params.get('priority')
        customer_id_filter = self.request.query_params.get('customer_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        overdue_only = self.request.query_params.get('overdue_only')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)
        
        if customer_id_filter:
            queryset = queryset.filter(customer__customer_id=customer_id_filter)
        
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        if overdue_only == 'true':
            queryset = queryset.filter(
                required_date__lt=timezone.now(),
                status__in=['pending', 'confirmed', 'processing', 'picking', 'packed']
            )
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a new order with items"""
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            order = OrderService.create_order(
                customer_id=serializer.validated_data['customer_id'],
                items_data=serializer.validated_data['items'],
                priority=serializer.validated_data.get('priority', 'normal'),
                required_date=serializer.validated_data.get('required_date'),
                currency=serializer.validated_data.get('currency', 'USD'),
                notes=serializer.validated_data.get('notes', ''),
                user=request.user.username
            )
            
            response_serializer = OrderSerializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, order_id=None):
        """Update order status"""
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(
            data=request.data, 
            context={'order': order}
        )
        serializer.is_valid(raise_exception=True)
        
        try:
            status_record = OrderService.update_order_status(
                order_id=order.order_id,
                new_status=serializer.validated_data['status'],
                user=request.user.username,
                reason=serializer.validated_data.get('reason', '')
            )
            
            response_serializer = OrderStatusSerializer(status_record)
            return Response(response_serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, order_id=None):
        """Cancel an order"""
        order = self.get_object()
        reason = request.data.get('reason', 'Order cancelled by user')
        
        try:
            status_record = OrderService.cancel_order(
                order_id=order.order_id,
                user=request.user.username,
                reason=reason
            )
            
            response_serializer = OrderStatusSerializer(status_record)
            return Response(response_serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def create_picking_tasks(self, request, order_id=None):
        """Create picking tasks for an order"""
        order = self.get_object()
        
        try:
            picking_tasks = OrderService.create_picking_tasks(
                order_id=order.order_id,
                user=request.user.username
            )
            
            serializer = PickingTaskSerializer(picking_tasks, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def status_history(self, request, order_id=None):
        """Get order status history"""
        order = self.get_object()
        status_records = OrderStatus.objects.filter(order=order).order_by('-timestamp')
        serializer = OrderStatusSerializer(status_records, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def check_stock(self, request, order_id=None):
        """Check stock availability for order"""
        order = self.get_object()
        availability = OrderService.check_stock_availability(order.order_id)
        return Response(availability)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get order statistics"""
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        if date_from:
            date_from = timezone.datetime.fromisoformat(date_from)
        if date_to:
            date_to = timezone.datetime.fromisoformat(date_to)
        
        stats = OrderService.get_order_statistics(date_from, date_to)
        serializer = OrderReportSerializer(stats)
        return Response(serializer.data)


class OrderItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing order items
    """
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated, IsAdminOrWorker]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['order', 'item']
    ordering_fields = ['created_at', 'quantity', 'total_price']
    ordering = ['created_at']
    
    def get_permissions(self):
        """
        Admin: Full CRUD access
        Worker: Read-only access
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsAdmin]
        else:
            permission_classes = [IsAuthenticated, IsAdminOrWorker]
        
        return [permission() for permission in permission_classes]


class PickingTaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing picking tasks
    """
    queryset = PickingTask.objects.all()
    serializer_class = PickingTaskSerializer
    permission_classes = [IsAuthenticated, IsAdminOrWorker]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'assigned_to', 'order', 'location']
    search_fields = ['task_id', 'order__order_id', 'order_item__item__name']
    ordering_fields = ['created_at', 'assigned_at', 'completed_at']
    ordering = ['created_at']
    lookup_field = 'task_id'
    
    def get_queryset(self):
        """Filter tasks based on user role and assignment"""
        queryset = PickingTask.objects.select_related(
            'order', 'order_item', 'order_item__item', 'location'
        )
        
        # Workers can only see their own assigned tasks or unassigned tasks
        if hasattr(self.request.user, 'groups') and self.request.user.groups.filter(name='worker').exists():
            queryset = queryset.filter(
                models.Q(assigned_to=self.request.user.username) | 
                models.Q(assigned_to__isnull=True)
            )
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def assign(self, request, task_id=None):
        """Assign a picking task to a worker"""
        task = self.get_object()
        serializer = PickingTaskAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            updated_task = OrderService.assign_picking_task(
                task_id=task.task_id,
                assigned_to=serializer.validated_data['assigned_to'],
                user=request.user.username,
                notes=serializer.validated_data.get('notes', '')
            )
            
            response_serializer = PickingTaskSerializer(updated_task)
            return Response(response_serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def start(self, request, task_id=None):
        """Start a picking task"""
        task = self.get_object()
        
        try:
            updated_task = OrderService.start_picking_task(
                task_id=task.task_id,
                user=request.user.username
            )
            
            response_serializer = PickingTaskSerializer(updated_task)
            return Response(response_serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, task_id=None):
        """Complete a picking task"""
        task = self.get_object()
        serializer = PickingTaskUpdateSerializer(
            data=request.data,
            context={'task': task}
        )
        serializer.is_valid(raise_exception=True)
        
        try:
            updated_task = OrderService.complete_picking_task(
                task_id=task.task_id,
                quantity_picked=serializer.validated_data['quantity_picked'],
                user=request.user.username,
                notes=serializer.validated_data.get('notes', '')
            )
            
            response_serializer = PickingTaskSerializer(updated_task)
            return Response(response_serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def my_tasks(self, request):
        """Get tasks assigned to current user"""
        tasks = PickingTask.objects.filter(
            assigned_to=request.user.username,
            status__in=['assigned', 'in_progress']
        ).select_related('order', 'order_item', 'order_item__item', 'location')
        
        serializer = PickingTaskSerializer(tasks, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending (unassigned) picking tasks"""
        tasks = PickingTask.objects.filter(
            status='pending'
        ).select_related('order', 'order_item', 'order_item__item', 'location')
        
        serializer = PickingTaskSerializer(tasks, many=True)
        return Response(serializer.data)


class OrderStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing order status history
    """
    queryset = OrderStatus.objects.all()
    serializer_class = OrderStatusSerializer
    permission_classes = [IsAuthenticated, IsAdminOrWorker]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['order', 'from_status', 'to_status']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']
