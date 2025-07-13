from typing import Dict, List, Any, Optional
from kafka.consumer.fetcher import ConsumerRecord
import structlog

from .base_consumer import BaseConsumer
from ..processors.inventory_processor import InventoryProcessor
from ..enrichers.inventory_enricher import InventoryEnricher
from ..anomaly_detection.inventory_anomaly_detector import InventoryAnomalyDetector
from ..utils.kafka_client import TopicConfig

logger = structlog.get_logger(__name__)


class InventoryConsumer(BaseConsumer):
    def __init__(self, **kwargs):
        super().__init__(
            topics=[TopicConfig.INVENTORY],
            consumer_group="inventory-processing",
            **kwargs
        )
        self.processor = InventoryProcessor()
        self.enricher = InventoryEnricher()
        self.anomaly_detector = InventoryAnomalyDetector()

    def process_message(self, message: ConsumerRecord) -> Optional[Dict[str, Any]]:
        try:
            data = message.value
            metadata = self.get_message_metadata(message)
            
            logger.info(
                "Processing inventory message",
                item_id=data.get("item_id"),
                action=data.get("action"),
                quantity=data.get("quantity"),
            )
            
            # Basic validation
            if not self._validate_inventory_message(data):
                logger.warning("Invalid inventory message", data=data)
                return None
            
            # Process the message
            processed_data = self.processor.process(data, metadata)
            
            # Enrich with additional data
            enriched_data = self.enricher.enrich(processed_data)
            
            # Check for anomalies
            anomaly_result = self.anomaly_detector.detect(enriched_data)
            if anomaly_result.get("is_anomaly"):
                self._handle_anomaly(enriched_data, anomaly_result)
            
            return enriched_data
            
        except Exception as e:
            logger.error("Failed to process inventory message", error=str(e))
            return None

    def process_batch(self, messages: List[Dict[str, Any]]):
        if not messages:
            return
            
        logger.info("Processing inventory batch", batch_size=len(messages))
        
        # Send processed messages to processed topic
        for message in messages:
            self.kafka_client.send_message(
                topic=TopicConfig.PROCESSED_INVENTORY,
                value=message,
                key=message.get("item_id"),
            )
        
        # Batch anomaly detection
        self.anomaly_detector.batch_detect(messages)
        
        logger.info("Inventory batch processed successfully", count=len(messages))

    def _validate_inventory_message(self, data: Dict[str, Any]) -> bool:
        required_fields = ["item_id", "action", "quantity", "timestamp"]
        
        for field in required_fields:
            if field not in data:
                logger.warning("Missing required field", field=field, data=data)
                return False
        
        # Validate action types
        valid_actions = ["stock_in", "stock_out", "adjustment", "transfer"]
        if data["action"] not in valid_actions:
            logger.warning("Invalid action", action=data["action"])
            return False
        
        # Validate quantity
        try:
            quantity = float(data["quantity"])
            if quantity < 0 and data["action"] in ["stock_in"]:
                logger.warning("Negative quantity for stock_in", quantity=quantity)
                return False
        except (ValueError, TypeError):
            logger.warning("Invalid quantity type", quantity=data["quantity"])
            return False
        
        return True

    def _handle_anomaly(self, data: Dict[str, Any], anomaly_result: Dict[str, Any]):
        alert_data = {
            "type": "inventory_anomaly",
            "item_id": data.get("item_id"),
            "anomaly_type": anomaly_result.get("anomaly_type"),
            "confidence": anomaly_result.get("confidence"),
            "details": anomaly_result.get("details"),
            "timestamp": data.get("timestamp"),
            "severity": anomaly_result.get("severity", "medium"),
        }
        
        # Send alert to alerts topic
        self.kafka_client.send_message(
            topic=TopicConfig.ALERTS,
            value=alert_data,
            key=f"anomaly_{data.get('item_id')}",
        )
        
        logger.warning(
            "Inventory anomaly detected",
            item_id=data.get("item_id"),
            anomaly_type=anomaly_result.get("anomaly_type"),
            confidence=anomaly_result.get("confidence"),
        )