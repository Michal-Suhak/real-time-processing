import asyncio
import json
import smtplib
from datetime import datetime, timezone
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from typing import Dict, List, Any, Optional, Callable
import structlog
import httpx
from enum import Enum

logger = structlog.get_logger(__name__)

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"  
    ERROR = "error"
    CRITICAL = "critical"

class AlertStatus(Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"

class Alert:
    def __init__(self, 
                 alert_id: str,
                 title: str,
                 description: str,
                 severity: AlertSeverity,
                 source: str,
                 timestamp: Optional[datetime] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.alert_id = alert_id
        self.title = title
        self.description = description
        self.severity = severity
        self.source = source
        self.timestamp = timestamp or datetime.now(tz=timezone.utc)
        self.metadata = metadata or {}
        self.status = AlertStatus.ACTIVE
        self.acknowledged_by = None
        self.acknowledged_at = None
        self.resolved_at = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_id': self.alert_id,
            'title': self.title,
            'description': self.description,
            'severity': self.severity.value,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
            'status': self.status.value,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }
        
    def acknowledge(self, user: str) -> None:
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = datetime.now(tz=timezone.utc)
        
    def resolve(self) -> None:
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now(tz=timezone.utc)

class NotificationChannel:
    """Base class for notification channels"""
    
    async def send(self, alert: Alert) -> bool:
        raise NotImplementedError

class EmailNotificationChannel(NotificationChannel):
    def __init__(self, smtp_config: Dict[str, Any]):
        self.smtp_host = smtp_config.get('host', 'localhost')
        self.smtp_port = smtp_config.get('port', 587)
        self.username = smtp_config.get('username')
        self.password = smtp_config.get('password')
        self.from_email = smtp_config.get('from_email')
        self.to_emails = smtp_config.get('to_emails', [])
        self.use_tls = smtp_config.get('use_tls', True)
        
    async def send(self, alert: Alert) -> bool:
        try:
            # Create message
            msg = MimeMultipart()
            msg['From'] = self.from_email
            msg['To'] = ', '.join(self.to_emails)
            msg['Subject'] = f"[{alert.severity.value.upper()}] Warehouse Alert: {alert.title}"
            
            # Create HTML body
            html_body = self._create_html_body(alert)
            msg.attach(MimeText(html_body, 'html'))
            
            # Send email
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
                
            server.send_message(msg)
            server.quit()
            
            logger.info("Email alert sent", alert_id=alert.alert_id, to_emails=self.to_emails)
            return True
            
        except Exception as e:
            logger.error("Failed to send email alert", error=str(e), alert_id=alert.alert_id)
            return False
            
    def _create_html_body(self, alert: Alert) -> str:
        severity_color = {
            AlertSeverity.INFO: "#17a2b8",
            AlertSeverity.WARNING: "#ffc107", 
            AlertSeverity.ERROR: "#dc3545",
            AlertSeverity.CRITICAL: "#721c24"
        }
        
        color = severity_color.get(alert.severity, "#6c757d")
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <div style="border-left: 4px solid {color}; padding-left: 20px;">
                <h2 style="color: {color}; margin-top: 0;">
                    🚨 Warehouse Alert: {alert.title}
                </h2>
                <p><strong>Severity:</strong> <span style="color: {color};">{alert.severity.value.upper()}</span></p>
                <p><strong>Source:</strong> {alert.source}</p>
                <p><strong>Time:</strong> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                <p><strong>Description:</strong></p>
                <p style="background-color: #f8f9fa; padding: 10px; border-radius: 4px;">
                    {alert.description}
                </p>
                
                {self._format_metadata(alert.metadata)}
                
                <hr style="margin: 20px 0;">
                <p style="font-size: 12px; color: #6c757d;">
                    Alert ID: {alert.alert_id}<br>
                    Generated by Warehouse Real-Time Processing System
                </p>
            </div>
        </body>
        </html>
        """
        
    def _format_metadata(self, metadata: Dict[str, Any]) -> str:
        if not metadata:
            return ""
            
        html = "<p><strong>Additional Information:</strong></p><ul>"
        for key, value in metadata.items():
            html += f"<li><strong>{key}:</strong> {value}</li>"
        html += "</ul>"
        return html

class SlackNotificationChannel(NotificationChannel):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        
    async def send(self, alert: Alert) -> bool:
        try:
            # Create Slack message
            message = self._create_slack_message(alert)
            
            # Send to Slack
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=message,
                    timeout=10
                )
                response.raise_for_status()
                
            logger.info("Slack alert sent", alert_id=alert.alert_id)
            return True
            
        except Exception as e:
            logger.error("Failed to send Slack alert", error=str(e), alert_id=alert.alert_id)
            return False
            
    def _create_slack_message(self, alert: Alert) -> Dict[str, Any]:
        severity_emojis = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌", 
            AlertSeverity.CRITICAL: "🚨"
        }
        
        severity_colors = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ff9500",
            AlertSeverity.ERROR: "#ff0000",
            AlertSeverity.CRITICAL: "#8B0000"
        }
        
        emoji = severity_emojis.get(alert.severity, "📢")
        color = severity_colors.get(alert.severity, "#808080")
        
        fields = [
            {
                "title": "Severity",
                "value": alert.severity.value.upper(),
                "short": True
            },
            {
                "title": "Source", 
                "value": alert.source,
                "short": True
            },
            {
                "title": "Time",
                "value": alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
                "short": True
            },
            {
                "title": "Alert ID",
                "value": alert.alert_id,
                "short": True
            }
        ]
        
        # Add metadata fields
        for key, value in alert.metadata.items():
            fields.append({
                "title": key.replace('_', ' ').title(),
                "value": str(value),
                "short": True
            })
        
        return {
            "text": f"{emoji} Warehouse Alert: {alert.title}",
            "attachments": [
                {
                    "color": color,
                    "title": alert.title,
                    "text": alert.description,
                    "fields": fields,
                    "footer": "Warehouse Processing System",
                    "ts": int(alert.timestamp.timestamp())
                }
            ]
        }

class WebhookNotificationChannel(NotificationChannel):
    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None):
        self.webhook_url = webhook_url
        self.headers = headers or {'Content-Type': 'application/json'}
        
    async def send(self, alert: Alert) -> bool:
        try:
            payload = {
                'event': 'alert',
                'alert': alert.to_dict(),
                'timestamp': datetime.now(tz=timezone.utc).isoformat()
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=10
                )
                response.raise_for_status()
                
            logger.info("Webhook alert sent", alert_id=alert.alert_id, url=self.webhook_url)
            return True
            
        except Exception as e:
            logger.error("Failed to send webhook alert", error=str(e), alert_id=alert.alert_id)
            return False

class AlertManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.active_alerts: Dict[str, Alert] = {}
        self.notification_channels: List[NotificationChannel] = []
        self.alert_rules: List[Dict[str, Any]] = []
        self.logger = logger.bind(component="alert_manager")
        
        # Initialize notification channels
        self._setup_notification_channels()
        
        # Load alert rules
        self._load_alert_rules()
        
    def _setup_notification_channels(self):
        """Setup notification channels from config"""
        channels_config = self.config.get('notification_channels', {})
        
        # Email channel
        if 'email' in channels_config:
            email_channel = EmailNotificationChannel(channels_config['email'])
            self.notification_channels.append(email_channel)
            
        # Slack channel
        if 'slack' in channels_config:
            slack_channel = SlackNotificationChannel(channels_config['slack']['webhook_url'])
            self.notification_channels.append(slack_channel)
            
        # Webhook channels
        if 'webhooks' in channels_config:
            for webhook_config in channels_config['webhooks']:
                webhook_channel = WebhookNotificationChannel(
                    webhook_config['url'],
                    webhook_config.get('headers')
                )
                self.notification_channels.append(webhook_channel)
                
    def _load_alert_rules(self):
        """Load alert rules from config"""
        self.alert_rules = self.config.get('alert_rules', [])
        
    async def create_alert(self, 
                          alert_id: str,
                          title: str,
                          description: str,
                          severity: AlertSeverity,
                          source: str,
                          metadata: Optional[Dict[str, Any]] = None) -> Alert:
        """Create and process a new alert"""
        
        # Check if alert already exists and is active
        if alert_id in self.active_alerts:
            existing_alert = self.active_alerts[alert_id]
            if existing_alert.status == AlertStatus.ACTIVE:
                self.logger.info("Alert already active, skipping", alert_id=alert_id)
                return existing_alert
                
        # Create new alert
        alert = Alert(alert_id, title, description, severity, source, metadata=metadata)
        self.active_alerts[alert_id] = alert
        
        self.logger.info("Alert created", 
                        alert_id=alert_id, 
                        severity=severity.value,
                        source=source)
        
        # Send notifications
        await self._send_notifications(alert)
        
        return alert
        
    async def _send_notifications(self, alert: Alert):
        """Send alert notifications to all configured channels"""
        
        # Check if alert severity meets notification threshold
        min_severity = AlertSeverity(self.config.get('min_notification_severity', 'warning'))
        severity_levels = {
            AlertSeverity.INFO: 0,
            AlertSeverity.WARNING: 1, 
            AlertSeverity.ERROR: 2,
            AlertSeverity.CRITICAL: 3
        }
        
        if severity_levels.get(alert.severity, 0) < severity_levels.get(min_severity, 1):
            self.logger.debug("Alert severity below notification threshold", 
                            alert_id=alert.alert_id,
                            severity=alert.severity.value)
            return
            
        # Send to all channels
        tasks = []
        for channel in self.notification_channels:
            task = asyncio.create_task(channel.send(alert))
            tasks.append(task)
            
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for result in results if result is True)
            
            self.logger.info("Notifications sent", 
                           alert_id=alert.alert_id,
                           successful=success_count,
                           total=len(tasks))
            
    async def acknowledge_alert(self, alert_id: str, user: str) -> bool:
        """Acknowledge an alert"""
        if alert_id not in self.active_alerts:
            self.logger.warning("Alert not found for acknowledgment", alert_id=alert_id)
            return False
            
        alert = self.active_alerts[alert_id]
        alert.acknowledge(user)
        
        self.logger.info("Alert acknowledged", alert_id=alert_id, user=user)
        return True
        
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert"""
        if alert_id not in self.active_alerts:
            self.logger.warning("Alert not found for resolution", alert_id=alert_id)
            return False
            
        alert = self.active_alerts[alert_id]
        alert.resolve()
        
        # Remove from active alerts
        del self.active_alerts[alert_id]
        
        self.logger.info("Alert resolved", alert_id=alert_id)
        return True
        
    def get_active_alerts(self, 
                         severity_filter: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get list of active alerts, optionally filtered by severity"""
        alerts = list(self.active_alerts.values())
        
        if severity_filter:
            alerts = [alert for alert in alerts if alert.severity == severity_filter]
            
        # Sort by severity (critical first) then by timestamp
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.ERROR: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3
        }
        
        alerts.sort(key=lambda a: (severity_order.get(a.severity, 4), a.timestamp))
        return alerts
        
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get specific alert by ID"""
        return self.active_alerts.get(alert_id)
        
    async def evaluate_rules(self, data: Dict[str, Any]) -> List[Alert]:
        """Evaluate alert rules against incoming data"""
        triggered_alerts = []
        
        for rule in self.alert_rules:
            try:
                if await self._evaluate_rule(rule, data):
                    alert = await self._create_alert_from_rule(rule, data)
                    triggered_alerts.append(alert)
            except Exception as e:
                self.logger.error("Error evaluating alert rule", 
                                rule_name=rule.get('name', 'unknown'),
                                error=str(e))
                                
        return triggered_alerts
        
    async def _evaluate_rule(self, rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluate a single alert rule"""
        conditions = rule.get('conditions', [])
        
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            if field not in data:
                continue
                
            data_value = data[field]
            
            # Evaluate condition
            if operator == 'gt' and data_value > value:
                return True
            elif operator == 'lt' and data_value < value:
                return True
            elif operator == 'eq' and data_value == value:
                return True
            elif operator == 'contains' and value in str(data_value):
                return True
            elif operator == 'regex':
                import re
                if re.search(value, str(data_value)):
                    return True
                    
        return False
        
    async def _create_alert_from_rule(self, 
                                    rule: Dict[str, Any], 
                                    data: Dict[str, Any]) -> Alert:
        """Create alert from triggered rule"""
        rule_name = rule.get('name', 'Unknown Rule')
        alert_id = f"{rule_name}_{data.get('correlation_id', 'unknown')}"
        
        title = rule.get('title', f'Alert: {rule_name}')
        description = rule.get('description', 'Alert rule triggered')
        severity = AlertSeverity(rule.get('severity', 'warning'))
        source = rule.get('source', 'alert_rules')
        
        # Include relevant data in metadata
        metadata = {
            'rule_name': rule_name,
            'triggered_by': data.get('source', 'unknown'),
            'correlation_id': data.get('correlation_id'),
        }
        
        return await self.create_alert(alert_id, title, description, severity, source, metadata)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get alert manager statistics"""
        active_count = len(self.active_alerts)
        severity_counts = {severity.value: 0 for severity in AlertSeverity}
        
        for alert in self.active_alerts.values():
            severity_counts[alert.severity.value] += 1
            
        return {
            'active_alerts': active_count,
            'severity_breakdown': severity_counts,
            'notification_channels': len(self.notification_channels),
            'alert_rules': len(self.alert_rules)
        }