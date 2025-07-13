from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from decimal import Decimal
from typing import List, Dict, Any
import uuid

from .models import Customer, Order, OrderItem, OrderStatus, PickingTask
from inventory.models import Item, Location, StockLevel
from inventory.services import InventoryService


class OrderService:
    """
    Service class for order operations with business logic and validation
    """
    
    @staticmethod
    @transaction.atomic
    def create_order(customer_id: str, items_data: List[Dict], priority: str = 'normal',
                     required_date: timezone.datetime = None, currency: str = 'USD',
                     notes: str = '', user: str = '') -> Order:
        """
        Create a new order with items
        """
        # Get customer
        customer = get_object_or_404(Customer, customer_id=customer_id, is_active=True)
        
        # Generate order ID
        order_id = f"ORD-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        # Calculate total value
        total_value = Decimal('0.00')
        validated_items = []
        
        for item_data in items_data:
            item = get_object_or_404(Item, item_id=item_data['item_id'], is_active=True)
            quantity = int(item_data['quantity'])
            unit_price = Decimal(str(item_data['unit_price']))
            total_price = quantity * unit_price
            total_value += total_price
            
            validated_items.append({
                'item': item,
                'quantity': quantity,
                'unit_price': unit_price,
                'total_price': total_price,
                'notes': item_data.get('notes', '')
            })
        
        # Create order
        order = Order.objects.create(
            order_id=order_id,
            customer=customer,
            priority=priority,
            required_date=required_date,
            total_value=total_value,
            currency=currency,
            notes=notes
        )
        
        # Create order items
        for item_data in validated_items:
            OrderItem.objects.create(
                order=order,
                item=item_data['item'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total_price=item_data['total_price'],
                notes=item_data['notes']
            )
        
        # Create initial status record
        OrderStatus.objects.create(
            order=order,
            to_status='pending',
            changed_by=user,
            reason='Order created'
        )
        
        return order
    
    @staticmethod
    @transaction.atomic
    def update_order_status(order_id: str, new_status: str, user: str, reason: str = '') -> OrderStatus:
        """
        Update order status with validation
        """
        order = get_object_or_404(Order, order_id=order_id)
        old_status = order.status
        
        # Validate status transition (handled by serializer, but double-check here)
        valid_transitions = {
            'pending': ['confirmed', 'cancelled'],
            'confirmed': ['processing', 'cancelled'],
            'processing': ['picking', 'cancelled'],
            'picking': ['packed', 'cancelled'],
            'packed': ['shipped'],
            'shipped': ['delivered'],
            'delivered': ['returned'],
            'cancelled': [],
            'returned': []
        }
        
        if new_status not in valid_transitions.get(old_status, []):
            raise ValueError(f"Cannot transition from {old_status} to {new_status}")
        
        # Update order status
        order.status = new_status
        if new_status == 'shipped':
            order.shipped_date = timezone.now()
        order.save()
        
        # Create status history record
        status_record = OrderStatus.objects.create(
            order=order,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            reason=reason
        )
        
        return status_record
    
    @staticmethod
    @transaction.atomic
    def cancel_order(order_id: str, user: str, reason: str = '') -> OrderStatus:
        """
        Cancel an order
        """
        order = get_object_or_404(Order, order_id=order_id)
        
        if order.status in ['shipped', 'delivered', 'cancelled', 'returned']:
            raise ValueError(f"Cannot cancel order with status {order.status}")
        
        return OrderService.update_order_status(order_id, 'cancelled', user, reason)
    
    @staticmethod
    @transaction.atomic
    def create_picking_tasks(order_id: str, user: str = '') -> List[PickingTask]:
        """
        Create picking tasks for an order
        """
        order = get_object_or_404(Order, order_id=order_id)
        
        if order.status != 'processing':
            raise ValueError("Order must be in processing status to create picking tasks")
        
        picking_tasks = []
        
        for order_item in order.order_items.all():
            # Find locations with available stock
            stock_levels = StockLevel.objects.filter(
                item=order_item.item,
                quantity__gt=0
            ).order_by('-quantity')
            
            remaining_quantity = order_item.quantity
            
            for stock_level in stock_levels:
                if remaining_quantity <= 0:
                    break
                
                quantity_to_pick = min(remaining_quantity, stock_level.quantity)
                
                # Generate task ID
                task_id = f"PICK-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                
                picking_task = PickingTask.objects.create(
                    task_id=task_id,
                    order=order,
                    order_item=order_item,
                    location=stock_level.location,
                    quantity_to_pick=quantity_to_pick
                )
                
                picking_tasks.append(picking_task)
                remaining_quantity -= quantity_to_pick
            
            if remaining_quantity > 0:
                raise ValueError(f"Insufficient stock for item {order_item.item.item_id}")
        
        # Update order status to picking
        OrderService.update_order_status(order_id, 'picking', user, 'Picking tasks created')
        
        return picking_tasks
    
    @staticmethod
    @transaction.atomic
    def assign_picking_task(task_id: str, assigned_to: str, user: str, notes: str = '') -> PickingTask:
        """
        Assign a picking task to a worker
        """
        task = get_object_or_404(PickingTask, task_id=task_id)
        
        if task.status != 'pending':
            raise ValueError(f"Cannot assign task with status {task.status}")
        
        task.status = 'assigned'
        task.assigned_to = assigned_to
        task.assigned_at = timezone.now()
        task.notes = notes
        task.save()
        
        return task
    
    @staticmethod
    @transaction.atomic
    def start_picking_task(task_id: str, user: str) -> PickingTask:
        """
        Start a picking task
        """
        task = get_object_or_404(PickingTask, task_id=task_id)
        
        if task.status != 'assigned':
            raise ValueError(f"Cannot start task with status {task.status}")
        
        if task.assigned_to != user:
            raise ValueError("Task is not assigned to this user")
        
        task.status = 'in_progress'
        task.started_at = timezone.now()
        task.save()
        
        return task
    
    @staticmethod
    @transaction.atomic
    def complete_picking_task(task_id: str, quantity_picked: int, user: str, notes: str = '') -> PickingTask:
        """
        Complete a picking task and update inventory
        """
        task = get_object_or_404(PickingTask, task_id=task_id)
        
        if task.status != 'in_progress':
            raise ValueError(f"Cannot complete task with status {task.status}")
        
        if task.assigned_to != user:
            raise ValueError("Task is not assigned to this user")
        
        if quantity_picked > task.quantity_to_pick:
            raise ValueError("Picked quantity cannot exceed quantity to pick")
        
        # Update task
        task.quantity_picked = quantity_picked
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.notes = notes
        task.save()
        
        # Update order item picked quantity
        task.order_item.picked_quantity += quantity_picked
        task.order_item.save()
        
        # Create inventory movement for stock out
        if quantity_picked > 0:
            InventoryService.stock_out(
                item_id=task.order_item.item.item_id,
                location_id=task.location.id,
                quantity=quantity_picked,
                reference_id=task.order.order_id,
                notes=f"Picked for order {task.order.order_id}",
                user=user
            )
        
        # Check if all picking tasks for the order are completed
        order = task.order
        total_tasks = order.picking_tasks.count()
        completed_tasks = order.picking_tasks.filter(status='completed').count()
        
        if total_tasks == completed_tasks:
            # Check if all items are fully picked
            all_picked = all(
                item.picked_quantity >= item.quantity
                for item in order.order_items.all()
            )
            
            if all_picked:
                OrderService.update_order_status(
                    order.order_id, 'packed', user, 'All items picked'
                )
        
        return task
    
    @staticmethod
    def get_order_statistics(date_from: timezone.datetime = None, 
                           date_to: timezone.datetime = None) -> Dict[str, Any]:
        """
        Get order statistics for reporting
        """
        queryset = Order.objects.all()
        
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        total_orders = queryset.count()
        
        # Orders by status
        orders_by_status = {}
        for status_choice in Order.STATUS_CHOICES:
            status = status_choice[0]
            count = queryset.filter(status=status).count()
            orders_by_status[status] = count
        
        # Orders by priority
        orders_by_priority = {}
        for priority_choice in Order.PRIORITY_CHOICES:
            priority = priority_choice[0]
            count = queryset.filter(priority=priority).count()
            orders_by_priority[priority] = count
        
        # Completion rate
        completed_orders = queryset.filter(status='delivered').count()
        completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        # Average order value
        total_value = queryset.aggregate(
            total=models.Sum('total_value')
        )['total'] or Decimal('0.00')
        average_order_value = (total_value / total_orders) if total_orders > 0 else Decimal('0.00')
        
        # Overdue orders
        overdue_orders = queryset.filter(
            required_date__lt=timezone.now(),
            status__in=['pending', 'confirmed', 'processing', 'picking', 'packed']
        ).count()
        
        # Pending picking tasks
        pending_picking_tasks = PickingTask.objects.filter(
            status__in=['pending', 'assigned', 'in_progress']
        ).count()
        
        return {
            'total_orders': total_orders,
            'orders_by_status': orders_by_status,
            'orders_by_priority': orders_by_priority,
            'completion_rate': Decimal(str(completion_rate)),
            'average_order_value': average_order_value,
            'overdue_orders': overdue_orders,
            'pending_picking_tasks': pending_picking_tasks
        }
    
    @staticmethod
    def check_stock_availability(order_id: str) -> Dict[str, Any]:
        """
        Check stock availability for an order
        """
        order = get_object_or_404(Order, order_id=order_id)
        
        availability = {
            'order_id': order.order_id,
            'items': [],
            'fully_available': True
        }
        
        for order_item in order.order_items.all():
            total_stock = order_item.item.total_stock
            required_quantity = order_item.quantity
            available_quantity = min(total_stock, required_quantity)
            shortage = max(0, required_quantity - total_stock)
            
            item_availability = {
                'item_id': order_item.item.item_id,
                'item_name': order_item.item.name,
                'required_quantity': required_quantity,
                'available_quantity': available_quantity,
                'shortage': shortage,
                'is_available': shortage == 0
            }
            
            availability['items'].append(item_availability)
            
            if shortage > 0:
                availability['fully_available'] = False
        
        return availability