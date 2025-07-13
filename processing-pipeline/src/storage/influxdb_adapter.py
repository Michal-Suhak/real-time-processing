import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import structlog

from .base_storage import BaseStorageAdapter, StorageError, ConnectionError, WriteError

logger = structlog.get_logger(__name__)

class InfluxDBAdapter(BaseStorageAdapter):
    """InfluxDB adapter for time-series metrics storage"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client: Optional[InfluxDBClient] = None
        self.write_api = None
        
        # Configuration
        self.url = config.get('url', 'http://localhost:8086')
        self.token = config.get('token')
        self.org = config.get('org', 'warehouse')
        self.bucket = config.get('bucket', 'warehouse_metrics')
        
        if not self.token:
            raise ValueError("InfluxDB token is required")
            
    async def connect(self) -> bool:
        """Establish connection to InfluxDB"""
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )
            
            # Test connection
            health = self.client.health()
            if health.status != "pass":
                raise ConnectionError(f"InfluxDB health check failed: {health.message}")
                
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            
            self.logger.info("Connected to InfluxDB", url=self.url, org=self.org)
            return True
            
        except Exception as e:
            self.logger.error("Failed to connect to InfluxDB", error=str(e))
            raise ConnectionError(f"InfluxDB connection failed: {e}")
            
    async def disconnect(self) -> None:
        """Close connection to InfluxDB"""
        if self.client:
            self.client.close()
            self.client = None
            self.write_api = None
            self.logger.info("Disconnected from InfluxDB")
            
    async def health_check(self) -> bool:
        """Check if InfluxDB is healthy"""
        if not self.client:
            return False
            
        try:
            health = self.client.health()
            return health.status == "pass"
        except Exception as e:
            self.logger.warning("InfluxDB health check failed", error=str(e))
            return False
            
    async def store(self, data: Dict[str, Any]) -> bool:
        """Store single metric point in InfluxDB"""
        return await self.batch_store([data])
        
    async def batch_store(self, data_list: List[Dict[str, Any]]) -> bool:
        """Store multiple metric points in InfluxDB"""
        if not self.write_api:
            raise ConnectionError("Not connected to InfluxDB")
            
        try:
            points = []
            
            for data in data_list:
                point = self._create_point(data)
                if point:
                    points.append(point)
                    
            if points:
                self.write_api.write(bucket=self.bucket, record=points)
                self.logger.debug("Stored metrics to InfluxDB", count=len(points))
                
            return True
            
        except Exception as e:
            self.logger.error("Failed to store metrics to InfluxDB", error=str(e), count=len(data_list))
            raise WriteError(f"InfluxDB write failed: {e}")
            
    def _create_point(self, data: Dict[str, Any]) -> Optional[Point]:
        """Create InfluxDB point from data"""
        try:
            # Extract measurement name
            measurement = data.get('measurement')
            if not measurement:
                # Try to infer from event type or metric name
                measurement = data.get('event_type', data.get('metric_name', 'warehouse_metric'))
                
            # Create point
            point = Point(measurement)
            
            # Add timestamp
            timestamp = data.get('timestamp')
            if timestamp:
                if isinstance(timestamp, str):
                    # Parse ISO format timestamp
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                elif isinstance(timestamp, (int, float)):
                    # Unix timestamp
                    timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                point.time(timestamp)
            else:
                point.time(datetime.now(tz=timezone.utc))
                
            # Add tags (indexed dimensions)
            tags = data.get('tags', {})
            for key, value in tags.items():
                if value is not None:
                    point.tag(key, str(value))
                    
            # Add common tags from data
            tag_fields = ['event_type', 'topic', 'source', 'warehouse_zone', 'location_id', 
                         'item_category', 'action', 'severity', 'alert_type']
            for field in tag_fields:
                if field in data and data[field] is not None:
                    point.tag(field, str(data[field]))
                    
            # Add fields (actual values)
            fields = data.get('fields', {})
            for key, value in fields.items():
                if value is not None:
                    point.field(key, value)
                    
            # Add common fields from data
            field_mappings = {
                'quantity': 'quantity',
                'processing_time_ms': 'processing_time_ms',
                'anomaly_score': 'anomaly_score',
                'confidence_score': 'confidence_score',
                'value': 'value',
                'count': 'count',
                'duration_ms': 'duration_ms',
                'error_count': 'error_count',
                'success_rate': 'success_rate',
                'throughput': 'throughput',
                'latency_p95': 'latency_p95',
                'latency_p99': 'latency_p99'
            }
            
            for data_key, field_key in field_mappings.items():
                if data_key in data and data[data_key] is not None:
                    try:
                        # Convert to appropriate numeric type
                        value = data[data_key]
                        if isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                            value = float(value) if '.' in value else int(value)
                        point.field(field_key, value)
                    except (ValueError, TypeError):
                        self.logger.warning("Failed to convert field value", 
                                          field=data_key, value=data[data_key])
                        
            # Ensure at least one field exists
            if not any(point._fields):
                # Add a default field if none exist
                point.field('event_count', 1)
                
            return point
            
        except Exception as e:
            self.logger.warning("Failed to create InfluxDB point", error=str(e), data=data)
            return None
            
    async def query_metrics(self, 
                          measurement: str, 
                          start_time: datetime, 
                          end_time: datetime,
                          filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Query metrics from InfluxDB"""
        if not self.client:
            raise ConnectionError("Not connected to InfluxDB")
            
        try:
            query_api = self.client.query_api()
            
            # Build Flux query
            flux_query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r._measurement == "{measurement}")
            '''
            
            # Add filters
            if filters:
                for key, value in filters.items():
                    flux_query += f'\n|> filter(fn: (r) => r.{key} == "{value}")'
                    
            result = query_api.query(flux_query)
            
            # Convert to list of dictionaries
            data = []
            for table in result:
                for record in table.records:
                    data.append({
                        'time': record.get_time(),
                        'measurement': record.get_measurement(),
                        'field': record.get_field(),
                        'value': record.get_value(),
                        **{k: v for k, v in record.values.items() if k.startswith('_') is False}
                    })
                    
            return data
            
        except Exception as e:
            self.logger.error("Failed to query InfluxDB", error=str(e))
            raise StorageError(f"InfluxDB query failed: {e}")
            
    async def get_latest_metrics(self, measurement: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get latest metrics for a measurement"""
        end_time = datetime.now(tz=timezone.utc)
        start_time = end_time.replace(hour=end_time.hour - 1)  # Last hour
        
        return await self.query_metrics(measurement, start_time, end_time)