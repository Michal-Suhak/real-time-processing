import abc
from typing import Dict, List, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

class BaseStorageAdapter(abc.ABC):
    """Base class for all storage adapters"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logger.bind(storage_type=self.__class__.__name__)
        
    @abc.abstractmethod
    async def connect(self) -> bool:
        """Establish connection to storage system"""
        pass
        
    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close connection to storage system"""
        pass
        
    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Check if storage system is healthy"""
        pass
        
    @abc.abstractmethod
    async def store(self, data: Dict[str, Any]) -> bool:
        """Store data in the storage system"""
        pass
        
    @abc.abstractmethod
    async def batch_store(self, data_list: List[Dict[str, Any]]) -> bool:
        """Store multiple records in batch"""
        pass

class StorageError(Exception):
    """Base exception for storage operations"""
    pass

class ConnectionError(StorageError):
    """Exception raised when storage connection fails"""
    pass

class WriteError(StorageError):
    """Exception raised when write operation fails"""
    pass