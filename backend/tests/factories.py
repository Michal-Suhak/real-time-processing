"""
Factory classes for creating test data
"""
import factory
from django.contrib.auth.models import User, Group
from factory.django import DjangoModelFactory

from inventory.models import Supplier, Category, Location, Item, StockLevel, InventoryMovement


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@warehouse.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True


class AdminUserFactory(UserFactory):
    username = factory.Sequence(lambda n: f"admin{n}")
    is_staff = True
    
    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if not create:
            return
        
        admin_group, _ = Group.objects.get_or_create(name='admin')
        self.groups.add(admin_group)


class WorkerUserFactory(UserFactory):
    username = factory.Sequence(lambda n: f"worker{n}")
    
    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if not create:
            return
        
        worker_group, _ = Group.objects.get_or_create(name='worker')
        self.groups.add(worker_group)


class SupplierFactory(DjangoModelFactory):
    class Meta:
        model = Supplier
    
    name = factory.Faker('company')
    contact_info = factory.Faker('text', max_nb_chars=200)
    country = factory.Faker('country')
    is_active = True


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category
    
    name = factory.Iterator(['Electronics', 'Clothing', 'Food', 'Tools', 'Books', 'Other'])
    description = factory.Faker('text', max_nb_chars=100)


class LocationFactory(DjangoModelFactory):
    class Meta:
        model = Location
    
    code = factory.Sequence(lambda n: f"LOC-{n:03d}")
    zone = factory.Iterator(['A', 'B', 'C', 'D'])
    location_type = factory.Iterator(['storage', 'picking', 'shipping', 'receiving'])
    capacity = factory.Faker('random_int', min=100, max=1000)
    current_utilization = 0
    temperature_controlled = factory.Faker('boolean', chance_of_getting_true=20)
    automated = factory.Faker('boolean', chance_of_getting_true=30)
    is_active = True


class ItemFactory(DjangoModelFactory):
    class Meta:
        model = Item
    
    item_id = factory.Sequence(lambda n: f"ITEM-{n:05d}")
    name = factory.Faker('word')
    category = factory.SubFactory(CategoryFactory)
    supplier = factory.SubFactory(SupplierFactory)
    unit_cost = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    weight = factory.Faker('pydecimal', left_digits=3, right_digits=3, positive=True)
    dimensions = factory.Faker('lexify', text='??x??x??')
    is_perishable = factory.Faker('boolean', chance_of_getting_true=20)
    is_high_value = factory.Faker('boolean', chance_of_getting_true=15)
    reorder_point = factory.Faker('random_int', min=10, max=100)
    max_stock_level = factory.Faker('random_int', min=500, max=2000)
    is_active = True


class StockLevelFactory(DjangoModelFactory):
    class Meta:
        model = StockLevel
    
    item = factory.SubFactory(ItemFactory)
    location = factory.SubFactory(LocationFactory)
    quantity = factory.Faker('random_int', min=0, max=500)


class InventoryMovementFactory(DjangoModelFactory):
    class Meta:
        model = InventoryMovement
    
    item = factory.SubFactory(ItemFactory)
    location = factory.SubFactory(LocationFactory)
    action = factory.Iterator(['stock_in', 'stock_out', 'adjustment', 'transfer'])
    quantity = factory.Faker('random_int', min=-100, max=100)
    previous_quantity = factory.Faker('random_int', min=0, max=200)
    new_quantity = factory.LazyAttribute(lambda obj: obj.previous_quantity + obj.quantity)
    reference_id = factory.Sequence(lambda n: f"REF-{n:06d}")
    notes = factory.Faker('text', max_nb_chars=100)
    user = factory.Faker('user_name')
    is_business_hours = True
    shift = factory.Iterator(['morning', 'afternoon', 'night'])


# Factory for high-value items
class HighValueItemFactory(ItemFactory):
    is_high_value = True
    unit_cost = factory.Faker('pydecimal', left_digits=4, right_digits=2, min_value=1000)


# Factory for perishable items
class PerishableItemFactory(ItemFactory):
    is_perishable = True
    category = factory.SubFactory(CategoryFactory, name='Food')


# Factory for items that need reordering
class LowStockItemFactory(ItemFactory):
    reorder_point = 50
    
    @factory.post_generation
    def create_low_stock(self, create, extracted, **kwargs):
        if not create:
            return
        
        location = LocationFactory()
        StockLevelFactory(item=self, location=location, quantity=20)  # Below reorder point


# Factory for stock movement with specific user
class UserInventoryMovementFactory(InventoryMovementFactory):
    @classmethod
    def _create(cls, model_class, user=None, **kwargs):
        if user:
            kwargs['user'] = user.username
        return super()._create(model_class, **kwargs)