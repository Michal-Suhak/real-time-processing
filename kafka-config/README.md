# Kafka Cluster Configuration

## Overview

This configuration sets up a robust Kafka cluster with multiple topics optimized for different types of warehouse logs.

## Topics Configuration

### 1. **warehouse.inventory** (6 partitions)
- **Purpose**: Inventory changes, stock updates, item additions/removals
- **Retention**: 7 days (604800000 ms)
- **Storage**: 1GB per partition
- **Use Cases**: Real-time inventory tracking, stock alerts

### 2. **warehouse.orders** (8 partitions)
- **Purpose**: Order processing events
- **Retention**: 30 days (2592000000 ms)
- **Storage**: 2GB per partition
- **Use Cases**: Order lifecycle tracking, business analytics

### 3. **warehouse.shipments** (4 partitions)
- **Purpose**: Shipment tracking and delivery status
- **Retention**: 30 days
- **Storage**: 1GB per partition
- **Use Cases**: Logistics tracking, delivery notifications

### 4. **warehouse.alerts** (3 partitions)
- **Purpose**: System alerts and threshold violations
- **Retention**: 14 days (1209600000 ms)
- **Storage**: 512MB per partition
- **Use Cases**: Low stock alerts, system errors, anomaly detection

### 5. **warehouse.audit** (2 partitions)
- **Purpose**: Security and compliance tracking
- **Retention**: 90 days (7776000000 ms)
- **Storage**: 5GB per partition
- **Compression**: GZIP (higher compression for long-term storage)
- **Use Cases**: Security audits, compliance reporting

### 6. **warehouse.metrics** (3 partitions)
- **Purpose**: Performance and system metrics
- **Retention**: 3 days (259200000 ms)
- **Storage**: 1GB per partition
- **Segment**: 1 hour (for faster rollover)
- **Use Cases**: Real-time monitoring, performance analysis

## Partition Strategy

- **High-volume topics** (orders, inventory): More partitions for parallel processing
- **Low-volume topics** (audit, alerts): Fewer partitions to avoid overhead
- **Balanced topics** (shipments, metrics): Moderate partitions for scalability

## Retention Policies

- **Critical business data** (orders, audit): Long retention (30-90 days)
- **Operational data** (inventory, shipments): Medium retention (7-30 days)
- **Monitoring data** (metrics, alerts): Short retention (3-14 days)

## Compression

- **Snappy**: Fast compression for real-time data (inventory, orders, shipments, alerts, metrics)
- **GZIP**: High compression for archival data (audit logs)

## Management

- **Kafka UI**: Available at http://localhost:8080
- **Topic Creation**: Automatic on first startup via `kafka-topics-init` service
- **Monitoring**: Built-in topic metrics and partition details

## Commands

```bash
# View all topics
docker exec warehouse_kafka kafka-topics --bootstrap-server localhost:9092 --list

# Describe specific topic
docker exec warehouse_kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic warehouse.inventory

# View topic configurations
docker exec warehouse_kafka kafka-configs --bootstrap-server localhost:9092 --entity-type topics --entity-name warehouse.orders --describe
```