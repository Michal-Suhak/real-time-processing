from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Carrier(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=10, unique=True)
    api_endpoint = models.URLField(blank=True)
    tracking_url_template = models.CharField(max_length=500, blank=True, help_text="Use {tracking_number} placeholder")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'carriers'

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_tracking_url(self, tracking_number):
        if self.tracking_url_template and tracking_number:
            return self.tracking_url_template.format(tracking_number=tracking_number)
        return None


class Shipment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('failed_delivery', 'Failed Delivery'),
        ('returned', 'Returned'),
        ('lost', 'Lost'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('standard', 'Standard'),
        ('expedited', 'Expedited'),
        ('next_day', 'Next Day'),
        ('same_day', 'Same Day'),
    ]
    
    shipment_id = models.CharField(max_length=50, unique=True)
    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='shipments')
    carrier = models.ForeignKey(Carrier, on_delete=models.PROTECT)
    tracking_number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=15, choices=PRIORITY_CHOICES, default='standard')
    
    # Shipping details
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    weight = models.DecimalField(max_digits=8, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    dimensions = models.CharField(max_length=100, help_text="LxWxH in cm")
    
    # Addresses
    origin_address = models.TextField()
    destination_address = models.TextField()
    destination_country = models.CharField(max_length=100)
    destination_postal_code = models.CharField(max_length=20)
    
    # Dates
    shipped_date = models.DateTimeField(null=True, blank=True)
    estimated_delivery_date = models.DateTimeField(null=True, blank=True)
    actual_delivery_date = models.DateTimeField(null=True, blank=True)
    
    # Additional info
    signature_required = models.BooleanField(default=False)
    insurance_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    special_instructions = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shipments'
        ordering = ['-created_at']

    def __str__(self):
        return f"Shipment {self.shipment_id} - {self.tracking_number}"

    @property
    def is_delivered(self):
        return self.status == 'delivered'

    @property
    def is_in_transit(self):
        return self.status in ['picked_up', 'in_transit', 'out_for_delivery']

    @property
    def delivery_performance_days(self):
        if self.shipped_date and self.actual_delivery_date:
            return (self.actual_delivery_date - self.shipped_date).days
        return None

    @property
    def tracking_url(self):
        return self.carrier.get_tracking_url(self.tracking_number)


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='shipment_items')
    order_item = models.ForeignKey('orders.OrderItem', on_delete=models.PROTECT)
    quantity_shipped = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    class Meta:
        db_table = 'shipment_items'
        unique_together = ['shipment', 'order_item']

    def __str__(self):
        return f"{self.shipment.shipment_id} - {self.order_item.item.name} x{self.quantity_shipped}"


class ShipmentStatus(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=50, default='manual', help_text="manual, api, webhook")

    class Meta:
        db_table = 'shipment_status_history'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.shipment.tracking_number}: {self.from_status} → {self.to_status}"


class DeliveryAttempt(models.Model):
    OUTCOME_CHOICES = [
        ('successful', 'Successful'),
        ('failed_no_one_home', 'Failed - No One Home'),
        ('failed_refused', 'Failed - Refused'),
        ('failed_address_issue', 'Failed - Address Issue'),
        ('failed_other', 'Failed - Other'),
    ]
    
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='delivery_attempts')
    attempt_number = models.PositiveIntegerField()
    attempt_date = models.DateTimeField()
    outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES)
    notes = models.TextField(blank=True)
    signature = models.CharField(max_length=255, blank=True)
    photo_proof_url = models.URLField(blank=True)
    
    class Meta:
        db_table = 'delivery_attempts'
        unique_together = ['shipment', 'attempt_number']
        ordering = ['attempt_number']

    def __str__(self):
        return f"{self.shipment.tracking_number} - Attempt {self.attempt_number}: {self.outcome}"
