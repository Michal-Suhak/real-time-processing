# InfluxDB v2 Initial Database Configuration

# Create organization
influx org create -n warehouse -t warehouse-metrics-token

# Create buckets for different metric types
influx bucket create -n warehouse_metrics -o warehouse -r 30d
influx bucket create -n warehouse_alerts -o warehouse -r 90d  
influx bucket create -n warehouse_performance -o warehouse -r 7d
influx bucket create -n warehouse_aggregates -o warehouse -r 365d

# Create users
influx user create -n metrics_writer -o warehouse
influx user create -n analytics_reader -o warehouse

# Create API tokens
influx auth create -o warehouse --read-buckets --write-buckets -d "Processing Pipeline Token"
influx auth create -o warehouse --read-buckets -d "Analytics Reader Token"