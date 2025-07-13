"""
Inventory service layer tests
"""
import pytest
from decimal import Decimal
from freezegun import freeze_time

from inventory.models import StockLevel, InventoryMovement
from inventory.services import InventoryService
from tests.factories import ItemFactory, LocationFactory, StockLevelFactory


@pytest.mark.inventory
@pytest.mark.unit
class TestInventoryService:
    """Test inventory service business logic"""
    
    def test_stock_in_creates_movement_and_updates_stock(self, db):
        """Test stock in operation creates movement and updates stock level"""
        item = ItemFactory()
        location = LocationFactory(current_utilization=0)
        
        movement = InventoryService.stock_in(
            item_id=item.item_id,
            location_id=location.id,
            quantity=100,
            reference_id='PO-001',
            notes='Purchase order',
            user='testuser'
        )
        
        # Check movement was created
        assert movement.action == 'stock_in'
        assert movement.quantity == 100
        assert movement.previous_quantity == 0
        assert movement.new_quantity == 100
        assert movement.reference_id == 'PO-001'
        assert movement.user == 'testuser'
        
        # Check stock level was created/updated
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 100
        
        # Check location utilization updated
        location.refresh_from_db()
        assert location.current_utilization == 100
    
    def test_stock_in_existing_stock_level(self, db):
        """Test stock in with existing stock level"""
        item = ItemFactory()
        location = LocationFactory()
        
        # Create existing stock
        StockLevelFactory(item=item, location=location, quantity=50)
        
        movement = InventoryService.stock_in(
            item_id=item.item_id,
            location_id=location.id,
            quantity=25,
            user='testuser'
        )
        
        assert movement.previous_quantity == 50
        assert movement.new_quantity == 75
        
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 75
    
    def test_stock_in_negative_quantity_raises_error(self, db):
        """Test stock in with negative quantity raises error"""
        item = ItemFactory()
        location = LocationFactory()
        
        with pytest.raises(ValueError, match="Quantity must be positive"):
            InventoryService.stock_in(
                item_id=item.item_id,
                location_id=location.id,
                quantity=-10,
                user='testuser'
            )
    
    def test_stock_out_removes_stock(self, db):
        """Test stock out operation removes stock"""
        item = ItemFactory()
        location = LocationFactory(current_utilization=100)
        
        # Create initial stock
        StockLevelFactory(item=item, location=location, quantity=50)
        
        movement = InventoryService.stock_out(
            item_id=item.item_id,
            location_id=location.id,
            quantity=20,
            reference_id='ORDER-001',
            user='testuser'
        )
        
        # Check movement
        assert movement.action == 'stock_out'
        assert movement.quantity == -20  # Negative for stock out
        assert movement.previous_quantity == 50
        assert movement.new_quantity == 30
        
        # Check stock level updated
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 30
        
        # Check location utilization updated
        location.refresh_from_db()
        assert location.current_utilization == 80  # 100 - 20
    
    def test_stock_out_insufficient_stock_raises_error(self, db):
        """Test stock out with insufficient stock raises error"""
        item = ItemFactory()
        location = LocationFactory()
        
        # Create insufficient stock
        StockLevelFactory(item=item, location=location, quantity=10)
        
        with pytest.raises(ValueError, match="Insufficient stock"):
            InventoryService.stock_out(
                item_id=item.item_id,
                location_id=location.id,
                quantity=20,
                user='testuser'
            )
    
    def test_stock_out_no_stock_level_raises_error(self, db):
        """Test stock out with no existing stock level raises error"""
        item = ItemFactory()
        location = LocationFactory()
        
        with pytest.raises(ValueError, match="No stock available"):
            InventoryService.stock_out(
                item_id=item.item_id,
                location_id=location.id,
                quantity=10,
                user='testuser'
            )
    
    def test_stock_transfer_moves_between_locations(self, db):
        """Test stock transfer between locations"""
        item = ItemFactory()
        from_location = LocationFactory(current_utilization=100)
        to_location = LocationFactory(capacity=1000, current_utilization=200)
        
        # Create stock at source location
        StockLevelFactory(item=item, location=from_location, quantity=50)
        
        movements = InventoryService.stock_transfer(
            item_id=item.item_id,
            from_location_id=from_location.id,
            to_location_id=to_location.id,
            quantity=30,
            reference_id='TRANSFER-001',
            user='testuser'
        )
        
        # Should return two movements
        assert len(movements) == 2
        
        # Check both movements are marked as transfer
        assert all(m.action == 'transfer' for m in movements)
        
        # Check stock levels
        from_stock = StockLevel.objects.get(item=item, location=from_location)
        to_stock = StockLevel.objects.get(item=item, location=to_location)
        
        assert from_stock.quantity == 20  # 50 - 30
        assert to_stock.quantity == 30    # 0 + 30
        
        # Check location utilizations
        from_location.refresh_from_db()
        to_location.refresh_from_db()
        assert from_location.current_utilization == 70   # 100 - 30
        assert to_location.current_utilization == 230    # 200 + 30
    
    def test_stock_transfer_same_location_raises_error(self, db):
        """Test stock transfer to same location raises error"""
        item = ItemFactory()
        location = LocationFactory()
        
        with pytest.raises(ValueError, match="Source and destination locations cannot be the same"):
            InventoryService.stock_transfer(
                item_id=item.item_id,
                from_location_id=location.id,
                to_location_id=location.id,
                quantity=10,
                user='testuser'
            )
    
    def test_stock_transfer_insufficient_capacity_raises_error(self, db):
        """Test stock transfer with insufficient destination capacity raises error"""
        item = ItemFactory()
        from_location = LocationFactory()
        to_location = LocationFactory(capacity=100, current_utilization=95)
        
        StockLevelFactory(item=item, location=from_location, quantity=50)
        
        with pytest.raises(ValueError, match="does not have sufficient capacity"):
            InventoryService.stock_transfer(
                item_id=item.item_id,
                from_location_id=from_location.id,
                to_location_id=to_location.id,
                quantity=10,  # Would exceed capacity (95 + 10 > 100)
                user='testuser'
            )
    
    def test_stock_adjustment_positive(self, db):
        """Test positive stock adjustment"""
        item = ItemFactory()
        location = LocationFactory(current_utilization=50)
        
        # Create initial stock
        StockLevelFactory(item=item, location=location, quantity=100)
        
        movement = InventoryService.stock_adjustment(
            item_id=item.item_id,
            location_id=location.id,
            quantity_change=5,
            reference_id='CYCLE-COUNT-001',
            notes='Cycle count adjustment',
            user='testuser'
        )
        
        # Check movement
        assert movement.action == 'adjustment'
        assert movement.quantity == 5
        assert movement.previous_quantity == 100
        assert movement.new_quantity == 105
        
        # Check stock level
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 105
        
        # Check location utilization
        location.refresh_from_db()
        assert location.current_utilization == 55  # 50 + 5
    
    def test_stock_adjustment_negative(self, db):
        """Test negative stock adjustment"""
        item = ItemFactory()
        location = LocationFactory(current_utilization=100)
        
        # Create initial stock
        StockLevelFactory(item=item, location=location, quantity=100)
        
        movement = InventoryService.stock_adjustment(
            item_id=item.item_id,
            location_id=location.id,
            quantity_change=-10,
            reference_id='DAMAGE-001',
            notes='Damaged goods write-off',
            user='testuser'
        )
        
        # Check movement
        assert movement.quantity == -10
        assert movement.new_quantity == 90
        
        # Check stock level
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 90
        
        # Check location utilization
        location.refresh_from_db()
        assert location.current_utilization == 90  # 100 - 10
    
    def test_stock_adjustment_zero_quantity_raises_error(self, db):
        """Test stock adjustment with zero quantity raises error"""
        item = ItemFactory()
        location = LocationFactory()
        
        with pytest.raises(ValueError, match="Quantity change cannot be zero"):
            InventoryService.stock_adjustment(
                item_id=item.item_id,
                location_id=location.id,
                quantity_change=0,
                user='testuser'
            )
    
    def test_stock_adjustment_negative_result_raises_error(self, db):
        """Test stock adjustment that would result in negative stock raises error"""
        item = ItemFactory()
        location = LocationFactory()
        
        # Create small stock
        StockLevelFactory(item=item, location=location, quantity=5)
        
        with pytest.raises(ValueError, match="Adjustment would result in negative stock"):
            InventoryService.stock_adjustment(
                item_id=item.item_id,
                location_id=location.id,
                quantity_change=-10,  # Would result in -5
                user='testuser'
            )
    
    def test_bulk_movements_success(self, db):
        """Test successful bulk movements operation"""
        item1 = ItemFactory()
        item2 = ItemFactory()
        location = LocationFactory()
        
        movements_data = [
            {
                'item_id': item1.item_id,
                'location_id': location.id,
                'quantity': 50,
                'action': 'stock_in',
                'reference_id': 'BULK-001'
            },
            {
                'item_id': item2.item_id,
                'location_id': location.id,
                'quantity': 30,
                'action': 'stock_in',
                'reference_id': 'BULK-001'
            }
        ]
        
        movements = InventoryService.bulk_movements(movements_data, user='testuser')
        
        assert len(movements) == 2
        
        # Check stock levels created
        stock1 = StockLevel.objects.get(item=item1, location=location)
        stock2 = StockLevel.objects.get(item=item2, location=location)
        
        assert stock1.quantity == 50
        assert stock2.quantity == 30
    
    def test_bulk_movements_empty_list_raises_error(self, db):
        """Test bulk movements with empty list raises error"""
        with pytest.raises(ValueError, match="No movements provided"):
            InventoryService.bulk_movements([], user='testuser')
    
    def test_bulk_movements_too_many_raises_error(self, db):
        """Test bulk movements with too many items raises error"""
        movements_data = [{'action': 'stock_in'} for _ in range(101)]
        
        with pytest.raises(ValueError, match="Maximum 100 movements allowed"):
            InventoryService.bulk_movements(movements_data, user='testuser')
    
    def test_bulk_movements_with_transfer(self, db):
        """Test bulk movements including transfer operation"""
        item = ItemFactory()
        from_location = LocationFactory(current_utilization=100)
        to_location = LocationFactory(capacity=1000, current_utilization=0)
        
        # Create initial stock
        StockLevelFactory(item=item, location=from_location, quantity=100)
        
        movements_data = [
            {
                'item_id': item.item_id,
                'location_id': from_location.id,
                'destination_location_id': to_location.id,
                'quantity': 25,
                'action': 'transfer',
                'reference_id': 'BULK-TRANSFER-001'
            }
        ]
        
        movements = InventoryService.bulk_movements(movements_data, user='testuser')
        
        # Transfer creates 2 movements
        assert len(movements) == 2
        
        # Check stock levels
        from_stock = StockLevel.objects.get(item=item, location=from_location)
        to_stock = StockLevel.objects.get(item=item, location=to_location)
        
        assert from_stock.quantity == 75  # 100 - 25
        assert to_stock.quantity == 25    # 0 + 25


@pytest.mark.inventory
@pytest.mark.unit
class TestInventoryServiceBusinessLogic:
    """Test business logic in inventory service"""
    
    @freeze_time("2024-01-15 10:30:00")  # Monday morning
    def test_is_business_hours_morning(self):
        """Test business hours detection during morning"""
        assert InventoryService._is_business_hours() is True
    
    @freeze_time("2024-01-15 20:30:00")  # Monday evening
    def test_is_business_hours_evening(self):
        """Test business hours detection during evening"""
        assert InventoryService._is_business_hours() is False
    
    @freeze_time("2024-01-15 09:30:00")  # Monday morning
    def test_get_current_shift_morning(self):
        """Test shift detection during morning"""
        assert InventoryService._get_current_shift() == 'morning'
    
    @freeze_time("2024-01-15 16:30:00")  # Monday afternoon
    def test_get_current_shift_afternoon(self):
        """Test shift detection during afternoon"""
        assert InventoryService._get_current_shift() == 'afternoon'
    
    @freeze_time("2024-01-15 23:30:00")  # Monday night
    def test_get_current_shift_night(self):
        """Test shift detection during night"""
        assert InventoryService._get_current_shift() == 'night'
    
    def test_movement_business_hours_tracking(self, db):
        """Test that movements track business hours correctly"""
        item = ItemFactory()
        location = LocationFactory()
        
        with freeze_time("2024-01-15 15:30:00"):  # Business hours
            movement = InventoryService.stock_in(
                item_id=item.item_id,
                location_id=location.id,
                quantity=50,
                user='testuser'
            )
            
            assert movement.is_business_hours is True
            assert movement.shift == 'afternoon'
        
        with freeze_time("2024-01-15 22:30:00"):  # After hours
            movement = InventoryService.stock_in(
                item_id=item.item_id,
                location_id=location.id,
                quantity=25,
                user='testuser'
            )
            
            assert movement.is_business_hours is False
            assert movement.shift == 'night'
    
    def test_item_not_found_raises_error(self, db):
        """Test that operations with non-existent item raise error"""
        location = LocationFactory()
        
        with pytest.raises(Exception):  # Should raise 404 or similar
            InventoryService.stock_in(
                item_id='NON-EXISTENT',
                location_id=location.id,
                quantity=50,
                user='testuser'
            )
    
    def test_location_not_found_raises_error(self, db):
        """Test that operations with non-existent location raise error"""
        item = ItemFactory()
        
        with pytest.raises(Exception):  # Should raise 404 or similar
            InventoryService.stock_in(
                item_id=item.item_id,
                location_id=99999,  # Non-existent location
                quantity=50,
                user='testuser'
            )
    
    def test_inactive_item_raises_error(self, db):
        """Test that operations with inactive item raise error"""
        item = ItemFactory(is_active=False)
        location = LocationFactory()
        
        with pytest.raises(Exception):  # Should raise 404 or similar
            InventoryService.stock_in(
                item_id=item.item_id,
                location_id=location.id,
                quantity=50,
                user='testuser'
            )
    
    def test_inactive_location_raises_error(self, db):
        """Test that operations with inactive location raise error"""
        item = ItemFactory()
        location = LocationFactory(is_active=False)
        
        with pytest.raises(Exception):  # Should raise 404 or similar
            InventoryService.stock_in(
                item_id=item.item_id,
                location_id=location.id,
                quantity=50,
                user='testuser'
            )