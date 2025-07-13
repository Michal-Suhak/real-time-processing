import os
import time
import signal
import threading
from typing import Dict, Any
import structlog
import redis
from prometheus_client import start_http_server, Counter, Histogram, Gauge

from .consumers.inventory_consumer import InventoryConsumer
from .utils.kafka_client import KafkaClient, TopicConfig

# Configure structured logging
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

# Prometheus metrics
MESSAGES_PROCESSED = Counter('messages_processed_total', 'Total processed messages', ['topic', 'status'])
PROCESSING_TIME = Histogram('message_processing_seconds', 'Time spent processing messages', ['topic'])
ACTIVE_CONSUMERS = Gauge('active_consumers', 'Number of active consumers', ['consumer_type'])
ANOMALIES_DETECTED = Counter('anomalies_detected_total', 'Total anomalies detected', ['anomaly_type'])
REDIS_OPERATIONS = Counter('redis_operations_total', 'Total Redis operations', ['operation', 'status'])


class ProcessingPipelineManager:
    def __init__(self):
        self.running = False
        self.consumers = {}
        self.threads = {}
        
        # Initialize Redis connection
        self.redis_client = self._initialize_redis()
        
        # Initialize Kafka client
        self.kafka_client = KafkaClient()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _initialize_redis(self) -> redis.Redis:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("Redis connection established", url=redis_url)
            return client
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e), url=redis_url)
            return None

    def _signal_handler(self, signum, frame):
        logger.info("Received signal, shutting down", signal=signum)
        self.stop()

    def start(self):
        logger.info("Starting processing pipeline manager")
        self.running = True
        
        # Start Prometheus metrics server
        metrics_port = int(os.getenv("METRICS_PORT", "8090"))
        start_http_server(metrics_port)
        logger.info("Prometheus metrics server started", port=metrics_port)
        
        # Start consumers
        self._start_consumers()
        
        # Start health check thread
        health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        health_thread.start()
        
        # Main loop
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def _start_consumers(self):
        logger.info("Starting Kafka consumers")
        
        # Start inventory consumer
        inventory_consumer = InventoryConsumer(
            kafka_client=self.kafka_client,
            batch_size=50,
            poll_timeout=1000,
        )
        
        # Inject Redis client if available
        if self.redis_client:
            inventory_consumer.enricher.redis_client = self.redis_client
            inventory_consumer.anomaly_detector.redis_client = self.redis_client
        
        self.consumers["inventory"] = inventory_consumer
        
        # Start consumer in separate thread
        inventory_thread = threading.Thread(
            target=self._run_consumer_with_metrics,
            args=("inventory", inventory_consumer),
            daemon=True
        )
        inventory_thread.start()
        self.threads["inventory"] = inventory_thread
        
        ACTIVE_CONSUMERS.labels(consumer_type="inventory").set(1)
        
        logger.info("All consumers started")

    def _run_consumer_with_metrics(self, consumer_name: str, consumer):
        logger.info("Starting consumer thread", consumer=consumer_name)
        
        try:
            # Wrap the consumer's process_message method to add metrics
            original_process_message = consumer.process_message
            
            def process_message_with_metrics(message):
                start_time = time.time()
                topic = message.topic
                
                try:
                    result = original_process_message(message)
                    MESSAGES_PROCESSED.labels(topic=topic, status="success").inc()
                    
                    # Track anomalies
                    if result and result.get("anomaly_detected"):
                        anomaly_type = result.get("anomaly_type", "unknown")
                        ANOMALIES_DETECTED.labels(anomaly_type=anomaly_type).inc()
                    
                    return result
                    
                except Exception as e:
                    MESSAGES_PROCESSED.labels(topic=topic, status="error").inc()
                    logger.error("Message processing failed", error=str(e), topic=topic)
                    raise
                finally:
                    processing_time = time.time() - start_time
                    PROCESSING_TIME.labels(topic=topic).observe(processing_time)
            
            consumer.process_message = process_message_with_metrics
            
            # Start the consumer
            consumer.start()
            
        except Exception as e:
            logger.error("Consumer thread failed", consumer=consumer_name, error=str(e))
            ACTIVE_CONSUMERS.labels(consumer_type=consumer_name).set(0)
        finally:
            logger.info("Consumer thread stopped", consumer=consumer_name)

    def _health_check_loop(self):
        logger.info("Starting health check loop")
        
        while self.running:
            try:
                self._perform_health_checks()
                time.sleep(30)  # Health check every 30 seconds
            except Exception as e:
                logger.error("Health check failed", error=str(e))
                time.sleep(60)  # Wait longer if health check fails

    def _perform_health_checks(self):
        health_status = {
            "timestamp": time.time(),
            "kafka": self._check_kafka_health(),
            "redis": self._check_redis_health(),
            "consumers": self._check_consumer_health(),
        }
        
        # Store health status in Redis
        if self.redis_client:
            try:
                self.redis_client.setex(
                    "pipeline:health",
                    300,  # 5 minutes TTL
                    str(health_status)
                )
                REDIS_OPERATIONS.labels(operation="health_check", status="success").inc()
            except Exception as e:
                REDIS_OPERATIONS.labels(operation="health_check", status="error").inc()
                logger.warning("Failed to store health status", error=str(e))
        
        # Log unhealthy components
        unhealthy_components = [
            component for component, status in health_status.items()
            if isinstance(status, dict) and not status.get("healthy", True)
        ]
        
        if unhealthy_components:
            logger.warning("Unhealthy components detected", components=unhealthy_components)

    def _check_kafka_health(self) -> Dict[str, Any]:
        try:
            # Try to create a test consumer to check connectivity
            test_consumer = self.kafka_client.create_consumer([TopicConfig.INVENTORY])
            test_consumer.close()
            
            return {"healthy": True, "status": "connected"}
        except Exception as e:
            return {"healthy": False, "status": "disconnected", "error": str(e)}

    def _check_redis_health(self) -> Dict[str, Any]:
        if not self.redis_client:
            return {"healthy": False, "status": "not_configured"}
        
        try:
            self.redis_client.ping()
            return {"healthy": True, "status": "connected"}
        except Exception as e:
            return {"healthy": False, "status": "disconnected", "error": str(e)}

    def _check_consumer_health(self) -> Dict[str, Any]:
        consumer_status = {}
        
        for name, thread in self.threads.items():
            is_alive = thread.is_alive()
            consumer_status[name] = {
                "healthy": is_alive,
                "status": "running" if is_alive else "stopped"
            }
        
        return consumer_status

    def stop(self):
        if not self.running:
            return
        
        logger.info("Stopping processing pipeline manager")
        self.running = False
        
        # Stop all consumers
        for name, consumer in self.consumers.items():
            logger.info("Stopping consumer", consumer=name)
            try:
                consumer.stop()
                ACTIVE_CONSUMERS.labels(consumer_type=name).set(0)
            except Exception as e:
                logger.error("Error stopping consumer", consumer=name, error=str(e))
        
        # Wait for threads to finish
        for name, thread in self.threads.items():
            logger.info("Waiting for consumer thread", consumer=name)
            thread.join(timeout=10)
            if thread.is_alive():
                logger.warning("Consumer thread did not stop gracefully", consumer=name)
        
        # Close connections
        if self.kafka_client:
            self.kafka_client.close()
        
        if self.redis_client:
            self.redis_client.close()
        
        logger.info("Processing pipeline manager stopped")


def main():
    log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # Set up logging
    import logging
    logging.basicConfig(level=getattr(logging, log_level))
    
    logger.info("Starting Warehouse Processing Pipeline", log_level=log_level)
    
    # Create and start the manager
    manager = ProcessingPipelineManager()
    
    try:
        manager.start()
    except Exception as e:
        logger.error("Pipeline manager failed", error=str(e))
        raise
    finally:
        manager.stop()


if __name__ == "__main__":
    main()