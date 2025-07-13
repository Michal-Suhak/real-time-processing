-- Create warehouse analytics database
CREATE DATABASE IF NOT EXISTS warehouse_analytics;

-- Use the database
USE warehouse_analytics;

-- Raw events table for all warehouse operations
CREATE TABLE IF NOT EXISTS raw_events (
    event_id String,
    timestamp DateTime64(3),
    event_type LowCardinality(String),
    topic LowCardinality(String),
    partition UInt32,
    offset UInt64,
    source LowCardinality(String),
    correlation_id String,
    user_id String,
    session_id String,
    
    -- Inventory specific fields
    item_id String,
    action LowCardinality(String),
    quantity Int32,
    location_id String,
    warehouse_zone LowCardinality(String),
    item_category LowCardinality(String),
    
    -- Order specific fields  
    order_id String,
    order_status LowCardinality(String),
    customer_id String,
    order_value Decimal64(2),
    
    -- Shipment specific fields
    shipment_id String,
    carrier LowCardinality(String),
    tracking_number String,
    destination_country LowCardinality(String),
    
    -- Additional metadata
    raw_data String,
    processing_timestamp DateTime64(3) DEFAULT now64(),
    
    -- Partitioning and indexing
    date Date MATERIALIZED toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (event_type, timestamp, item_id)
TTL timestamp + INTERVAL 2 YEAR;

-- Aggregated inventory metrics table
CREATE TABLE IF NOT EXISTS inventory_metrics (
    date Date,
    hour UInt8,
    warehouse_zone LowCardinality(String),
    item_category LowCardinality(String),
    location_id String,
    
    -- Volume metrics
    total_transactions UInt32,
    inbound_transactions UInt32,
    outbound_transactions UInt32,
    total_quantity Int64,
    inbound_quantity Int64,
    outbound_quantity Int64,
    
    -- Quality metrics
    avg_processing_time_ms Float32,
    error_count UInt32,
    success_rate Float32,
    
    -- Value metrics
    avg_transaction_value Decimal64(2),
    total_transaction_value Decimal64(2),
    
    -- Statistical metrics
    quantity_stddev Float32,
    quantity_percentile_95 Int32,
    quantity_percentile_99 Int32,
    
    -- Anomaly metrics
    anomaly_count UInt32,
    avg_anomaly_score Float32,
    max_anomaly_score Float32,
    
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, hour, warehouse_zone, item_category)
TTL date + INTERVAL 1 YEAR;

-- Daily warehouse KPIs
CREATE TABLE IF NOT EXISTS daily_kpis (
    date Date,
    warehouse_zone LowCardinality(String),
    
    -- Operational metrics
    total_orders UInt32,
    completed_orders UInt32,
    cancelled_orders UInt32,
    pending_orders UInt32,
    order_completion_rate Float32,
    
    -- Inventory metrics
    stock_movements UInt32,
    items_processed UInt32,
    unique_items_touched UInt32,
    avg_stock_level Float32,
    stock_turnover_rate Float32,
    
    -- Performance metrics
    avg_processing_time_minutes Float32,
    throughput_items_per_hour Float32,
    error_rate Float32,
    
    -- Financial metrics
    total_revenue Decimal64(2),
    avg_order_value Decimal64(2),
    shipping_costs Decimal64(2),
    
    -- Quality metrics
    accuracy_rate Float32,
    customer_satisfaction_score Float32,
    
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, warehouse_zone)
TTL date + INTERVAL 3 YEAR;

-- Alert events table
CREATE TABLE IF NOT EXISTS alert_events (
    alert_id String,
    timestamp DateTime64(3),
    alert_type LowCardinality(String),
    severity LowCardinality(String),
    source LowCardinality(String),
    
    -- Alert details
    title String,
    description String,
    confidence_score Float32,
    
    -- Context data
    affected_item_id String,
    affected_location String,
    warehouse_zone LowCardinality(String),
    
    -- Resolution tracking
    resolved UInt8 DEFAULT 0,
    resolution_timestamp Nullable(DateTime64(3)),
    resolution_time_minutes Nullable(Float32),
    assignee String,
    
    -- Source event data
    source_event_id String,
    source_correlation_id String,
    
    created_at DateTime64(3) DEFAULT now64(),
    date Date MATERIALIZED toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (alert_type, severity, timestamp)
TTL timestamp + INTERVAL 6 MONTH;

-- Performance tracking table
CREATE TABLE IF NOT EXISTS performance_metrics (
    timestamp DateTime64(3),
    metric_name LowCardinality(String),
    metric_type LowCardinality(String), -- counter, gauge, histogram
    service_name LowCardinality(String),
    
    -- Metric values
    value Float64,
    count UInt64 DEFAULT 1,
    
    -- Labels/dimensions
    labels Map(String, String),
    
    -- Performance context
    duration_ms Nullable(Float32),
    status_code Nullable(UInt16),
    error_message Nullable(String),
    
    date Date MATERIALIZED toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (metric_name, service_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- Materialized views for real-time aggregations

-- Real-time inventory summary
CREATE MATERIALIZED VIEW IF NOT EXISTS inventory_summary_mv TO inventory_metrics AS
SELECT
    toDate(timestamp) as date,
    toHour(timestamp) as hour,
    warehouse_zone,
    item_category,
    location_id,
    
    count() as total_transactions,
    countIf(action IN ('stock_in', 'received', 'restocked')) as inbound_transactions,
    countIf(action IN ('stock_out', 'picked', 'shipped')) as outbound_transactions,
    
    sum(quantity) as total_quantity,
    sumIf(quantity, action IN ('stock_in', 'received', 'restocked')) as inbound_quantity,
    sumIf(abs(quantity), action IN ('stock_out', 'picked', 'shipped')) as outbound_quantity,
    
    avg(toFloat32(JSONExtractFloat(raw_data, 'processing_time_ms'))) as avg_processing_time_ms,
    countIf(JSONExtractString(raw_data, 'status') = 'error') as error_count,
    (count() - countIf(JSONExtractString(raw_data, 'status') = 'error')) / count() as success_rate,
    
    avg(toDecimal64(JSONExtractFloat(raw_data, 'transaction_value'), 2)) as avg_transaction_value,
    sum(toDecimal64(JSONExtractFloat(raw_data, 'transaction_value'), 2)) as total_transaction_value,
    
    stddevPop(quantity) as quantity_stddev,
    quantile(0.95)(quantity) as quantity_percentile_95,
    quantile(0.99)(quantity) as quantity_percentile_99,
    
    countIf(JSONExtractFloat(raw_data, 'anomaly_score') > 0.7) as anomaly_count,
    avgIf(toFloat32(JSONExtractFloat(raw_data, 'anomaly_score')), JSONExtractFloat(raw_data, 'anomaly_score') > 0) as avg_anomaly_score,
    maxIf(toFloat32(JSONExtractFloat(raw_data, 'anomaly_score')), JSONExtractFloat(raw_data, 'anomaly_score') > 0) as max_anomaly_score,
    
    now64() as created_at
FROM raw_events
WHERE event_type = 'inventory'
GROUP BY date, hour, warehouse_zone, item_category, location_id;

-- Create indexes for better query performance
-- Note: ClickHouse uses ORDER BY for primary indexing

-- Additional secondary indexes for specific query patterns
ALTER TABLE raw_events ADD INDEX idx_correlation_id correlation_id TYPE bloom_filter(0.01) GRANULARITY 1;
ALTER TABLE raw_events ADD INDEX idx_user_id user_id TYPE bloom_filter(0.01) GRANULARITY 1;
ALTER TABLE raw_events ADD INDEX idx_item_id item_id TYPE bloom_filter(0.01) GRANULARITY 1;

-- Grant permissions
GRANT ALL ON warehouse_analytics.* TO warehouse_user;
GRANT SELECT ON warehouse_analytics.* TO readonly_user;