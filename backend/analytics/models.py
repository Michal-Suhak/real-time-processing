from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored'),
    ]
    
    TYPE_CHOICES = [
        ('inventory', 'Inventory'),
        ('anomaly', 'Anomaly'),
        ('security', 'Security'),
        ('performance', 'Performance'),
        ('data_quality', 'Data Quality'),
    ]
    
    alert_id = models.CharField(max_length=50, unique=True)
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    title = models.CharField(max_length=255)
    description = models.TextField()
    source = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, blank=True)
    entity_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=100, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.alert_id} - {self.title} [{self.severity}]"


class AnomalyDetection(models.Model):
    ANOMALY_TYPE_CHOICES = [
        ('volume', 'Volume-based'),
        ('time', 'Time-based'),
        ('location', 'Location-based'),
        ('pattern', 'Pattern-based'),
        ('threshold', 'Threshold-based'),
    ]
    
    detection_id = models.CharField(max_length=50, unique=True)
    anomaly_type = models.CharField(max_length=20, choices=ANOMALY_TYPE_CHOICES)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)
    anomaly_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))]
    )
    threshold = models.DecimalField(max_digits=5, decimal_places=2)
    details = models.JSONField(default=dict)
    is_confirmed = models.BooleanField(default=False)
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'anomaly_detections'
        ordering = ['-detected_at']

    def __str__(self):
        return f"Anomaly {self.detection_id} - Score: {self.anomaly_score}"

    @property
    def risk_level(self):
        if self.anomaly_score >= 80:
            return 'critical'
        elif self.anomaly_score >= 60:
            return 'high'
        elif self.anomaly_score >= 40:
            return 'medium'
        else:
            return 'low'


class Metric(models.Model):
    METRIC_TYPE_CHOICES = [
        ('operational', 'Operational'),
        ('business', 'Business'),
        ('quality', 'Quality'),
        ('performance', 'Performance'),
    ]
    
    metric_name = models.CharField(max_length=100)
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPE_CHOICES)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    unit = models.CharField(max_length=50, blank=True)
    dimensions = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'metrics'
        indexes = [
            models.Index(fields=['metric_name', 'timestamp']),
            models.Index(fields=['metric_type', 'timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.metric_name}: {self.value} {self.unit}"


class PerformanceReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    
    report_id = models.CharField(max_length=50, unique=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Inventory metrics
    total_transactions = models.PositiveIntegerField(default=0)
    stock_in_count = models.PositiveIntegerField(default=0)
    stock_out_count = models.PositiveIntegerField(default=0)
    adjustment_count = models.PositiveIntegerField(default=0)
    transfer_count = models.PositiveIntegerField(default=0)
    
    # Order metrics
    orders_created = models.PositiveIntegerField(default=0)
    orders_completed = models.PositiveIntegerField(default=0)
    orders_cancelled = models.PositiveIntegerField(default=0)
    average_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Shipment metrics
    shipments_created = models.PositiveIntegerField(default=0)
    shipments_delivered = models.PositiveIntegerField(default=0)
    average_delivery_days = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    
    # Performance metrics
    success_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))]
    )
    error_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))]
    )
    
    # Anomaly metrics
    anomalies_detected = models.PositiveIntegerField(default=0)
    critical_anomalies = models.PositiveIntegerField(default=0)
    
    additional_metrics = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.CharField(max_length=100, default='system')

    class Meta:
        db_table = 'performance_reports'
        unique_together = ['report_type', 'period_start', 'period_end']
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.report_type.title()} Report {self.report_id}"

    @property
    def order_completion_rate(self):
        if self.orders_created == 0:
            return Decimal('0.00')
        return (Decimal(self.orders_completed) / Decimal(self.orders_created)) * 100

    @property
    def shipment_success_rate(self):
        if self.shipments_created == 0:
            return Decimal('0.00')
        return (Decimal(self.shipments_delivered) / Decimal(self.shipments_created)) * 100


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    log_id = models.CharField(max_length=50, unique=True)
    user = models.CharField(max_length=100)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100, blank=True)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['entity_type', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} {self.entity_type} ({self.timestamp})"
