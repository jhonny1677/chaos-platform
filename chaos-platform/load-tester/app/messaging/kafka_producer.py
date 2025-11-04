"""Async Kafka producer with graceful degradation when broker is unavailable."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("load-tester.kafka")

try:
    from aiokafka import AIOKafkaProducer as _AIOKafkaProducer
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False


class KafkaProducer:
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: Optional[object] = None

    async def start(self) -> None:
        if not _KAFKA_AVAILABLE:
            logger.warning("aiokafka unavailable — Kafka publishing disabled")
            return
        try:
            self._producer = _AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                compression_type="lz4",
                linger_ms=5,          # small batching for throughput
                max_batch_size=65536,
            )
            await self._producer.start()
            logger.info("Kafka producer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            logger.error("Kafka connect failed: %s — events will be dropped", exc)
            self._producer = None

    async def send(self, topic: str, value: dict, key: Optional[str] = None) -> bool:
        if not self._producer:
            return False
        try:
            await self._producer.send(topic, value=value, key=key)
            from app.observability.metrics import KAFKA_MESSAGES_PRODUCED
            KAFKA_MESSAGES_PRODUCED.labels(topic=topic).inc()
            return True
        except Exception as exc:
            logger.debug("Kafka send failed (%s): %s", topic, exc)
            return False

    async def send_and_wait(self, topic: str, value: dict, key: Optional[str] = None) -> bool:
        if not self._producer:
            return False
        try:
            await self._producer.send_and_wait(topic, value=value, key=key)
            from app.observability.metrics import KAFKA_MESSAGES_PRODUCED
            KAFKA_MESSAGES_PRODUCED.labels(topic=topic).inc()
            return True
        except Exception as exc:
            logger.debug("Kafka send_and_wait failed (%s): %s", topic, exc)
            return False

    async def stop(self) -> None:
        if self._producer:
            try:
                await self._producer.stop()
            except Exception:
                pass
            self._producer = None
