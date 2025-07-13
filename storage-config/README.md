# Storage & Analytics Architecture

This directory contains configuration and initialization scripts for the warehouse analytics storage layer, implementing a multi-tier storage strategy for different data types and use cases.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Processing    │    │    Storage &     │    │   Visualization │
│    Pipeline     │───▶│    Analytics     │───▶│   & Dashboards  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
              ┌─────▼───┐ ┌───▼────┐ ┌──▼────┐
              │ InfluxDB│ │Elasticsearch│ │ClickHouse │
              │(Metrics)│ │ (Logs)  │ │(Data Warehouse)│
              └─────────┘ └─────────┘ └────────┘
```

## 📊 Storage Systems

### 1. InfluxDB - Time-Series Metrics Storage

**Purpose**: Real-time metrics and monitoring data
**Retention**: 30 days (configurable)
**Data Types**: 
- Performance metrics (latency, throughput, error rates)
- Business KPIs (order rates, inventory levels)
- System health metrics
- Real-time aggregations

**Buckets**:
- `warehouse_metrics` - General metrics (30d retention)
- `warehouse_alerts` - Alert metrics (90d retention)  
- `warehouse_performance` - Performance data (7d retention)
- `warehouse_aggregates` - Aggregated data (365d retention)

**Access**: 
- URL: http://localhost:8086
- Admin UI: http://localhost:8086
- API Token: `warehouse-super-secret-admin-token`

### 2. Elasticsearch - Log Search & Analysis

**Purpose**: Full-text search and log analysis
**Retention**: Index lifecycle management with automatic rollover
**Data Types**:
- Application logs
- Security audit trails
- Alert events
- System logs

**Indices**:
- `warehouse-logs-*` - Application logs (30d retention)
- `warehouse-alerts-*` - Alert data (90d retention)
- `warehouse-audit-*` - Audit trails (2y retention)

**Features**:
- Automatic index templates
- Index lifecycle management (ILM)
- Full-text search capabilities
- Real-time log ingestion

**Access**:
- URL: http://localhost:9200
- Cluster health: `curl http://localhost:9200/_cluster/health`

### 3. ClickHouse - Data Warehouse

**Purpose**: Historical analytics and data warehousing
**Retention**: 2+ years with automatic partitioning
**Data Types**:
- Historical event data
- Aggregated business metrics
- Compliance records
- Long-term trend analysis

**Tables**:
- `raw_events` - All warehouse events (2y retention)
- `inventory_metrics` - Hourly aggregated metrics (1y retention)
- `daily_kpis` - Business KPIs (3y retention)
- `alert_events` - Alert history (6m retention)
- `performance_metrics` - Performance data (30d retention)

**Features**:
- Columnar storage for analytics
- Automatic partitioning by month
- Materialized views for real-time aggregation
- SQL interface for complex analytics

**Access**:
- HTTP: http://localhost:8123
- TCP: localhost:9000
- Users: `warehouse_user` / `readonly_user`

## 🔄 Data Flow

### 1. Real-Time Metrics Flow
```
Kafka Topics → Processing Pipeline → InfluxDB → Grafana Dashboards
```

### 2. Log Analysis Flow  
```
Application Logs → Processing Pipeline → Elasticsearch → Kibana/Search API
```

### 3. Historical Analytics Flow
```
All Events → Processing Pipeline → ClickHouse → Analytics Queries/Reports
```

### 4. Alert Processing Flow
```
Anomaly Detection → Processing Pipeline → [Elasticsearch + ClickHouse] → Alert Dashboard
```

## 🚀 Getting Started

### 1. Start All Services
```bash
# From project root
docker-compose up -d influxdb elasticsearch clickhouse

# Wait for services to be ready
docker-compose logs -f elasticsearch-setup
```

### 2. Verify Connections
```bash
# InfluxDB
curl http://localhost:8086/ping

# Elasticsearch  
curl http://localhost:9200/_cluster/health

# ClickHouse
curl http://localhost:8123/ping
```

### 3. Initialize Data
The processing pipeline automatically:
- Creates InfluxDB buckets and users
- Sets up Elasticsearch indices and templates
- Initializes ClickHouse database and tables

## 📈 Monitoring & Health Checks

### InfluxDB Health
```bash
curl http://localhost:8086/health
```

### Elasticsearch Health
```bash
curl http://localhost:9200/_cluster/health?pretty
```

### ClickHouse Health  
```bash
curl http://localhost:8123/ping
```

## 🔧 Configuration

### Environment Variables
All storage systems are configured via environment variables in `docker-compose.yml`:

```yaml
# InfluxDB
INFLUXDB_URL=http://influxdb:8086
INFLUXDB_TOKEN=warehouse-super-secret-admin-token
INFLUXDB_ORG=warehouse

# Elasticsearch
ELASTICSEARCH_URL=http://elasticsearch:9200

# ClickHouse
CLICKHOUSE_URL=http://clickhouse:8123
CLICKHOUSE_USER=warehouse_user
CLICKHOUSE_PASSWORD=warehouse_password
```

### Storage Adapter Configuration
The processing pipeline uses the `StorageManager` to route data:

```python
# Data routing rules
routing_rules = {
    'metrics': ['influxdb'],
    'logs': ['elasticsearch'], 
    'alerts': ['elasticsearch', 'clickhouse'],
    'events': ['clickhouse'],
    'aggregated': ['clickhouse'],
    'performance': ['influxdb', 'clickhouse']
}
```

## 📊 Analytics Examples

### InfluxDB Queries (Flux)
```flux
// Inventory throughput over time
from(bucket: "warehouse_metrics")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "inventory_throughput")
  |> aggregateWindow(every: 1h, fn: mean)
```

### Elasticsearch Queries
```json
{
  "query": {
    "bool": {
      "must": [
        {"range": {"@timestamp": {"gte": "now-1h"}}},
        {"term": {"severity": "error"}}
      ]
    }
  }
}
```

### ClickHouse Queries
```sql
-- Daily inventory summary
SELECT 
    date,
    warehouse_zone,
    sum(inbound_quantity) as total_inbound,
    sum(outbound_quantity) as total_outbound
FROM inventory_metrics 
WHERE date >= today() - 7
GROUP BY date, warehouse_zone
ORDER BY date DESC;
```

## 🔒 Security Considerations

1. **Authentication**: All systems configured with basic authentication
2. **Network**: Services isolated in Docker network
3. **Encryption**: TLS disabled for development (enable for production)
4. **Access Control**: Role-based users for ClickHouse
5. **Data Retention**: Automatic cleanup policies configured

## 🚨 Troubleshooting

### Common Issues

1. **Elasticsearch Memory**: Increase Docker memory if ES fails to start
2. **ClickHouse Permissions**: Check file permissions for config volumes
3. **InfluxDB Token**: Ensure token matches between services
4. **Network Connectivity**: Verify all services are in `warehouse_network`

### Logs
```bash
# Check service logs
docker-compose logs influxdb
docker-compose logs elasticsearch  
docker-compose logs clickhouse

# Processing pipeline logs
docker-compose logs processing-pipeline
```

## 📚 Further Reading

- [InfluxDB Documentation](https://docs.influxdata.com/)
- [Elasticsearch Guide](https://www.elastic.co/guide/)
- [ClickHouse Documentation](https://clickhouse.com/docs/)
- [Grafana Dashboards](https://grafana.com/docs/)

## 🎯 Performance Tuning

### InfluxDB
- Adjust batch sizes in processing pipeline
- Monitor memory usage and cardinality
- Configure retention policies by data importance

### Elasticsearch
- Tune JVM heap size (currently 1GB)
- Optimize index templates for your data
- Monitor cluster health and shard allocation

### ClickHouse
- Partition by appropriate time intervals
- Use appropriate data types for compression
- Monitor merge performance and disk usage