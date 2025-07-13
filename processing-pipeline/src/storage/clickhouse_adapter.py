import asyncio
import json
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
import httpx
import structlog

from .base_storage import BaseStorageAdapter, StorageError, ConnectionError, WriteError

logger = structlog.get_logger(__name__)

class ClickHouseAdapter(BaseStorageAdapter):
    """ClickHouse adapter for historical analytics and data warehousing"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client: Optional[httpx.AsyncClient] = None
        
        # Configuration
        self.url = config.get('url', 'http://localhost:8123')
        self.username = config.get('username', 'default')
        self.password = config.get('password', '')
        self.database = config.get('database', 'warehouse_analytics')
        self.timeout = config.get('timeout', 30)
        
        # Table mappings
        self.table_mappings = {
            'raw_events': 'raw_events',
            'inventory_metrics': 'inventory_metrics',
            'daily_kpis': 'daily_kpis',
            'alert_events': 'alert_events',
            'performance_metrics': 'performance_metrics'
        }
        
    async def connect(self) -> bool:
        """Establish connection to ClickHouse"""
        try:
            # Create HTTP client with authentication
            auth = None
            if self.username:
                auth = (self.username, self.password)
                
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                auth=auth
            )
            
            # Test connection with a simple query
            response = await self.client.get(f"{self.url}/ping")
            if response.status_code != 200:
                raise ConnectionError(f"ClickHouse ping failed: {response.status_code}")
                
            # Test database access
            query = f"SELECT 1 FROM system.databases WHERE name = '{self.database}'"
            result = await self._execute_query(query)
            
            if not result or not result.strip():
                raise ConnectionError(f"Database '{self.database}' not accessible")
                
            self.logger.info("Connected to ClickHouse", 
                           url=self.url, 
                           database=self.database)
            return True
            
        except Exception as e:
            self.logger.error("Failed to connect to ClickHouse", error=str(e))
            raise ConnectionError(f"ClickHouse connection failed: {e}")
            
    async def disconnect(self) -> None:
        """Close connection to ClickHouse"""
        if self.client:
            await self.client.aclose()
            self.client = None
            self.logger.info("Disconnected from ClickHouse")
            
    async def health_check(self) -> bool:
        """Check if ClickHouse is healthy"""
        if not self.client:
            return False
            
        try:
            response = await self.client.get(f"{self.url}/ping")
            return response.status_code == 200
        except Exception as e:
            self.logger.warning("ClickHouse health check failed", error=str(e))
            return False
            
    async def store(self, data: Dict[str, Any]) -> bool:
        """Store single record in ClickHouse"""
        return await self.batch_store([data])
        
    async def batch_store(self, data_list: List[Dict[str, Any]]) -> bool:
        """Store multiple records in ClickHouse"""
        if not self.client:
            raise ConnectionError("Not connected to ClickHouse")
            
        try:
            if not data_list:
                return True
                
            # Group data by table type
            table_data = {}
            for data in data_list:
                table_name = self._get_table_name(data)
                if table_name not in table_data:
                    table_data[table_name] = []
                table_data[table_name].append(data)
                
            # Insert into each table
            for table_name, records in table_data.items():
                await self._batch_insert(table_name, records)
                
            self.logger.debug("Stored records to ClickHouse", 
                            total_records=len(data_list),
                            tables=list(table_data.keys()))
            return True
            
        except Exception as e:
            self.logger.error("Failed to store records to ClickHouse", 
                            error=str(e), count=len(data_list))
            raise WriteError(f"ClickHouse batch write failed: {e}")
            
    async def _batch_insert(self, table_name: str, records: List[Dict[str, Any]]) -> None:
        """Insert records into specific table"""
        if table_name == 'raw_events':
            await self._insert_raw_events(records)
        elif table_name == 'inventory_metrics':
            await self._insert_inventory_metrics(records)
        elif table_name == 'daily_kpis':
            await self._insert_daily_kpis(records)
        elif table_name == 'alert_events':
            await self._insert_alert_events(records)
        elif table_name == 'performance_metrics':
            await self._insert_performance_metrics(records)
        else:
            self.logger.warning("Unknown table for insertion", table=table_name)
            
    async def _insert_raw_events(self, records: List[Dict[str, Any]]) -> None:
        """Insert records into raw_events table"""
        values = []
        
        for record in records:
            # Extract and format values for raw_events table
            event_id = record.get('event_id', record.get('correlation_id', ''))
            timestamp = self._format_datetime(record.get('timestamp'))
            event_type = record.get('event_type', 'unknown')
            topic = record.get('topic', '')
            partition = record.get('partition', 0)
            offset = record.get('offset', 0)
            source = record.get('source', '')
            correlation_id = record.get('correlation_id', '')
            user_id = record.get('user_id', '')
            session_id = record.get('session_id', '')
            
            # Inventory fields
            item_id = record.get('item_id', '')
            action = record.get('action', '')
            quantity = record.get('quantity', 0)
            location_id = record.get('location_id', '')
            warehouse_zone = record.get('warehouse_zone', '')
            item_category = record.get('item_category', '')
            
            # Order fields
            order_id = record.get('order_id', '')
            order_status = record.get('order_status', '')
            customer_id = record.get('customer_id', '')
            order_value = record.get('order_value', 0.0)
            
            # Shipment fields
            shipment_id = record.get('shipment_id', '')
            carrier = record.get('carrier', '')
            tracking_number = record.get('tracking_number', '')
            destination_country = record.get('destination_country', '')
            
            # Raw data as JSON
            raw_data = json.dumps(record)
            processing_timestamp = self._format_datetime(datetime.now(tz=timezone.utc))
            
            value_tuple = (
                event_id, timestamp, event_type, topic, partition, offset,
                source, correlation_id, user_id, session_id,
                item_id, action, quantity, location_id, warehouse_zone, item_category,
                order_id, order_status, customer_id, order_value,
                shipment_id, carrier, tracking_number, destination_country,
                raw_data, processing_timestamp
            )
            values.append(value_tuple)
            
        # Build INSERT query
        query = f"""
        INSERT INTO {self.database}.raw_events (
            event_id, timestamp, event_type, topic, partition, offset,
            source, correlation_id, user_id, session_id,
            item_id, action, quantity, location_id, warehouse_zone, item_category,
            order_id, order_status, customer_id, order_value,
            shipment_id, carrier, tracking_number, destination_country,
            raw_data, processing_timestamp
        ) VALUES
        """
        
        value_strings = []
        for value_tuple in values:
            value_str = "(" + ", ".join(self._format_value(v) for v in value_tuple) + ")"
            value_strings.append(value_str)
            
        final_query = query + ", ".join(value_strings)
        await self._execute_query(final_query)
        
    async def _insert_inventory_metrics(self, records: List[Dict[str, Any]]) -> None:
        """Insert records into inventory_metrics table"""
        # This would typically be called from aggregated data
        # Implementation similar to raw_events but with aggregated fields
        pass
        
    async def _insert_alert_events(self, records: List[Dict[str, Any]]) -> None:
        """Insert records into alert_events table"""
        values = []
        
        for record in records:
            alert_id = record.get('alert_id', record.get('correlation_id', ''))
            timestamp = self._format_datetime(record.get('timestamp'))
            alert_type = record.get('alert_type', record.get('event_type', ''))
            severity = record.get('severity', 'info')
            source = record.get('source', '')
            title = record.get('title', record.get('message', ''))
            description = record.get('description', '')
            confidence_score = record.get('confidence_score', 0.0)
            affected_item_id = record.get('item_id', '')
            affected_location = record.get('location_id', '')
            warehouse_zone = record.get('warehouse_zone', '')
            resolved = 0  # Default to unresolved
            assignee = record.get('assignee', '')
            source_event_id = record.get('source_event_id', '')
            source_correlation_id = record.get('correlation_id', '')
            
            value_tuple = (
                alert_id, timestamp, alert_type, severity, source,
                title, description, confidence_score,
                affected_item_id, affected_location, warehouse_zone,
                resolved, assignee, source_event_id, source_correlation_id
            )
            values.append(value_tuple)
            
        query = f"""
        INSERT INTO {self.database}.alert_events (
            alert_id, timestamp, alert_type, severity, source,
            title, description, confidence_score,
            affected_item_id, affected_location, warehouse_zone,
            resolved, assignee, source_event_id, source_correlation_id
        ) VALUES
        """
        
        value_strings = []
        for value_tuple in values:
            value_str = "(" + ", ".join(self._format_value(v) for v in value_tuple) + ")"
            value_strings.append(value_str)
            
        final_query = query + ", ".join(value_strings)
        await self._execute_query(final_query)
        
    async def _insert_performance_metrics(self, records: List[Dict[str, Any]]) -> None:
        """Insert records into performance_metrics table"""
        values = []
        
        for record in records:
            timestamp = self._format_datetime(record.get('timestamp'))
            metric_name = record.get('metric_name', record.get('name', ''))
            metric_type = record.get('metric_type', 'gauge')
            service_name = record.get('service_name', record.get('source', ''))
            value = record.get('value', 0.0)
            count = record.get('count', 1)
            
            # Labels as JSON string
            labels = json.dumps(record.get('labels', {}))
            
            duration_ms = record.get('duration_ms')
            status_code = record.get('status_code')
            error_message = record.get('error_message', '')
            
            value_tuple = (
                timestamp, metric_name, metric_type, service_name,
                value, count, labels, duration_ms, status_code, error_message
            )
            values.append(value_tuple)
            
        query = f"""
        INSERT INTO {self.database}.performance_metrics (
            timestamp, metric_name, metric_type, service_name,
            value, count, labels, duration_ms, status_code, error_message
        ) VALUES
        """
        
        value_strings = []
        for value_tuple in values:
            value_str = "(" + ", ".join(self._format_value(v) for v in value_tuple) + ")"
            value_strings.append(value_str)
            
        final_query = query + ", ".join(value_strings)
        await self._execute_query(final_query)
        
    def _get_table_name(self, data: Dict[str, Any]) -> str:
        """Determine appropriate table for the data"""
        # Check for specific indicators
        if 'alert' in data.get('event_type', '').lower() or data.get('severity'):
            return 'alert_events'
        elif 'metric' in data.get('event_type', '').lower() or data.get('metric_name'):
            return 'performance_metrics'
        elif 'aggregated' in data.get('data_type', '').lower():
            return 'inventory_metrics'
        else:
            return 'raw_events'
            
    def _format_datetime(self, dt: Union[str, datetime, int, float, None]) -> str:
        """Format datetime for ClickHouse"""
        if dt is None:
            return "now64()"
            
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except ValueError:
                return "now64()"
        elif isinstance(dt, (int, float)):
            dt = datetime.fromtimestamp(dt, tz=timezone.utc)
            
        if isinstance(dt, datetime):
            return f"'{dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'"
        
        return "now64()"
        
    def _format_value(self, value: Any) -> str:
        """Format value for ClickHouse query"""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            # Escape single quotes
            escaped = value.replace("'", "\\'")
            return f"'{escaped}'"
        elif isinstance(value, bool):
            return "1" if value else "0"
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            # Convert to string and escape
            escaped = str(value).replace("'", "\\'")
            return f"'{escaped}'"
            
    async def _execute_query(self, query: str) -> str:
        """Execute query against ClickHouse"""
        if not self.client:
            raise ConnectionError("Not connected to ClickHouse")
            
        try:
            params = {'query': query}
            response = await self.client.post(self.url, params=params)
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            self.logger.error("ClickHouse query failed", error=str(e), query=query[:200])
            raise StorageError(f"ClickHouse query failed: {e}")
            
    async def query(self, 
                   sql: str, 
                   format: str = 'JSONEachRow') -> List[Dict[str, Any]]:
        """Execute SELECT query and return results"""
        query_with_format = f"{sql} FORMAT {format}"
        result = await self._execute_query(query_with_format)
        
        if format == 'JSONEachRow':
            # Parse each line as JSON
            results = []
            for line in result.strip().split('\n'):
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return results
        else:
            return [{'result': result}]
            
    async def get_inventory_summary(self, 
                                  start_date: datetime, 
                                  end_date: datetime) -> List[Dict[str, Any]]:
        """Get inventory summary for date range"""
        query = f"""
        SELECT 
            date,
            warehouse_zone,
            item_category,
            sum(total_transactions) as total_transactions,
            sum(inbound_quantity) as total_inbound,
            sum(outbound_quantity) as total_outbound,
            avg(success_rate) as avg_success_rate,
            sum(anomaly_count) as total_anomalies
        FROM {self.database}.inventory_metrics
        WHERE date >= '{start_date.strftime('%Y-%m-%d')}'
          AND date <= '{end_date.strftime('%Y-%m-%d')}'
        GROUP BY date, warehouse_zone, item_category
        ORDER BY date DESC, warehouse_zone, item_category
        """
        
        return await self.query(query)
        
    async def get_top_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent high-priority alerts"""
        query = f"""
        SELECT 
            alert_id,
            timestamp,
            alert_type,
            severity,
            title,
            confidence_score,
            affected_item_id,
            warehouse_zone,
            resolved
        FROM {self.database}.alert_events
        WHERE severity IN ('high', 'critical', 'error')
          AND resolved = 0
        ORDER BY timestamp DESC, confidence_score DESC
        LIMIT {limit}
        """
        
        return await self.query(query)
        
    async def get_performance_trends(self, 
                                   metric_name: str,
                                   hours: int = 24) -> List[Dict[str, Any]]:
        """Get performance trends for a metric"""
        query = f"""
        SELECT 
            toStartOfHour(timestamp) as hour,
            service_name,
            avg(value) as avg_value,
            max(value) as max_value,
            min(value) as min_value,
            count() as data_points
        FROM {self.database}.performance_metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {hours} HOUR
        GROUP BY hour, service_name
        ORDER BY hour DESC, service_name
        """
        
        return await self.query(query)