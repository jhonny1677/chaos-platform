"""Async Kafka producer with graceful degradation.

If Kafka is unreachable (common in dev/test), all publish calls are silently
logged and skipped — the chaos engine continues to function without Kafka.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("chaos-engine.kafka")

try:
    from aiokafka import AIOKafkaProducer as _AIOKafkaProducer
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False


class KafkaProducer:
    """Thin async wrapper around aiokafka with connection lifecycle management."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str = "chaos-events",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._producer: Optional[object] = None

    async def start(self) -> None:
        if not _KAFKA_AVAILABLE:
            logger.warning("aiokafka not available — Kafka publishing disabled")
            return
        try:
            self._producer = _AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            await self._producer.start()
            logger.info("Kafka producer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            logger.error("Failed to connect to Kafka: %s — events will be dropped", exc)
            self._producer = None

    async def send(self, event_type: str, data: dict, key: Optional[str] = None) -> bool:
        """Publish a message. Returns True on success, False on failure (non-fatal)."""
        if not self._producer:
            logger.debug("Kafka unavailable — dropping event %s", event_type)
            return False

        message = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        try:
            await self._producer.send_and_wait(self.topic, value=message, key=key)
            return True
        except Exception as exc:
            logger.error("Failed to publish Kafka event %s: %s", event_type, exc)
            return False

    async def stop(self) -> None:
        if self._producer:
            try:
                await self._producer.stop()
            except Exception:
                pass
            self._producer = None
