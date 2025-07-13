import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ElasticsearchException
import structlog

from .base_storage import BaseStorageAdapter, StorageError, ConnectionError, WriteError

logger = structlog.get_logger(__name__)

class ElasticsearchAdapter(BaseStorageAdapter):
    """Elasticsearch adapter for log search and analysis"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client: Optional[AsyncElasticsearch] = None
        
        # Configuration
        self.url = config.get('url', 'http://localhost:9200')
        self.username = config.get('username')
        self.password = config.get('password')
        self.verify_certs = config.get('verify_certs', False)
        self.timeout = config.get('timeout', 30)
        
        # Index settings
        self.default_index = config.get('default_index', 'warehouse-logs')
        self.index_patterns = {
            'logs': 'warehouse-logs',
            'alerts': 'warehouse-alerts', 
            'audit': 'warehouse-audit'
        }
        
    async def connect(self) -> bool:
        """Establish connection to Elasticsearch"""
        try:
            # Build connection parameters
            kwargs = {
                'hosts': [self.url],
                'timeout': self.timeout,
                'verify_certs': self.verify_certs
            }
            
            if self.username and self.password:
                kwargs['basic_auth'] = (self.username, self.password)
                
            self.client = AsyncElasticsearch(**kwargs)
            
            # Test connection
            health = await self.client.cluster.health()
            if health['status'] == 'red':
                raise ConnectionError("Elasticsearch cluster status is red")
                
            self.logger.info("Connected to Elasticsearch", 
                           url=self.url, 
                           cluster_status=health['status'])
            return True
            
        except Exception as e:
            self.logger.error("Failed to connect to Elasticsearch", error=str(e))
            raise ConnectionError(f"Elasticsearch connection failed: {e}")
            
    async def disconnect(self) -> None:
        """Close connection to Elasticsearch"""
        if self.client:
            await self.client.close()
            self.client = None
            self.logger.info("Disconnected from Elasticsearch")
            
    async def health_check(self) -> bool:
        """Check if Elasticsearch is healthy"""
        if not self.client:
            return False
            
        try:
            health = await self.client.cluster.health()
            return health['status'] in ['green', 'yellow']
        except Exception as e:
            self.logger.warning("Elasticsearch health check failed", error=str(e))
            return False
            
    async def store(self, data: Dict[str, Any]) -> bool:
        """Store single document in Elasticsearch"""
        return await self.batch_store([data])
        
    async def batch_store(self, data_list: List[Dict[str, Any]]) -> bool:
        """Store multiple documents in Elasticsearch using bulk API"""
        if not self.client:
            raise ConnectionError("Not connected to Elasticsearch")
            
        try:
            if not data_list:
                return True
                
            # Prepare bulk operations
            operations = []
            for data in data_list:
                doc = self._prepare_document(data)
                index_name = self._get_index_name(data)
                
                # Index operation
                operations.append({
                    "index": {
                        "_index": index_name,
                        "_id": data.get('id') or data.get('correlation_id')
                    }
                })
                operations.append(doc)
                
            # Execute bulk operation
            response = await self.client.bulk(
                operations=operations,
                refresh=False  # Don't wait for refresh for performance
            )
            
            # Check for errors
            if response.get('errors'):
                error_count = sum(1 for item in response['items'] 
                                if 'error' in item.get('index', {}))
                self.logger.warning("Bulk indexing had errors", 
                                  total=len(data_list), 
                                  errors=error_count)
                                  
                # Log first few errors for debugging
                for item in response['items'][:5]:
                    if 'error' in item.get('index', {}):
                        self.logger.error("Index error", 
                                        error=item['index']['error'])
            else:
                self.logger.debug("Stored documents to Elasticsearch", 
                                count=len(data_list))
                
            return True
            
        except Exception as e:
            self.logger.error("Failed to store documents to Elasticsearch", 
                            error=str(e), count=len(data_list))
            raise WriteError(f"Elasticsearch bulk write failed: {e}")
            
    def _prepare_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare document for Elasticsearch indexing"""
        doc = data.copy()
        
        # Ensure @timestamp field exists
        if '@timestamp' not in doc:
            timestamp = doc.get('timestamp')
            if timestamp:
                if isinstance(timestamp, str):
                    # Parse ISO format timestamp
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        doc['@timestamp'] = dt.isoformat()
                    except ValueError:
                        doc['@timestamp'] = datetime.now(tz=timezone.utc).isoformat()
                elif isinstance(timestamp, (int, float)):
                    # Unix timestamp
                    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    doc['@timestamp'] = dt.isoformat()
                else:
                    doc['@timestamp'] = datetime.now(tz=timezone.utc).isoformat()
            else:
                doc['@timestamp'] = datetime.now(tz=timezone.utc).isoformat()
                
        # Ensure timestamp field is also ISO format if it exists
        if 'timestamp' in doc and not isinstance(doc['timestamp'], str):
            if isinstance(doc['timestamp'], (int, float)):
                dt = datetime.fromtimestamp(doc['timestamp'], tz=timezone.utc)
                doc['timestamp'] = dt.isoformat()
                
        # Clean up None values and empty strings
        doc = {k: v for k, v in doc.items() if v is not None and v != ''}
        
        # Ensure certain fields are strings for keyword mapping
        string_fields = ['level', 'logger', 'topic', 'action', 'location_id', 
                        'user_id', 'correlation_id', 'source', 'warehouse_zone',
                        'item_category', 'alert_type', 'severity']
        
        for field in string_fields:
            if field in doc and doc[field] is not None:
                doc[field] = str(doc[field])
                
        # Ensure numeric fields are properly typed
        numeric_fields = ['partition', 'offset', 'quantity', 'processing_time_ms',
                         'anomaly_score', 'confidence_score']
        
        for field in numeric_fields:
            if field in doc and doc[field] is not None:
                try:
                    if isinstance(doc[field], str):
                        if '.' in doc[field]:
                            doc[field] = float(doc[field])
                        else:
                            doc[field] = int(doc[field])
                except (ValueError, TypeError):
                    # Keep as string if conversion fails
                    pass
                    
        return doc
        
    def _get_index_name(self, data: Dict[str, Any]) -> str:
        """Determine the appropriate index name for the data"""
        # Check data type to determine index
        event_type = data.get('event_type', '').lower()
        level = data.get('level', '').lower()
        
        # Alert data
        if event_type == 'alert' or level in ['error', 'critical'] or 'alert' in data:
            return self.index_patterns['alerts']
            
        # Audit data
        if event_type == 'audit' or 'audit' in data.get('source', '').lower():
            return self.index_patterns['audit']
            
        # Default to logs
        return self.index_patterns['logs']
        
    async def search(self, 
                    query: Dict[str, Any],
                    index: Optional[str] = None,
                    size: int = 100,
                    sort: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Search documents in Elasticsearch"""
        if not self.client:
            raise ConnectionError("Not connected to Elasticsearch")
            
        try:
            search_params = {
                'index': index or f"{self.default_index}-*",
                'body': {
                    'query': query,
                    'size': size
                }
            }
            
            if sort:
                search_params['body']['sort'] = sort
            else:
                # Default sort by timestamp desc
                search_params['body']['sort'] = [
                    {'@timestamp': {'order': 'desc'}}
                ]
                
            response = await self.client.search(**search_params)
            return response
            
        except Exception as e:
            self.logger.error("Elasticsearch search failed", error=str(e))
            raise StorageError(f"Elasticsearch search failed: {e}")
            
    async def search_logs(self,
                         text_query: Optional[str] = None,
                         filters: Optional[Dict[str, Any]] = None,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         size: int = 100) -> List[Dict[str, Any]]:
        """Search logs with common parameters"""
        
        # Build query
        must_clauses = []
        
        # Text search
        if text_query:
            must_clauses.append({
                'multi_match': {
                    'query': text_query,
                    'fields': ['message', 'description', 'title'],
                    'type': 'best_fields'
                }
            })
            
        # Time range filter
        if start_time or end_time:
            time_filter = {'range': {'@timestamp': {}}}
            if start_time:
                time_filter['range']['@timestamp']['gte'] = start_time.isoformat()
            if end_time:
                time_filter['range']['@timestamp']['lte'] = end_time.isoformat()
            must_clauses.append(time_filter)
            
        # Additional filters
        if filters:
            for field, value in filters.items():
                if isinstance(value, list):
                    must_clauses.append({'terms': {field: value}})
                else:
                    must_clauses.append({'term': {field: value}})
                    
        # Construct query
        if must_clauses:
            query = {'bool': {'must': must_clauses}}
        else:
            query = {'match_all': {}}
            
        response = await self.search(query, size=size)
        
        # Extract hits
        return [hit['_source'] for hit in response.get('hits', {}).get('hits', [])]
        
    async def get_aggregations(self,
                              agg_config: Dict[str, Any],
                              index: Optional[str] = None,
                              query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get aggregated data from Elasticsearch"""
        if not self.client:
            raise ConnectionError("Not connected to Elasticsearch")
            
        try:
            search_params = {
                'index': index or f"{self.default_index}-*",
                'body': {
                    'size': 0,  # We only want aggregations
                    'aggs': agg_config
                }
            }
            
            if query:
                search_params['body']['query'] = query
                
            response = await self.client.search(**search_params)
            return response.get('aggregations', {})
            
        except Exception as e:
            self.logger.error("Elasticsearch aggregation failed", error=str(e))
            raise StorageError(f"Elasticsearch aggregation failed: {e}")
            
    async def delete_old_data(self, older_than_days: int = 30) -> Dict[str, Any]:
        """Delete data older than specified days"""
        if not self.client:
            raise ConnectionError("Not connected to Elasticsearch")
            
        try:
            cutoff_date = datetime.now(tz=timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp() - (older_than_days * 24 * 3600)
            
            cutoff_datetime = datetime.fromtimestamp(cutoff_date, tz=timezone.utc)
            
            # Delete query
            delete_query = {
                'query': {
                    'range': {
                        '@timestamp': {
                            'lt': cutoff_datetime.isoformat()
                        }
                    }
                }
            }
            
            response = await self.client.delete_by_query(
                index=f"{self.default_index}-*",
                body=delete_query
            )
            
            self.logger.info("Deleted old documents", 
                           deleted=response.get('deleted', 0),
                           older_than_days=older_than_days)
            
            return response
            
        except Exception as e:
            self.logger.error("Failed to delete old data", error=str(e))
            raise StorageError(f"Elasticsearch delete failed: {e}")