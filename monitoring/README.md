# Warehouse Monitoring & Visualization

Complete monitoring and visualization solution for the warehouse real-time processing system, providing real-time dashboards, intelligent alerting, and comprehensive log analysis.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Data Sources  │───▶│   Monitoring &   │───▶│  Visualization  │
│                 │    │   Alerting       │    │   & Analysis    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │                        │
    ┌───▼────┐              ┌────▼────┐              ┌────▼────┐
    │ Kafka  │              │ Alert   │              │ Grafana │
    │InfluxDB│              │ Manager │              │Dashboard│
    │ ClickH │              │ System  │              │Log View │
    │ ElasticS│              │         │              │         │
    └────────┘              └─────────┘              └─────────┘
```

## 📊 Components

### 1. Grafana Dashboards

**Purpose**: Real-time visualization of warehouse KPIs and system metrics

**Features**:
- **Warehouse Overview Dashboard**: High-level operational metrics
- **Inventory Analytics Dashboard**: Detailed inventory movement analysis
- **System Performance Dashboard**: Technical performance metrics
- **Alert Dashboard**: Active alerts and alert trends

**Data Sources**:
- InfluxDB: Real-time metrics and time-series data
- ClickHouse: Historical analytics and aggregated data
- Prometheus: System performance metrics

**Access**: http://localhost:3001 (admin/admin)

### 2. Alert Management System

**Purpose**: Intelligent alerting for critical events and anomalies

**Features**:
- **Rule-Based Alerting**: Configurable alert rules for various conditions
- **Multi-Channel Notifications**: Email, Slack, webhooks
- **Alert Lifecycle Management**: Create, acknowledge, resolve alerts
- **Severity Levels**: Info, Warning, Error, Critical
- **Rate Limiting**: Prevent alert storms

**Alert Rules**:
- High anomaly scores (> 0.8)
- Negative stock risks
- Large quantity movements
- After-hours activity
- Processing latency issues
- System health degradation

### 3. Log Search & Analysis Interface

**Purpose**: Web-based log search and filtering for operational analysis

**Features**:
- **Full-Text Search**: Search across message, description, title fields
- **Advanced Filtering**: Filter by level, source, time range
- **Real-Time Updates**: Live log streaming
- **Export Capabilities**: JSON and CSV export
- **Visual Analytics**: Charts and aggregations
- **Responsive Design**: Mobile-friendly interface

**Access**: http://localhost:5000

## 🚀 Quick Start

### 1. Start Monitoring Services
```bash
# Start all monitoring components
docker-compose up -d grafana log-viewer

# Verify services are running
docker-compose ps | grep -E "(grafana|log-viewer)"
```

### 2. Access Dashboards
```bash
# Grafana dashboards
open http://localhost:3001
# Login: admin / admin

# Log viewer interface  
open http://localhost:5000
```

### 3. Configure Alerting
```bash
# Edit alert configuration
vim monitoring/alerting/config.json

# Update notification channels (email, Slack, webhooks)
# Adjust alert rules and thresholds
```

## 📈 Dashboard Details

### Warehouse Overview Dashboard
- **Inventory Transaction Volume**: Real-time transaction trends
- **System Success Rate**: Overall system health percentage
- **Items by Warehouse Zone**: Distribution pie chart
- **Critical Alerts**: Count of active critical alerts
- **System Uptime**: Availability percentage
- **Processing Latency**: P95/P99 response times
- **Recent Unresolved Alerts**: Table of current issues

### Inventory Analytics Dashboard
- **Inventory Movement by Zone**: Time-series by warehouse zone
- **Activity Heatmap**: Zone × Category transaction matrix
- **Top Item Categories**: Ranked by transaction volume
- **Inventory Actions Over Time**: Stacked bar chart by action type
- **Anomaly Detection Scores**: Real-time anomaly trends

## 🚨 Alert System Configuration

### Alert Rules Configuration
Edit `monitoring/alerting/alert_rules.json`:

```json
{
  "name": "high_anomaly_score",
  "title": "High Anomaly Score Detected",
  "severity": "warning",
  "conditions": [
    {
      "field": "anomaly_score",
      "operator": "gt", 
      "value": 0.8
    }
  ]
}
```

### Notification Channels
Configure in `monitoring/alerting/config.json`:

```json
{
  "notification_channels": {
    "email": {
      "host": "smtp.gmail.com",
      "to_emails": ["ops@warehouse.com"]
    },
    "slack": {
      "webhook_url": "https://hooks.slack.com/..."
    }
  }
}
```

### Alert Severity Levels
- **INFO**: Informational events, no action required
- **WARNING**: Potential issues that should be monitored
- **ERROR**: Problems that require attention
- **CRITICAL**: Urgent issues requiring immediate action

## 🔍 Log Search Features

### Search Capabilities
- **Text Search**: Full-text search across log messages
- **Field Filters**: Level, source, warehouse zone, item category
- **Time Range**: Flexible time range selection
- **Quick Filters**: 15min, 1hr, 6hr, 24hr presets

### Export & Analysis
- **JSON Export**: Full log data with metadata
- **CSV Export**: Tabular format for spreadsheet analysis
- **Live Charts**: Real-time level distribution and timeline
- **Aggregations**: Count by field values and time buckets

### Advanced Features
- **Log Level Distribution**: Pie chart of log levels
- **Activity Timeline**: Hourly log volume chart
- **Recent Searches**: Saved search history
- **Responsive Design**: Works on mobile devices

## 🔧 Configuration

### Environment Variables
```bash
# Grafana
GF_SECURITY_ADMIN_PASSWORD=admin
GF_INSTALL_PLUGINS=grafana-clickhouse-datasource

# Log Viewer
FLASK_ENV=production
ELASTICSEARCH_URL=http://elasticsearch:9200

# Alert Manager
EMAIL_HOST=smtp.gmail.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

### Data Source Configuration
Grafana data sources are automatically provisioned:
- **InfluxDB-Warehouse**: Time-series metrics
- **ClickHouse-Warehouse**: Historical analytics
- **Prometheus-Pipeline**: System performance

### Dashboard Provisioning
Dashboards are automatically loaded from:
```
monitoring/grafana/dashboards/
├── warehouse-overview.json
├── inventory-analytics.json  
└── system-performance.json
```

## 📊 Metrics & KPIs

### Business Metrics
- **Transaction Volume**: Inbound/outbound inventory movements
- **Success Rate**: Percentage of successful operations
- **Processing Latency**: Time to process events
- **Alert Volume**: Count of active alerts by severity

### Operational Metrics
- **System Uptime**: Service availability percentage
- **Throughput**: Events processed per second
- **Error Rate**: Percentage of failed operations
- **Resource Utilization**: CPU, memory, disk usage

### Security Metrics
- **After-Hours Activity**: Operations outside business hours
- **User Activity**: Unusual user behavior patterns
- **Data Quality**: Malformed or invalid data detection
- **Audit Events**: Security-relevant actions

## 🛠️ Development & Customization

### Adding New Dashboards
1. Create JSON dashboard file in `monitoring/grafana/dashboards/`
2. Restart Grafana service: `docker-compose restart grafana`
3. Dashboard automatically loaded via provisioning

### Custom Alert Rules
1. Edit `monitoring/alerting/alert_rules.json`
2. Add new rule with conditions and metadata
3. Restart processing pipeline to load new rules

### Log Viewer Extensions
1. Modify `monitoring/log-viewer/app.py` for new API endpoints
2. Update `templates/log_viewer.html` for UI changes
3. Rebuild container: `docker-compose build log-viewer`

## 🔒 Security Considerations

### Authentication
- **Grafana**: Default admin/admin (change in production)
- **Log Viewer**: No authentication (add auth for production)
- **Elasticsearch**: No authentication (basic auth recommended)

### Network Security
- All services isolated in Docker network
- Expose only necessary ports
- Use HTTPS in production environments

### Data Privacy
- Log data may contain sensitive information
- Configure appropriate retention policies
- Implement access controls based on user roles

## 🚨 Troubleshooting

### Common Issues

1. **Grafana Not Loading Dashboards**
   ```bash
   # Check provisioning volumes
   docker-compose logs grafana
   
   # Verify file permissions
   ls -la monitoring/grafana/dashboards/
   ```

2. **Log Viewer Cannot Connect to Elasticsearch**
   ```bash
   # Check Elasticsearch health
   curl http://localhost:9200/_cluster/health
   
   # Verify network connectivity
   docker-compose exec log-viewer ping elasticsearch
   ```

3. **Alerts Not Sending**
   ```bash
   # Check alert manager logs
   docker-compose logs processing-pipeline | grep alert
   
   # Verify notification configuration
   cat monitoring/alerting/config.json
   ```

### Performance Tuning

1. **Dashboard Performance**
   - Adjust query time ranges
   - Reduce dashboard refresh intervals
   - Optimize data source queries

2. **Log Search Performance**
   - Limit search result sizes
   - Use appropriate time ranges
   - Index optimization in Elasticsearch

3. **Alert Performance**
   - Configure rate limiting
   - Adjust alert rule frequency
   - Optimize notification channels

## 📚 API Reference

### Log Viewer API
```bash
# Search logs
POST /api/search
{
  "text_query": "error",
  "filters": {"level": "error"},
  "start_time": "2024-01-01T00:00:00Z",
  "size": 100
}

# Get aggregations
POST /api/aggregations
{
  "field": "level",
  "start_time": "2024-01-01T00:00:00Z"
}

# Export logs
POST /api/export
{
  "format": "json",
  "filters": {"level": "error"}
}
```

### Alert Manager API
```python
# Create alert
await alert_manager.create_alert(
    alert_id="high_anomaly_001",
    title="High Anomaly Score",
    description="Anomaly score exceeded threshold",
    severity=AlertSeverity.WARNING,
    source="anomaly_detection"
)

# Acknowledge alert
await alert_manager.acknowledge_alert("high_anomaly_001", "admin")

# Resolve alert
await alert_manager.resolve_alert("high_anomaly_001")
```

## 🎯 Best Practices

### Dashboard Design
- Use consistent color schemes and naming
- Include context and tooltips
- Optimize for different screen sizes
- Group related metrics together

### Alert Configuration
- Start with conservative thresholds
- Test notification channels regularly
- Document alert response procedures
- Review and tune rules based on feedback

### Log Analysis
- Use structured logging formats
- Include correlation IDs for tracing
- Implement log retention policies
- Regular log analysis and optimization

This monitoring system provides comprehensive visibility into warehouse operations with real-time dashboards, intelligent alerting, and powerful log analysis capabilities.