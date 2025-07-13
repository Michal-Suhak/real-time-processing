# Warehouse Processing Pipeline

A real-time log processing pipeline for warehouse operations with advanced analytics, anomaly detection, and metrics aggregation.

## Features

### 🔄 Real-Time Stream Processing
- **Kafka Consumers**: Multi-threaded consumers for parallel processing
- **Message Batching**: Configurable batch sizes for optimal throughput
- **Error Handling**: Robust error handling with retry mechanisms
- **Graceful Shutdown**: Clean shutdown with signal handling

### 🔍 Data Transformation & Enrichment
- **Data Validation**: Schema validation and data quality checks
- **Field Normalization**: Standardized data formats and field mappings
- **Context Enrichment**: Item details, location info, and business context
- **Temporal Analysis**: Business hours, shift patterns, and seasonal trends

### 🚨 Anomaly Detection
- **Statistical Analysis**: Z-score and IQR-based outlier detection
- **Pattern Recognition**: Time-based and frequency anomalies
- **Business Logic**: Inventory-specific anomaly rules
- **Risk Assessment**: Multi-factor risk scoring

### 📊 Metrics & Aggregation
- **Time Windows**: 1min, 5min, 15min, and 1hour aggregations
- **Statistical Metrics**: Mean, median, percentiles, trends
- **Business KPIs**: Throughput, quality scores, distribution metrics
- **Real-Time Dashboards**: Prometheus metrics for monitoring

### 💾 Caching & Storage
- **Redis Integration**: High-performance caching layer
- **Data Persistence**: Metrics and pattern storage
- **TTL Management**: Configurable cache expiration policies

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Kafka Topics  │───▶│  Kafka Consumers │───▶│   Processors    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                       ┌──────────────────┐              ▼
                       │      Redis       │◀────┌─────────────────┐
                       │     Cache        │     │    Enrichers    │
                       └──────────────────┘     └─────────────────┘
                                                         │
                       ┌──────────────────┐              ▼
                       │   Prometheus     │◀────┌─────────────────┐
                       │    Metrics       │     │ Anomaly Detection│
                       └──────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │   Aggregators   │
                                                └─────────────────┘
```

## Processing Components

### Consumers (`src/consumers/`)
- **BaseConsumer**: Abstract base class with common functionality
- **InventoryConsumer**: Specialized consumer for inventory events
- **Batch Processing**: Efficient batch message processing
- **Offset Management**: Manual offset commits for reliability

### Processors (`src/processors/`)
- **InventoryProcessor**: Core data transformation logic
- **Field Validation**: Data type and range validation
- **Timestamp Parsing**: Flexible timestamp handling
- **Business Context**: Shift and business hour analysis

### Enrichers (`src/enrichers/`)
- **InventoryEnricher**: Data enrichment with external context
- **Item Details**: Product information and metadata
- **Location Context**: Warehouse zone and capacity data
- **Risk Assessment**: Multi-factor risk analysis

### Anomaly Detection (`src/anomaly_detection/`)
- **BaseDetector**: Framework for anomaly detection algorithms
- **InventoryAnomalyDetector**: Business-specific anomaly rules
- **Statistical Methods**: Z-score, IQR, trend analysis
- **Alert Generation**: Structured anomaly alerts

### Aggregators (`src/aggregators/`)
- **BaseAggregator**: Time-windowed aggregation framework
- **InventoryAggregator**: Business metrics and KPIs
- **Statistical Analysis**: Comprehensive statistical calculations
- **Trend Detection**: Pattern and trend identification

## Configuration

### Environment Variables
```bash
# Kafka Settings
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_CONSUMER_GROUP=warehouse-processing
KAFKA_BATCH_SIZE=50

# Redis Settings
REDIS_URL=redis://redis:6379/0
REDIS_TTL_CACHE=3600

# Processing Settings
LOG_LEVEL=INFO
METRICS_PORT=8090
WINDOW_SIZE_MINUTES=5
CONFIDENCE_THRESHOLD=0.8
```

### Topics Processed
- **warehouse.inventory**: Inventory change events
- **warehouse.orders**: Order processing events  
- **warehouse.shipments**: Shipment tracking events
- **warehouse.alerts**: System alerts and notifications
- **warehouse.audit**: Audit and compliance logs
- **warehouse.metrics**: System performance metrics

## Monitoring & Observability

### Prometheus Metrics
- `messages_processed_total`: Total processed messages by topic and status
- `message_processing_seconds`: Processing time histograms
- `active_consumers`: Number of active consumer instances
- `anomalies_detected_total`: Anomaly detection counters
- `redis_operations_total`: Redis operation metrics

### Health Checks
- **Kafka Connectivity**: Broker connection status
- **Redis Availability**: Cache system health
- **Consumer Status**: Active consumer monitoring
- **Processing Metrics**: Throughput and error rates

### Logging
- **Structured Logging**: JSON-formatted logs with structured data
- **Log Levels**: Configurable verbosity (DEBUG, INFO, WARNING, ERROR)
- **Context Tracking**: Request correlation and tracing
- **Error Details**: Comprehensive error information

## Anomaly Types Detected

### Volume Anomalies
- Unusual quantity changes (Z-score > 3.0)
- Bulk transactions outside normal patterns
- Rapid stock depletion alerts

### Temporal Anomalies
- After-hours activity detection
- Weekend operation alerts
- Unusual timing patterns

### Business Logic Anomalies
- Negative stock risk warnings
- High-value transaction scrutiny
- Supplier delivery pattern violations
- Location access anomalies

### Statistical Anomalies
- Frequency-based outlier detection
- Pattern deviation alerts
- Trend change notifications

## Development

### Local Setup
```bash
# Install dependencies
uv pip install -e .

# Run tests
pytest tests/

# Run locally (requires Kafka and Redis)
python -m src.main
```

### Docker Development
```bash
# Build and run
docker-compose up processing-pipeline

# View logs
docker-compose logs -f processing-pipeline

# Scale consumers
docker-compose up --scale processing-pipeline=3
```

## Performance Tuning

### Kafka Optimization
- **Batch Size**: Adjust for throughput vs latency trade-off
- **Poll Timeout**: Balance responsiveness and CPU usage
- **Consumer Groups**: Scale with multiple instances
- **Partition Strategy**: Distribute load across partitions

### Memory Management
- **Window Sizes**: Configure time windows based on memory constraints
- **Cache TTL**: Balance performance and memory usage
- **Data Retention**: Optimize historical data storage

### Monitoring Guidelines
- Monitor processing lag and throughput
- Track anomaly detection accuracy
- Observe memory and CPU usage patterns
- Alert on consumer failures or health issues