from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_info = models.TextField(blank=True)
    country = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'suppliers'

    def __str__(self):
        return self.name


class Category(models.Model):
    CATEGORY_CHOICES = [
        ('Electronics', 'Electronics'),
        ('Clothing', 'Clothing'),
        ('Food', 'Food'),
        ('Tools', 'Tools'),
        ('Books', 'Books'),
        ('Other', 'Other'),
    ]
    
    name = models.CharField(max_length=50, choices=CATEGORY_CHOICES, unique=True)
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Location(models.Model):
    ZONE_CHOICES = [
        ('A', 'Zone A'),
        ('B', 'Zone B'),
        ('C', 'Zone C'),
        ('D', 'Zone D'),
    ]
    
    LOCATION_TYPE_CHOICES = [
        ('storage', 'Storage'),
        ('picking', 'Picking'),
        ('shipping', 'Shipping'),
        ('receiving', 'Receiving'),
    ]
    
    code = models.CharField(max_length=20, unique=True)
    zone = models.CharField(max_length=1, choices=ZONE_CHOICES)
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE_CHOICES)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    current_utilization = models.PositiveIntegerField(default=0)
    temperature_controlled = models.BooleanField(default=False)
    automated = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'locations'

    def __str__(self):
        return f"{self.code} ({self.zone})"

    @property
    def utilization_percentage(self):
        if self.capacity == 0:
            return 0
        return (self.current_utilization / self.capacity) * 100


class Item(models.Model):
    item_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    weight = models.DecimalField(max_digits=8, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    dimensions = models.CharField(max_length=100, help_text="LxWxH in cm")
    is_perishable = models.BooleanField(default=False)
    is_high_value = models.BooleanField(default=False)
    reorder_point = models.PositiveIntegerField(default=0)
    max_stock_level = models.PositiveIntegerField(default=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'items'

    def __str__(self):
        return f"{self.item_id} - {self.name}"

    @property
    def total_stock(self):
        return self.stock_levels.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

    @property
    def needs_reorder(self):
        return self.total_stock <= self.reorder_point


class StockLevel(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='stock_levels')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='stock_levels')
    quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_levels'
        unique_together = ['item', 'location']

    def __str__(self):
        return f"{self.item.item_id} @ {self.location.code}: {self.quantity}"


class InventoryMovement(models.Model):
    ACTION_CHOICES = [
        ('stock_in', 'Stock In'),
        ('stock_out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer'),
    ]
    
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='movements')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='movements')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity = models.IntegerField()
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reference_id = models.CharField(max_length=100, blank=True, help_text="Order ID, Transfer ID, etc.")
    notes = models.TextField(blank=True)
    user = models.CharField(max_length=100, blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_business_hours = models.BooleanField(default=True)
    shift = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = 'inventory_movements'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} - {self.item.item_id} @ {self.location.code}: {self.quantity}"

    @property
    def is_high_risk(self):
        risk_score = 0
        
        if self.item.is_high_value:
            risk_score += 3
        if abs(self.quantity) >= 100:
            risk_score += 2
        if not self.is_business_hours:
            risk_score += 1
        if self.item.is_perishable:
            risk_score += 1
            
        return risk_score >= 4
