#!/bin/bash

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
while ! kafka-topics --bootstrap-server kafka:9092 --list >/dev/null 2>&1; do
    echo "Kafka is not ready yet. Waiting..."
    sleep 5
done

echo "Kafka is ready. Creating topics..."

# Parse the JSON config file and create topics
jq -c '.topics[]' /kafka-config/topics-config.json | while read topic; do
    NAME=$(echo $topic | jq -r '.name')
    PARTITIONS=$(echo $topic | jq -r '.partitions')
    REPLICATION_FACTOR=$(echo $topic | jq -r '.replication_factor')
    DESCRIPTION=$(echo $topic | jq -r '.description')
    
    echo "Creating topic: $NAME"
    echo "Description: $DESCRIPTION"
    
    # Create the topic
    kafka-topics --bootstrap-server kafka:9092 \
        --create \
        --topic $NAME \
        --partitions $PARTITIONS \
        --replication-factor $REPLICATION_FACTOR \
        --if-not-exists
    
    # Apply topic configurations
    CONFIG_ENTRIES=""
    for key in $(echo $topic | jq -r '.config | keys[]'); do
        value=$(echo $topic | jq -r ".config[\"$key\"]")
        if [ -z "$CONFIG_ENTRIES" ]; then
            CONFIG_ENTRIES="$key=$value"
        else
            CONFIG_ENTRIES="$CONFIG_ENTRIES,$key=$value"
        fi
    done
    
    if [ ! -z "$CONFIG_ENTRIES" ]; then
        echo "Applying configurations: $CONFIG_ENTRIES"
        kafka-configs --bootstrap-server kafka:9092 \
            --entity-type topics \
            --entity-name $NAME \
            --alter \
            --add-config $CONFIG_ENTRIES
    fi
    
    echo "Topic $NAME created successfully"
    echo "---"
done

echo "All topics created successfully!"

# List all topics to verify
echo "Current topics:"
kafka-topics --bootstrap-server kafka:9092 --list

# Show topic details
echo -e "\nTopic details:"
for topic in warehouse.inventory warehouse.orders warehouse.shipments warehouse.alerts warehouse.audit warehouse.metrics; do
    echo "=== $topic ==="
    kafka-topics --bootstrap-server kafka:9092 --describe --topic $topic
    echo
done