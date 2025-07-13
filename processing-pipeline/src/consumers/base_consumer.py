import abc
import signal
import time
from typing import Dict, List, Any, Optional
from kafka import KafkaConsumer
from kafka.consumer.fetcher import ConsumerRecord
import structlog

from ..utils.kafka_client import KafkaClient

logger = structlog.get_logger(__name__)


class BaseConsumer(abc.ABC):
    def __init__(
        self,
        topics: List[str],
        consumer_group: str,
        kafka_client: Optional[KafkaClient] = None,
        batch_size: int = 100,
        poll_timeout: int = 1000,
    ):
        self.topics = topics
        self.consumer_group = consumer_group
        self.kafka_client = kafka_client or KafkaClient(consumer_group=consumer_group)
        self.batch_size = batch_size
        self.poll_timeout = poll_timeout
        self.consumer: Optional[KafkaConsumer] = None
        self.running = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info("Received signal, shutting down gracefully", signal=signum)
        self.stop()

    def start(self):
        logger.info(
            "Starting consumer",
            topics=self.topics,
            consumer_group=self.consumer_group,
        )
        
        self.consumer = self.kafka_client.create_consumer(
            topics=self.topics,
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )
        
        self.running = True
        self._consume_loop()

    def stop(self):
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("Consumer stopped")

    def _consume_loop(self):
        batch: List[ConsumerRecord] = []
        
        while self.running:
            try:
                message_pack = self.consumer.poll(timeout_ms=self.poll_timeout)
                
                for topic_partition, messages in message_pack.items():
                    for message in messages:
                        batch.append(message)
                        
                        if len(batch) >= self.batch_size:
                            self._process_batch(batch)
                            self._commit_offsets(batch)
                            batch.clear()
                
                if batch:
                    self._process_batch(batch)
                    self._commit_offsets(batch)
                    batch.clear()
                    
            except Exception as e:
                logger.error("Error in consume loop", error=str(e))
                time.sleep(1)

    def _process_batch(self, batch: List[ConsumerRecord]):
        processed_messages = []
        
        for message in batch:
            try:
                processed_message = self.process_message(message)
                if processed_message:
                    processed_messages.append(processed_message)
                    
            except Exception as e:
                logger.error(
                    "Error processing message",
                    topic=message.topic,
                    partition=message.partition,
                    offset=message.offset,
                    error=str(e),
                )
        
        if processed_messages:
            self.process_batch(processed_messages)

    def _commit_offsets(self, batch: List[ConsumerRecord]):
        try:
            self.consumer.commit()
            logger.debug("Committed offsets", batch_size=len(batch))
        except Exception as e:
            logger.error("Failed to commit offsets", error=str(e))

    @abc.abstractmethod
    def process_message(self, message: ConsumerRecord) -> Optional[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def process_batch(self, messages: List[Dict[str, Any]]):
        pass

    def get_message_metadata(self, message: ConsumerRecord) -> Dict[str, Any]:
        return {
            "topic": message.topic,
            "partition": message.partition,
            "offset": message.offset,
            "timestamp": message.timestamp,
            "key": message.key,
        }