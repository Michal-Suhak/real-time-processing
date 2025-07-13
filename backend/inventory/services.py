from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from typing import List, Dict, Any

from .models import Item, Location, StockLevel, InventoryMovement


class InventoryService:
    """
    Service class for inventory operations with business logic and validation
    """
    
    @staticmethod
    @transaction.atomic
    def stock_in(item_id: str, location_id: int, quantity: int, 
                 reference_id: str = '', notes: str = '', user: str = '') -> InventoryMovement:
        """
        Stock in operation - adds items to inventory
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive for stock in operations")
        
        item = get_object_or_404(Item, item_id=item_id, is_active=True)
        location = get_object_or_404(Location, id=location_id, is_active=True)
        
        # Get or create stock level
        stock_level, created = StockLevel.objects.get_or_create(
            item=item,
            location=location,
            defaults={'quantity': 0}
        )
        
        previous_quantity = stock_level.quantity
        new_quantity = previous_quantity + quantity
        
        # Update stock level
        stock_level.quantity = new_quantity
        stock_level.save()
        
        # Update location utilization
        location.current_utilization += quantity
        location.save()
        
        # Create movement record
        movement = InventoryMovement.objects.create(
            item=item,
            location=location,
            action='stock_in',
            quantity=quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            reference_id=reference_id,
            notes=notes,
            user=user,
            is_business_hours=InventoryService._is_business_hours(),
            shift=InventoryService._get_current_shift()
        )
        
        return movement
    
    @staticmethod
    @transaction.atomic
    def stock_out(item_id: str, location_id: int, quantity: int,
                  reference_id: str = '', notes: str = '', user: str = '') -> InventoryMovement:
        """
        Stock out operation - removes items from inventory
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive for stock out operations")
        
        item = get_object_or_404(Item, item_id=item_id, is_active=True)
        location = get_object_or_404(Location, id=location_id, is_active=True)
        
        # Get stock level
        try:
            stock_level = StockLevel.objects.get(item=item, location=location)
        except StockLevel.DoesNotExist:
            raise ValueError(f"No stock available for item {item_id} at location {location.code}")
        
        previous_quantity = stock_level.quantity
        new_quantity = previous_quantity - quantity
        
        # Check for negative stock
        if new_quantity < 0:
            raise ValueError(f"Insufficient stock. Available: {previous_quantity}, Requested: {quantity}")
        
        # Update stock level
        stock_level.quantity = new_quantity
        stock_level.save()
        
        # Update location utilization
        location.current_utilization = max(0, location.current_utilization - quantity)
        location.save()
        
        # Create movement record (quantity is negative for stock out)
        movement = InventoryMovement.objects.create(
            item=item,
            location=location,
            action='stock_out',
            quantity=-quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            reference_id=reference_id,
            notes=notes,
            user=user,
            is_business_hours=InventoryService._is_business_hours(),
            shift=InventoryService._get_current_shift()
        )
        
        return movement
    
    @staticmethod
    @transaction.atomic
    def stock_transfer(item_id: str, from_location_id: int, to_location_id: int, quantity: int,
                       reference_id: str = '', notes: str = '', user: str = '') -> List[InventoryMovement]:
        """
        Stock transfer operation - moves items between locations
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive for transfer operations")
        
        if from_location_id == to_location_id:
            raise ValueError("Source and destination locations cannot be the same")
        
        item = get_object_or_404(Item, item_id=item_id, is_active=True)
        from_location = get_object_or_404(Location, id=from_location_id, is_active=True)
        to_location = get_object_or_404(Location, id=to_location_id, is_active=True)
        
        # Check capacity at destination
        if to_location.current_utilization + quantity > to_location.capacity:
            raise ValueError(f"Destination location {to_location.code} does not have sufficient capacity")
        
        # Stock out from source location
        stock_out_movement = InventoryService.stock_out(
            item_id=item_id,
            location_id=from_location_id,
            quantity=quantity,
            reference_id=reference_id,
            notes=f"Transfer to {to_location.code}. {notes}",
            user=user
        )
        
        # Stock in to destination location
        stock_in_movement = InventoryService.stock_in(
            item_id=item_id,
            location_id=to_location_id,
            quantity=quantity,
            reference_id=reference_id,
            notes=f"Transfer from {from_location.code}. {notes}",
            user=user
        )
        
        # Update movement actions to indicate transfer
        stock_out_movement.action = 'transfer'
        stock_in_movement.action = 'transfer'
        stock_out_movement.save()
        stock_in_movement.save()
        
        return [stock_out_movement, stock_in_movement]
    
    @staticmethod
    @transaction.atomic
    def stock_adjustment(item_id: str, location_id: int, quantity_change: int,
                         reference_id: str = '', notes: str = '', user: str = '') -> InventoryMovement:
        """
        Stock adjustment operation - corrects inventory levels
        """
        if quantity_change == 0:
            raise ValueError("Quantity change cannot be zero for adjustment operations")
        
        item = get_object_or_404(Item, item_id=item_id, is_active=True)
        location = get_object_or_404(Location, id=location_id, is_active=True)
        
        # Get or create stock level
        stock_level, created = StockLevel.objects.get_or_create(
            item=item,
            location=location,
            defaults={'quantity': 0}
        )
        
        previous_quantity = stock_level.quantity
        new_quantity = previous_quantity + quantity_change
        
        # Prevent negative stock from adjustments
        if new_quantity < 0:
            raise ValueError(f"Adjustment would result in negative stock. Current: {previous_quantity}, Change: {quantity_change}")
        
        # Update stock level
        stock_level.quantity = new_quantity
        stock_level.save()
        
        # Update location utilization
        location.current_utilization = max(0, location.current_utilization + quantity_change)
        location.save()
        
        # Create movement record
        movement = InventoryMovement.objects.create(
            item=item,
            location=location,
            action='adjustment',
            quantity=quantity_change,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            reference_id=reference_id,
            notes=notes,
            user=user,
            is_business_hours=InventoryService._is_business_hours(),
            shift=InventoryService._get_current_shift()
        )
        
        return movement
    
    @staticmethod
    @transaction.atomic
    def bulk_movements(movements_data: List[Dict[str, Any]], user: str = '') -> List[InventoryMovement]:
        """
        Bulk inventory movements operation
        """
        if not movements_data:
            raise ValueError("No movements provided")
        
        if len(movements_data) > 100:
            raise ValueError("Maximum 100 movements allowed per bulk operation")
        
        movements = []
        
        for movement_data in movements_data:
            action = movement_data['action']
            
            if action == 'stock_in':
                movement = InventoryService.stock_in(
                    item_id=movement_data['item_id'],
                    location_id=movement_data['location_id'],
                    quantity=abs(movement_data['quantity']),
                    reference_id=movement_data.get('reference_id', ''),
                    notes=movement_data.get('notes', ''),
                    user=user
                )
                movements.append(movement)
            
            elif action == 'stock_out':
                movement = InventoryService.stock_out(
                    item_id=movement_data['item_id'],
                    location_id=movement_data['location_id'],
                    quantity=abs(movement_data['quantity']),
                    reference_id=movement_data.get('reference_id', ''),
                    notes=movement_data.get('notes', ''),
                    user=user
                )
                movements.append(movement)
            
            elif action == 'transfer':
                transfer_movements = InventoryService.stock_transfer(
                    item_id=movement_data['item_id'],
                    from_location_id=movement_data['location_id'],
                    to_location_id=movement_data['destination_location_id'],
                    quantity=abs(movement_data['quantity']),
                    reference_id=movement_data.get('reference_id', ''),
                    notes=movement_data.get('notes', ''),
                    user=user
                )
                movements.extend(transfer_movements)
            
            elif action == 'adjustment':
                movement = InventoryService.stock_adjustment(
                    item_id=movement_data['item_id'],
                    location_id=movement_data['location_id'],
                    quantity_change=movement_data['quantity'],
                    reference_id=movement_data.get('reference_id', ''),
                    notes=movement_data.get('notes', ''),
                    user=user
                )
                movements.append(movement)
            
            else:
                raise ValueError(f"Invalid action: {action}")
        
        return movements
    
    @staticmethod
    def _is_business_hours() -> bool:
        """
        Check if current time is within business hours (8 AM - 6 PM)
        """
        now = timezone.now()
        return 8 <= now.hour < 18
    
    @staticmethod
    def _get_current_shift() -> str:
        """
        Get current work shift based on time
        """
        now = timezone.now()
        hour = now.hour
        
        if 6 <= hour < 14:
            return 'morning'
        elif 14 <= hour < 22:
            return 'afternoon'
        else:
            return 'night'