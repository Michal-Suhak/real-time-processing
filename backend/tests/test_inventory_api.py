"""
Inventory API tests
"""
import pytest
from django.urls import reverse
from rest_framework import status

from inventory.models import Supplier, Category, Location, Item, StockLevel, InventoryMovement
from tests.factories import (
    SupplierFactory, CategoryFactory, LocationFactory, ItemFactory,
    StockLevelFactory, InventoryMovementFactory, HighValueItemFactory,
    PerishableItemFactory, LowStockItemFactory
)


@pytest.mark.inventory
@pytest.mark.api
class TestSupplierAPI:
    """Test Supplier API endpoints"""
    
    def test_list_suppliers_admin(self, admin_client):
        """Test admin can list suppliers"""
        SupplierFactory.create_batch(3)
        
        url = reverse('supplier-list')
        response = admin_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
    
    def test_list_suppliers_worker(self, worker_client):
        """Test worker can list suppliers"""
        SupplierFactory.create_batch(2)
        
        url = reverse('supplier-list')
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_create_supplier_admin(self, admin_client):
        """Test admin can create supplier"""
        url = reverse('supplier-list')
        data = {
            'name': 'Test Supplier',
            'contact_info': 'Test contact info',
            'country': 'Test Country'
        }
        
        response = admin_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Supplier.objects.filter(name='Test Supplier').exists()
    
    def test_create_supplier_worker_forbidden(self, worker_client):
        """Test worker cannot create supplier"""
        url = reverse('supplier-list')
        data = {
            'name': 'Test Supplier',
            'country': 'Test Country'
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_update_supplier_admin(self, admin_client):
        """Test admin can update supplier"""
        supplier = SupplierFactory()
        
        url = reverse('supplier-detail', kwargs={'pk': supplier.pk})
        data = {
            'name': 'Updated Supplier',
            'contact_info': supplier.contact_info,
            'country': supplier.country
        }
        
        response = admin_client.put(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        supplier.refresh_from_db()
        assert supplier.name == 'Updated Supplier'
    
    def test_delete_supplier_admin(self, admin_client):
        """Test admin can delete supplier"""
        supplier = SupplierFactory()
        
        url = reverse('supplier-detail', kwargs={'pk': supplier.pk})
        response = admin_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Supplier.objects.filter(pk=supplier.pk).exists()
    
    def test_filter_suppliers_by_country(self, admin_client):
        """Test filtering suppliers by country"""
        SupplierFactory(country='USA')
        SupplierFactory(country='Canada')
        SupplierFactory(country='USA')
        
        url = reverse('supplier-list')
        response = admin_client.get(url, {'country': 'USA'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2


@pytest.mark.inventory
@pytest.mark.api
class TestLocationAPI:
    """Test Location API endpoints"""
    
    def test_list_locations(self, worker_client):
        """Test listing locations"""
        LocationFactory.create_batch(4)
        
        url = reverse('location-list')
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 4
    
    def test_filter_locations_by_zone(self, worker_client):
        """Test filtering locations by zone"""
        LocationFactory(zone='A')
        LocationFactory(zone='B')
        LocationFactory(zone='A')
        
        url = reverse('location-list')
        response = worker_client.get(url, {'zone': 'A'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_filter_locations_by_type(self, worker_client):
        """Test filtering locations by type"""
        LocationFactory(location_type='storage')
        LocationFactory(location_type='picking')
        LocationFactory(location_type='storage')
        
        url = reverse('location-list')
        response = worker_client.get(url, {'type': 'storage'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_location_utilization_endpoint(self, worker_client):
        """Test location utilization endpoint"""
        location = LocationFactory(capacity=1000, current_utilization=250)
        item = ItemFactory()
        StockLevelFactory(location=location, item=item, quantity=100)
        
        url = reverse('location-utilization', kwargs={'pk': location.pk})
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['current_utilization'] == 250
        assert response.data['capacity'] == 1000
        assert response.data['utilization_percentage'] == 25.0
        assert len(response.data['stock_levels']) == 1


@pytest.mark.inventory
@pytest.mark.api
class TestItemAPI:
    """Test Item API endpoints"""
    
    def test_list_items(self, worker_client):
        """Test listing items"""
        ItemFactory.create_batch(3)
        
        url = reverse('item-list')
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
    
    def test_create_item_worker(self, worker_client):
        """Test worker can create item"""
        category = CategoryFactory()
        supplier = SupplierFactory()
        
        url = reverse('item-list')
        data = {
            'item_id': 'TEST-001',
            'name': 'Test Item',
            'category': category.id,
            'supplier': supplier.id,
            'unit_cost': '25.50',
            'weight': '1.500',
            'dimensions': '10x10x10',
            'reorder_point': 20,
            'max_stock_level': 500
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Item.objects.filter(item_id='TEST-001').exists()
    
    def test_filter_items_by_category(self, worker_client):
        """Test filtering items by category"""
        electronics = CategoryFactory(name='Electronics')
        clothing = CategoryFactory(name='Clothing')
        
        ItemFactory(category=electronics)
        ItemFactory(category=clothing)
        ItemFactory(category=electronics)
        
        url = reverse('item-list')
        response = worker_client.get(url, {'category': 'Electronics'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_filter_items_by_perishable(self, worker_client):
        """Test filtering items by perishable flag"""
        ItemFactory(is_perishable=True)
        ItemFactory(is_perishable=False)
        ItemFactory(is_perishable=True)
        
        url = reverse('item-list')
        response = worker_client.get(url, {'is_perishable': 'true'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_item_reorder_check(self, worker_client):
        """Test item reorder check endpoint"""
        item = ItemFactory(reorder_point=50)
        location = LocationFactory()
        StockLevelFactory(item=item, location=location, quantity=30)
        
        url = reverse('item-reorder-check', kwargs={'pk': item.pk})
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['needs_reorder'] is True
        assert response.data['total_stock'] == 30
        assert response.data['reorder_point'] == 50
    
    def test_low_stock_items(self, worker_client):
        """Test low stock items endpoint"""
        # Create items with different stock levels
        low_stock_item = LowStockItemFactory()  # This creates item with stock below reorder point
        normal_item = ItemFactory(reorder_point=10)
        location = LocationFactory()
        StockLevelFactory(item=normal_item, location=location, quantity=50)  # Above reorder point
        
        url = reverse('item-low-stock')
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Should only return the low stock item
        item_ids = [item['item_id'] for item in response.data]
        assert low_stock_item.item_id in item_ids
        assert normal_item.item_id not in item_ids


@pytest.mark.inventory
@pytest.mark.api
class TestStockLevelAPI:
    """Test StockLevel API endpoints"""
    
    def test_list_stock_levels(self, user_client):
        """Test listing stock levels (read-only for all users)"""
        StockLevelFactory.create_batch(3)
        
        url = reverse('stocklevel-list')
        response = user_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
    
    def test_filter_stock_levels_by_item(self, user_client):
        """Test filtering stock levels by item"""
        item1 = ItemFactory(item_id='ITEM-001')
        item2 = ItemFactory(item_id='ITEM-002')
        
        StockLevelFactory(item=item1)
        StockLevelFactory(item=item2)
        StockLevelFactory(item=item1)
        
        url = reverse('stocklevel-list')
        response = user_client.get(url, {'item_id': 'ITEM-001'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_filter_stock_levels_by_zone(self, user_client):
        """Test filtering stock levels by zone"""
        location_a = LocationFactory(zone='A')
        location_b = LocationFactory(zone='B')
        
        StockLevelFactory(location=location_a)
        StockLevelFactory(location=location_b)
        StockLevelFactory(location=location_a)
        
        url = reverse('stocklevel-list')
        response = user_client.get(url, {'zone': 'A'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2


@pytest.mark.inventory
@pytest.mark.api
class TestInventoryMovementAPI:
    """Test InventoryMovement API endpoints"""
    
    def test_list_movements(self, worker_client):
        """Test listing inventory movements"""
        InventoryMovementFactory.create_batch(3)
        
        url = reverse('inventorymovement-list')
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
    
    def test_filter_movements_by_action(self, worker_client):
        """Test filtering movements by action"""
        InventoryMovementFactory(action='stock_in')
        InventoryMovementFactory(action='stock_out')
        InventoryMovementFactory(action='stock_in')
        
        url = reverse('inventorymovement-list')
        response = worker_client.get(url, {'action': 'stock_in'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_high_risk_movements(self, worker_client):
        """Test high risk movements endpoint"""
        # Create high-value item for high risk movement
        high_value_item = HighValueItemFactory()
        location = LocationFactory()
        
        # Create movement with large quantity (high risk)
        InventoryMovementFactory(
            item=high_value_item,
            location=location,
            quantity=150,  # Large quantity
            is_business_hours=False  # After hours
        )
        
        # Create normal movement
        normal_item = ItemFactory()
        InventoryMovementFactory(
            item=normal_item,
            location=location,
            quantity=10,  # Small quantity
            is_business_hours=True
        )
        
        url = reverse('inventorymovement-high-risk')
        response = worker_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Should return at least the high-risk movement
        assert len(response.data) >= 1
    
    def test_delete_movement_admin_only(self, worker_client, admin_client):
        """Test that only admin can delete movements"""
        movement = InventoryMovementFactory()
        
        url = reverse('inventorymovement-detail', kwargs={'pk': movement.pk})
        
        # Worker cannot delete
        response = worker_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Admin can delete
        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.inventory
@pytest.mark.api
class TestStockOperations:
    """Test stock operation endpoints"""
    
    def test_stock_in_operation(self, worker_client):
        """Test stock in operation"""
        item = ItemFactory()
        location = LocationFactory()
        
        url = reverse('inventorymovement-stock-in')
        data = {
            'item_id': item.item_id,
            'location_id': location.id,
            'quantity': 100,
            'reference_id': 'PO-001',
            'notes': 'Purchase order delivery'
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['action'] == 'stock_in'
        assert response.data['quantity'] == 100
        
        # Check that stock level was created/updated
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 100
    
    def test_stock_out_operation(self, worker_client):
        """Test stock out operation"""
        item = ItemFactory()
        location = LocationFactory()
        
        # Create initial stock
        StockLevelFactory(item=item, location=location, quantity=50)
        
        url = reverse('inventorymovement-stock-out')
        data = {
            'item_id': item.item_id,
            'location_id': location.id,
            'quantity': 20,
            'reference_id': 'ORDER-001',
            'notes': 'Customer order fulfillment'
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['action'] == 'stock_out'
        assert response.data['quantity'] == -20  # Negative for stock out
        
        # Check that stock level was updated
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 30  # 50 - 20
    
    def test_stock_out_insufficient_stock(self, worker_client):
        """Test stock out with insufficient stock"""
        item = ItemFactory()
        location = LocationFactory()
        
        # Create insufficient stock
        StockLevelFactory(item=item, location=location, quantity=10)
        
        url = reverse('inventorymovement-stock-out')
        data = {
            'item_id': item.item_id,
            'location_id': location.id,
            'quantity': 20,  # More than available
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Insufficient stock' in response.data['error']
    
    def test_stock_transfer_operation(self, worker_client):
        """Test stock transfer operation"""
        item = ItemFactory()
        from_location = LocationFactory(current_utilization=100)
        to_location = LocationFactory(capacity=1000, current_utilization=0)
        
        # Create initial stock at source location
        StockLevelFactory(item=item, location=from_location, quantity=50)
        
        url = reverse('inventorymovement-transfer')
        data = {
            'item_id': item.item_id,
            'location_id': from_location.id,
            'destination_location_id': to_location.id,
            'quantity': 25,
            'reference_id': 'TRANSFER-001',
            'notes': 'Rebalancing stock'
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2  # Two movements: out and in
        
        # Check stock levels updated correctly
        from_stock = StockLevel.objects.get(item=item, location=from_location)
        to_stock = StockLevel.objects.get(item=item, location=to_location)
        
        assert from_stock.quantity == 25  # 50 - 25
        assert to_stock.quantity == 25    # 0 + 25
    
    def test_stock_adjustment_operation(self, worker_client):
        """Test stock adjustment operation"""
        item = ItemFactory()
        location = LocationFactory()
        
        # Create initial stock
        StockLevelFactory(item=item, location=location, quantity=100)
        
        url = reverse('inventorymovement-adjustment')
        data = {
            'item_id': item.item_id,
            'location_id': location.id,
            'quantity': -5,  # Adjustment downward
            'reference_id': 'CYCLE-COUNT-001',
            'notes': 'Cycle count adjustment'
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['action'] == 'adjustment'
        assert response.data['quantity'] == -5
        
        # Check that stock level was adjusted
        stock_level = StockLevel.objects.get(item=item, location=location)
        assert stock_level.quantity == 95  # 100 - 5
    
    def test_bulk_movements_operation(self, worker_client):
        """Test bulk movements operation"""
        item1 = ItemFactory()
        item2 = ItemFactory()
        location = LocationFactory()
        
        url = reverse('inventorymovement-bulk-movements')
        data = {
            'movements': [
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
        }
        
        response = worker_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2
        
        # Check that both stock levels were created
        stock1 = StockLevel.objects.get(item=item1, location=location)
        stock2 = StockLevel.objects.get(item=item2, location=location)
        
        assert stock1.quantity == 50
        assert stock2.quantity == 30
    
    def test_unauthorized_stock_operations(self, user_client):
        """Test that regular users cannot perform stock operations"""
        item = ItemFactory()
        location = LocationFactory()
        
        urls = [
            reverse('inventorymovement-stock-in'),
            reverse('inventorymovement-stock-out'),
            reverse('inventorymovement-transfer'),
            reverse('inventorymovement-adjustment'),
            reverse('inventorymovement-bulk-movements')
        ]
        
        data = {
            'item_id': item.item_id,
            'location_id': location.id,
            'quantity': 10
        }
        
        for url in urls:
            response = user_client.post(url, data)
            assert response.status_code == status.HTTP_403_FORBIDDEN