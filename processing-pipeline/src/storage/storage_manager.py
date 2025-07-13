import asyncio
from typing import Dict, List, Any, Optional, Set
import structlog

from .base_storage import BaseStorageAdapter, StorageError
from .influxdb_adapter import InfluxDBAdapter
from .elasticsearch_adapter import ElasticsearchAdapter
from .clickhouse_adapter import ClickHouseAdapter

logger = structlog.get_logger(__name__)

class StorageManager:
    """Manages multiple storage adapters and handles data routing"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adapters: Dict[str, BaseStorageAdapter] = {}
        self.logger = logger.bind(component="storage_manager")
        
        # Data routing configuration
        self.routing_rules = {
            'metrics': ['influxdb'],
            'logs': ['elasticsearch'],
            'alerts': ['elasticsearch', 'clickhouse'],
            'events': ['clickhouse'],
            'aggregated': ['clickhouse'],
            'performance': ['influxdb', 'clickhouse']
        }
        
        # Initialize adapters
        self._initialize_adapters()
        
    def _initialize_adapters(self):
        """Initialize storage adapters based on configuration"""
        
        # InfluxDB for time-series metrics
        if 'influxdb' in self.config:
            try:
                self.adapters['influxdb'] = InfluxDBAdapter(self.config['influxdb'])
                self.logger.info("Initialized InfluxDB adapter")
            except Exception as e:
                self.logger.error("Failed to initialize InfluxDB adapter", error=str(e))
                
        # Elasticsearch for log search
        if 'elasticsearch' in self.config:
            try:
                self.adapters['elasticsearch'] = ElasticsearchAdapter(self.config['elasticsearch'])
                self.logger.info("Initialized Elasticsearch adapter")
            except Exception as e:
                self.logger.error("Failed to initialize Elasticsearch adapter", error=str(e))
                
        # ClickHouse for data warehouse
        if 'clickhouse' in self.config:
            try:
                self.adapters['clickhouse'] = ClickHouseAdapter(self.config['clickhouse'])
                self.logger.info("Initialized ClickHouse adapter")
            except Exception as e:
                self.logger.error("Failed to initialize ClickHouse adapter", error=str(e))
                
    async def connect_all(self) -> Dict[str, bool]:
        """Connect to all configured storage systems"""
        results = {}
        
        for name, adapter in self.adapters.items():
            try:
                success = await adapter.connect()
                results[name] = success
                if success:
                    self.logger.info("Connected to storage", storage=name)
                else:
                    self.logger.error("Failed to connect to storage", storage=name)
            except Exception as e:
                results[name] = False
                self.logger.error("Connection error", storage=name, error=str(e))
                
        return results
        
    async def disconnect_all(self) -> None:
        """Disconnect from all storage systems"""
        tasks = []
        for name, adapter in self.adapters.items():
            task = asyncio.create_task(adapter.disconnect())
            tasks.append(task)
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.logger.info("Disconnected from all storage systems")
        
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all storage systems"""
        results = {}
        
        tasks = []
        for name, adapter in self.adapters.items():
            task = asyncio.create_task(self._health_check_adapter(name, adapter))
            tasks.append(task)
            
        if tasks:
            health_results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, (name, _) in enumerate(self.adapters.items()):
                result = health_results[i]
                if isinstance(result, Exception):
                    results[name] = False
                    self.logger.warning("Health check failed", storage=name, error=str(result))
                else:
                    results[name] = result
                    
        return results
        
    async def _health_check_adapter(self, name: str, adapter: BaseStorageAdapter) -> bool:
        """Health check for individual adapter"""
        try:
            return await adapter.health_check()
        except Exception as e:
            self.logger.warning("Health check error", storage=name, error=str(e))
            return False
            
    async def store_data(self, data: Dict[str, Any], data_type: Optional[str] = None) -> Dict[str, bool]:
        """Store data to appropriate storage systems based on data type"""
        # Determine data type if not provided
        if not data_type:
            data_type = self._infer_data_type(data)
            
        # Get target adapters for this data type
        target_adapters = self._get_target_adapters(data_type)
        
        if not target_adapters:
            self.logger.warning("No storage adapters configured for data type", 
                              data_type=data_type)
            return {}
            
        # Store data in parallel to all target adapters
        results = {}
        tasks = []
        
        for adapter_name in target_adapters:
            if adapter_name in self.adapters:
                task = asyncio.create_task(
                    self._store_to_adapter(adapter_name, data)
                )
                tasks.append((adapter_name, task))
            else:
                results[adapter_name] = False
                self.logger.warning("Adapter not available", 
                                  adapter=adapter_name, 
                                  data_type=data_type)
                
        # Wait for all storage operations
        for adapter_name, task in tasks:
            try:
                success = await task
                results[adapter_name] = success
            except Exception as e:
                results[adapter_name] = False
                self.logger.error("Storage operation failed", 
                                adapter=adapter_name, 
                                error=str(e))
                
        return results
        
    async def batch_store_data(self, 
                              data_list: List[Dict[str, Any]], 
                              data_type: Optional[str] = None) -> Dict[str, bool]:
        """Store multiple data records in batch"""
        if not data_list:
            return {}
            
        # Group data by type if not specified
        if data_type:
            # All data is the same type
            return await self._batch_store_by_type(data_list, data_type)
        else:
            # Group by inferred type
            type_groups = {}
            for data in data_list:
                inferred_type = self._infer_data_type(data)
                if inferred_type not in type_groups:
                    type_groups[inferred_type] = []
                type_groups[inferred_type].append(data)
                
            # Store each group
            all_results = {}
            for group_type, group_data in type_groups.items():
                group_results = await self._batch_store_by_type(group_data, group_type)
                # Merge results
                for adapter, success in group_results.items():
                    if adapter not in all_results:
                        all_results[adapter] = []
                    all_results[adapter].append(success)
                    
            # Convert lists to overall success status
            final_results = {}
            for adapter, success_list in all_results.items():
                final_results[adapter] = all(success_list)
                
            return final_results
            
    async def _batch_store_by_type(self, 
                                  data_list: List[Dict[str, Any]], 
                                  data_type: str) -> Dict[str, bool]:
        """Store batch of data of the same type"""
        target_adapters = self._get_target_adapters(data_type)
        
        if not target_adapters:
            return {}
            
        results = {}
        tasks = []
        
        for adapter_name in target_adapters:
            if adapter_name in self.adapters:
                task = asyncio.create_task(
                    self._batch_store_to_adapter(adapter_name, data_list)
                )
                tasks.append((adapter_name, task))
            else:
                results[adapter_name] = False
                
        for adapter_name, task in tasks:
            try:
                success = await task
                results[adapter_name] = success
            except Exception as e:
                results[adapter_name] = False
                self.logger.error("Batch storage operation failed", 
                                adapter=adapter_name, 
                                error=str(e),
                                count=len(data_list))
                
        return results
        
    async def _store_to_adapter(self, adapter_name: str, data: Dict[str, Any]) -> bool:
        """Store data to specific adapter"""
        adapter = self.adapters[adapter_name]
        try:
            return await adapter.store(data)
        except Exception as e:
            self.logger.error("Adapter storage failed", 
                            adapter=adapter_name, 
                            error=str(e))
            return False
            
    async def _batch_store_to_adapter(self, 
                                     adapter_name: str, 
                                     data_list: List[Dict[str, Any]]) -> bool:
        """Batch store data to specific adapter"""
        adapter = self.adapters[adapter_name]
        try:
            return await adapter.batch_store(data_list)
        except Exception as e:
            self.logger.error("Adapter batch storage failed", 
                            adapter=adapter_name, 
                            error=str(e),
                            count=len(data_list))
            return False
            
    def _infer_data_type(self, data: Dict[str, Any]) -> str:
        """Infer data type from data content"""
        # Check for specific indicators
        if 'metric_name' in data or 'measurement' in data:
            return 'metrics'
        elif 'alert' in data.get('event_type', '').lower() or data.get('severity'):
            return 'alerts'
        elif 'aggregated' in data.get('data_type', '').lower():
            return 'aggregated'
        elif 'performance' in data.get('source', '').lower():
            return 'performance'
        elif data.get('level') or data.get('message'):
            return 'logs'
        else:
            return 'events'
            
    def _get_target_adapters(self, data_type: str) -> List[str]:
        """Get list of target adapters for data type"""
        return self.routing_rules.get(data_type, ['clickhouse'])  # Default to clickhouse
        
    def get_adapter(self, adapter_name: str) -> Optional[BaseStorageAdapter]:
        """Get specific adapter instance"""
        return self.adapters.get(adapter_name)
        
    def list_adapters(self) -> List[str]:
        """List available adapter names"""
        return list(self.adapters.keys())
        
    def is_adapter_available(self, adapter_name: str) -> bool:
        """Check if adapter is available and connected"""
        return adapter_name in self.adapters
        
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get statistics from all storage systems"""
        stats = {
            'adapters': {},
            'health': await self.health_check_all(),
            'routing_rules': self.routing_rules
        }
        
        # Get adapter-specific stats
        for name, adapter in self.adapters.items():
            try:
                if hasattr(adapter, 'get_stats'):
                    adapter_stats = await adapter.get_stats()
                    stats['adapters'][name] = adapter_stats
                else:
                    stats['adapters'][name] = {'status': 'available'}
            except Exception as e:
                stats['adapters'][name] = {'status': 'error', 'error': str(e)}
                
        return stats