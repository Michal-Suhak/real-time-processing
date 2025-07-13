from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime, timedelta
import json
import asyncio
import httpx
from typing import Dict, List, Any, Optional
import structlog

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'warehouse-log-viewer-secret'

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

class ElasticsearchClient:
    def __init__(self, base_url: str = "http://localhost:9200"):
        self.base_url = base_url
        
    async def search(self, index: str, query: Dict[str, Any], size: int = 100) -> Dict[str, Any]:
        """Search Elasticsearch index"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/{index}/_search"
            response = await client.post(url, json=query, timeout=30)
            response.raise_for_status()
            return response.json()
            
    async def get_indices(self) -> List[str]:
        """Get list of available indices"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/_cat/indices?format=json"
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            indices = response.json()
            return [idx['index'] for idx in indices if idx['index'].startswith('warehouse-')]
            
    async def get_mappings(self, index: str) -> Dict[str, Any]:
        """Get field mappings for index"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/{index}/_mapping"
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

# Initialize Elasticsearch client
es_client = ElasticsearchClient()

@app.route('/')
def index():
    """Main log viewer page"""
    return render_template('log_viewer.html')

@app.route('/api/indices')
def get_indices():
    """Get available log indices"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        indices = loop.run_until_complete(es_client.get_indices())
        return jsonify({'indices': indices})
    except Exception as e:
        logger.error("Failed to get indices", error=str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        loop.close()

@app.route('/api/fields/<index>')
def get_fields(index):
    """Get available fields for an index"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        mappings = loop.run_until_complete(es_client.get_mappings(index))
        
        # Extract field names from mappings
        fields = []
        for idx_name, mapping in mappings.items():
            if 'mappings' in mapping and 'properties' in mapping['mappings']:
                fields.extend(mapping['mappings']['properties'].keys())
        
        return jsonify({'fields': sorted(list(set(fields)))})
    except Exception as e:
        logger.error("Failed to get fields", error=str(e), index=index)
        return jsonify({'error': str(e)}), 500
    finally:
        loop.close()

@app.route('/api/search', methods=['POST'])
def search_logs():
    """Search logs with filters"""
    try:
        data = request.get_json()
        
        # Extract search parameters
        indices = data.get('indices', ['warehouse-logs-*'])
        text_query = data.get('text_query', '')
        filters = data.get('filters', {})
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        size = min(data.get('size', 100), 1000)  # Limit to 1000 results
        sort_field = data.get('sort_field', '@timestamp')
        sort_order = data.get('sort_order', 'desc')
        
        # Build Elasticsearch query
        query = build_search_query(text_query, filters, start_time, end_time)
        
        # Add sorting
        es_query = {
            'query': query,
            'size': size,
            'sort': [{sort_field: {'order': sort_order}}],
            '_source': True
        }
        
        # Execute search
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        index_pattern = ','.join(indices)
        result = loop.run_until_complete(es_client.search(index_pattern, es_query, size))
        
        # Format response
        hits = result.get('hits', {}).get('hits', [])
        logs = []
        for hit in hits:
            log_entry = hit['_source']
            log_entry['_id'] = hit['_id']
            log_entry['_index'] = hit['_index']
            logs.append(log_entry)
        
        response = {
            'logs': logs,
            'total': result.get('hits', {}).get('total', {}).get('value', 0),
            'took': result.get('took', 0)
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error("Search failed", error=str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        loop.close()

@app.route('/api/export', methods=['POST'])
def export_logs():
    """Export search results as JSON or CSV"""
    try:
        data = request.get_json()
        export_format = data.get('format', 'json')
        
        # Use same search logic as search_logs
        indices = data.get('indices', ['warehouse-logs-*'])
        text_query = data.get('text_query', '')
        filters = data.get('filters', {})
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        size = min(data.get('size', 1000), 10000)  # Limit exports to 10k records
        
        query = build_search_query(text_query, filters, start_time, end_time)
        es_query = {
            'query': query,
            'size': size,
            'sort': [{'@timestamp': {'order': 'desc'}}]
        }
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        index_pattern = ','.join(indices)
        result = loop.run_until_complete(es_client.search(index_pattern, es_query, size))
        
        hits = result.get('hits', {}).get('hits', [])
        logs = [hit['_source'] for hit in hits]
        
        if export_format == 'json':
            output = json.dumps(logs, indent=2, default=str)
            mimetype = 'application/json'
            filename = f'warehouse_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        else:  # CSV
            import csv
            import io
            
            if not logs:
                return jsonify({'error': 'No logs to export'}), 400
                
            output_io = io.StringIO()
            
            # Get all unique field names
            all_fields = set()
            for log in logs:
                all_fields.update(log.keys())
            
            fieldnames = sorted(list(all_fields))
            writer = csv.DictWriter(output_io, fieldnames=fieldnames)
            writer.writeheader()
            
            for log in logs:
                # Convert complex objects to strings
                row = {}
                for field in fieldnames:
                    value = log.get(field, '')
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    row[field] = value
                writer.writerow(row)
            
            output = output_io.getvalue()
            mimetype = 'text/csv'
            filename = f'warehouse_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return Response(
            output,
            mimetype=mimetype,
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        logger.error("Export failed", error=str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        loop.close()

@app.route('/api/aggregations', methods=['POST'])
def get_aggregations():
    """Get aggregated data for charts"""
    try:
        data = request.get_json()
        
        indices = data.get('indices', ['warehouse-logs-*'])
        filters = data.get('filters', {})
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        agg_field = data.get('field', 'level')
        
        # Build base query
        query = build_search_query('', filters, start_time, end_time)
        
        # Add aggregations
        es_query = {
            'query': query,
            'size': 0,
            'aggs': {
                'field_counts': {
                    'terms': {
                        'field': agg_field,
                        'size': 20
                    }
                },
                'time_histogram': {
                    'date_histogram': {
                        'field': '@timestamp',
                        'calendar_interval': '1h'
                    }
                }
            }
        }
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        index_pattern = ','.join(indices)
        result = loop.run_until_complete(es_client.search(index_pattern, es_query))
        
        aggregations = result.get('aggregations', {})
        
        # Format field counts
        field_counts = []
        if 'field_counts' in aggregations:
            for bucket in aggregations['field_counts']['buckets']:
                field_counts.append({
                    'key': bucket['key'],
                    'count': bucket['doc_count']
                })
        
        # Format time histogram
        time_histogram = []
        if 'time_histogram' in aggregations:
            for bucket in aggregations['time_histogram']['buckets']:
                time_histogram.append({
                    'timestamp': bucket['key_as_string'],
                    'count': bucket['doc_count']
                })
        
        return jsonify({
            'field_counts': field_counts,
            'time_histogram': time_histogram
        })
        
    except Exception as e:
        logger.error("Aggregation failed", error=str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        loop.close()

def build_search_query(text_query: str, 
                      filters: Dict[str, Any], 
                      start_time: Optional[str], 
                      end_time: Optional[str]) -> Dict[str, Any]:
    """Build Elasticsearch query from search parameters"""
    
    must_clauses = []
    
    # Text search
    if text_query:
        must_clauses.append({
            'multi_match': {
                'query': text_query,
                'fields': ['message', 'description', 'title', 'logger'],
                'type': 'best_fields',
                'fuzziness': 'AUTO'
            }
        })
    
    # Time range filter
    if start_time or end_time:
        time_filter = {'range': {'@timestamp': {}}}
        if start_time:
            time_filter['range']['@timestamp']['gte'] = start_time
        if end_time:
            time_filter['range']['@timestamp']['lte'] = end_time
        must_clauses.append(time_filter)
    
    # Field filters
    for field, value in filters.items():
        if value:
            if isinstance(value, list):
                must_clauses.append({'terms': {field: value}})
            else:
                must_clauses.append({'term': {f'{field}.keyword': value}})
    
    # Build final query
    if must_clauses:
        return {'bool': {'must': must_clauses}}
    else:
        return {'match_all': {}}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)