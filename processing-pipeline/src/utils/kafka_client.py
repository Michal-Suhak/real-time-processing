import json
import logging
from typing import Dict, List, Optional, Callable, Any
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import structlog

logger = structlog.get_logger(__name__)


class KafkaClient:
    def __init__(
        self,
        bootstrap_servers: str = "kafka:9092",
        consumer_group: str = "warehouse-processing",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.consumer_group = consumer_group
        self.consumer: Optional[KafkaConsumer] = None
        self.producer: Optional[KafkaProducer] = None

    def create_consumer(
        self,
        topics: List[str],
        auto_offset_reset: str = "latest",
        enable_auto_commit: bool = True,
        value_deserializer: Optional[Callable] = None,
    ) -> KafkaConsumer:
        if value_deserializer is None:
            value_deserializer = lambda x: json.loads(x.decode("utf-8"))

        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.consumer_group,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=enable_auto_commit,
            value_deserializer=value_deserializer,
            key_deserializer=lambda x: x.decode("utf-8") if x else None,
            consumer_timeout_ms=1000,
        )
        
        logger.info(
            "Created Kafka consumer",
            topics=topics,
            group_id=self.consumer_group,
            auto_offset_reset=auto_offset_reset,
        )
        
        return self.consumer

    def create_producer(
        self,
        value_serializer: Optional[Callable] = None,
        key_serializer: Optional[Callable] = None,
    ) -> KafkaProducer:
        if value_serializer is None:
            value_serializer = lambda x: json.dumps(x).encode("utf-8")
        if key_serializer is None:
            key_serializer = lambda x: x.encode("utf-8") if x else None

        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=value_serializer,
            key_serializer=key_serializer,
            acks="all",
            retries=3,
            retry_backoff_ms=100,
        )
        
        logger.info("Created Kafka producer", bootstrap_servers=self.bootstrap_servers)
        
        return self.producer

    def send_message(
        self,
        topic: str,
        value: Any,
        key: Optional[str] = None,
        partition: Optional[int] = None,
    ) -> bool:
        if not self.producer:
            self.create_producer()

        try:
            future = self.producer.send(
                topic=topic,
                value=value,
                key=key,
                partition=partition,
            )
            
            record_metadata = future.get(timeout=10)
            
            logger.info(
                "Message sent successfully",
                topic=topic,
                partition=record_metadata.partition,
                offset=record_metadata.offset,
            )
            
            return True
            
        except KafkaError as e:
            logger.error("Failed to send message", topic=topic, error=str(e))
            return False

    def close(self):
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer closed")
        
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Kafka producer closed")


class TopicConfig:
    INVENTORY = "warehouse.inventory"
    ORDERS = "warehouse.orders"
    SHIPMENTS = "warehouse.shipments"
    ALERTS = "warehouse.alerts"
    AUDIT = "warehouse.audit"
    METRICS = "warehouse.metrics"
    
    PROCESSED_INVENTORY = "warehouse.processed.inventory"
    PROCESSED_ORDERS = "warehouse.processed.orders"
    PROCESSED_SHIPMENTS = "warehouse.processed.shipments"
    AGGREGATED_METRICS = "warehouse.aggregated.metrics"

    @classmethod
    def get_all_input_topics(cls) -> List[str]:
        return [
            cls.INVENTORY,
            cls.ORDERS,
            cls.SHIPMENTS,
            cls.ALERTS,
            cls.AUDIT,
            cls.METRICS,
        ]

    @classmethod
    def get_processing_topics(cls) -> List[str]:
        return [
            cls.PROCESSED_INVENTORY,
            cls.PROCESSED_ORDERS,
            cls.PROCESSED_SHIPMENTS,
            cls.AGGREGATED_METRICS,
        ]