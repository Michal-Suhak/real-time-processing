# Warehouse Real-Time Processing System

A real-time log processing system for warehouse operations using Django, React, and Apache Kafka.

## Architecture

- **Backend**: Django REST API with uv dependency management
- **Frontend**: React application for warehouse management
- **Database**: PostgreSQL for data persistence
- **Message Broker**: Apache Kafka for real-time log processing
- **Processing Pipeline**: Real-time stream processing with anomaly detection
- **Storage & Analytics**: Multi-tier storage (InfluxDB, Elasticsearch, ClickHouse)
- **Monitoring**: Grafana dashboards with Prometheus metrics
- **Containerization**: Docker Compose for easy development setup

## Quick Start

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd real-time-processing
   ```

2. **Environment setup**:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

3. **Start services**:
   ```bash
   docker-compose up --build
   ```

4. **Access applications**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Kafka UI: http://localhost:8080
   - InfluxDB: http://localhost:8086
   - Elasticsearch: http://localhost:9200
   - ClickHouse: http://localhost:8123
   - Grafana: http://localhost:3001
   - Kafka: localhost:9092

## Services

- **warehouse_db**: PostgreSQL database (port 5432)
- **warehouse_backend**: Django API server (port 8000)
- **warehouse_frontend**: React development server (port 3000)
- **warehouse_kafka**: Kafka broker (port 9092, 9093)
- **warehouse_zookeeper**: Zookeeper for Kafka (port 2181)
- **warehouse_kafka_ui**: Kafka management interface (port 8080)
- **warehouse_kafka_topics_init**: One-time topic initialization service
- **warehouse_processing_pipeline**: Real-time log processing with anomaly detection
- **warehouse_influxdb**: Time-series metrics database (port 8086)
- **warehouse_elasticsearch**: Log search and analysis (port 9200)
- **warehouse_clickhouse**: Data warehouse for analytics (port 8123)
- **warehouse_grafana**: Monitoring dashboards (port 3001)

## Development

### Backend (Django with uv)
```bash
cd backend
uv pip install -e .
python manage.py migrate
python manage.py runserver
```

### Frontend (React)
```bash
cd frontend
npm install
npm start
```

## Kafka Topics

The system automatically creates optimized topics with specific retention policies:

- **warehouse.inventory** (6 partitions, 7 days retention) - Inventory changes, stock updates
- **warehouse.orders** (8 partitions, 30 days retention) - Order processing lifecycle  
- **warehouse.shipments** (4 partitions, 30 days retention) - Shipment tracking, delivery status
- **warehouse.alerts** (3 partitions, 14 days retention) - System alerts, threshold violations
- **warehouse.audit** (2 partitions, 90 days retention) - Security events, compliance logs
- **warehouse.metrics** (3 partitions, 3 days retention) - Performance metrics, system health

Each topic is configured with appropriate partitioning for scalability and retention policies based on data importance. See `kafka-config/README.md` for detailed configuration.

## Storage & Analytics

The system implements a multi-tier storage strategy:

### 📊 InfluxDB - Time-Series Metrics
- **Purpose**: Real-time metrics and monitoring data
- **Retention**: 30 days (configurable by bucket)
- **Use Cases**: Performance metrics, business KPIs, system health

### 🔍 Elasticsearch - Log Search & Analysis  
- **Purpose**: Full-text search and log analysis
- **Retention**: Index lifecycle management with automatic rollover
- **Use Cases**: Application logs, security audit trails, alert events

### 🏢 ClickHouse - Data Warehouse
- **Purpose**: Historical analytics and data warehousing
- **Retention**: 2+ years with automatic partitioning
- **Use Cases**: Historical event data, business analytics, compliance records

### 📈 Grafana - Visualization
- **Purpose**: Real-time dashboards and monitoring
- **Data Sources**: InfluxDB, ClickHouse
- **Features**: Custom dashboards, alerting, user management

See `storage-config/README.md` for detailed configuration and usage examples.