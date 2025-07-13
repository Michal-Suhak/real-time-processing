#!/bin/bash

# Wait for Elasticsearch to be ready
echo "Waiting for Elasticsearch to be ready..."
while ! curl -s http://elasticsearch:9200/_cluster/health >/dev/null; do
    echo "Elasticsearch is not ready yet. Waiting..."
    sleep 10
done

echo "Elasticsearch is ready. Setting up indices and templates..."

# Load index templates and lifecycle policies
curl -X PUT "elasticsearch:9200/_index_template/warehouse-logs-template" \
  -H "Content-Type: application/json" \
  -d "$(jq '.index_templates[0].template' /elasticsearch-config/index-templates.json)"

curl -X PUT "elasticsearch:9200/_index_template/warehouse-alerts-template" \
  -H "Content-Type: application/json" \
  -d "$(jq '.index_templates[1].template' /elasticsearch-config/index-templates.json)"

curl -X PUT "elasticsearch:9200/_index_template/warehouse-audit-template" \
  -H "Content-Type: application/json" \
  -d "$(jq '.index_templates[2].template' /elasticsearch-config/index-templates.json)"

# Create lifecycle policies
curl -X PUT "elasticsearch:9200/_ilm/policy/warehouse-logs-policy" \
  -H "Content-Type: application/json" \
  -d "$(jq '.lifecycle_policies[0]' /elasticsearch-config/index-templates.json)"

curl -X PUT "elasticsearch:9200/_ilm/policy/warehouse-alerts-policy" \
  -H "Content-Type: application/json" \
  -d "$(jq '.lifecycle_policies[1]' /elasticsearch-config/index-templates.json)"

curl -X PUT "elasticsearch:9200/_ilm/policy/warehouse-audit-policy" \
  -H "Content-Type: application/json" \
  -d "$(jq '.lifecycle_policies[2]' /elasticsearch-config/index-templates.json)"

# Create initial indices with aliases
curl -X PUT "elasticsearch:9200/warehouse-logs-000001" \
  -H "Content-Type: application/json" \
  -d '{
    "aliases": {
      "warehouse-logs": {
        "is_write_index": true
      }
    }
  }'

curl -X PUT "elasticsearch:9200/warehouse-alerts-000001" \
  -H "Content-Type: application/json" \
  -d '{
    "aliases": {
      "warehouse-alerts": {
        "is_write_index": true
      }
    }
  }'

curl -X PUT "elasticsearch:9200/warehouse-audit-000001" \
  -H "Content-Type: application/json" \
  -d '{
    "aliases": {
      "warehouse-audit": {
        "is_write_index": true
      }
    }
  }'

echo "Elasticsearch setup completed successfully!"