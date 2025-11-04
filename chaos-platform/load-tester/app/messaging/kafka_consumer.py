"""Kafka consumer for the load-test-commands topic.

Commands that can arrive while a test is running:
  stop   — gracefully stop the test
  pause  — pause sending (workers idle but stay alive)
  resume — resume after pause
  scale  — change virtual user count: {"command": "scale", "virtual_users": 50}

Each running LoadEngine registers a callback; incoming commands are dispatched
to the engine that owns the test_id in the message.
"""

import json
import logging
from typing import Callable, Dict

logger = logging.getLogger("load-tester.kafka-consumer")

try:
    from aiokafka import AIOKafkaConsumer as _AIOKafkaConsumer
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False

_COMMANDS_TOPIC = "load-test-commands"


class CommandConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str = "load-tester"):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self._consumer = None
        self._handlers: Dict[str, Callable] = {}   # test_id → async callable
        self._running = False

    def register(self, test_id: str, handler: Callable) -> None:
        """Register a command handler for a specific test."""
        self._handlers[test_id] = handler

    def unregister(self, test_id: str) -> None:
        self._handlers.pop(test_id, None)

    async def start(self) -> None:
        if not _KAFKA_AVAILABLE:
            logger.warning("aiokafka unavailable — command consumer disabled")
            return
        try:
            self._consumer = _AIOKafkaConsumer(
                _COMMANDS_TOPIC,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="latest",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            await self._consumer.start()
            self._running = True
            logger.info("Command consumer started on topic %s", _COMMANDS_TOPIC)
        except Exception as exc:
            logger.error("Command consumer failed to start: %s", exc)

    async def consume_loop(self) -> None:
        if not self._consumer or not self._running:
            return
        try:
            async for msg in self._consumer:
                payload = msg.value
                test_id = payload.get("test_id")
                command = payload.get("command")
                handler = self._handlers.get(test_id)
                if handler and command:
                    try:
                        await handler(command, payload)
                    except Exception as exc:
                        logger.error("Command handler error for %s: %s", test_id, exc)
        except Exception as exc:
            logger.warning("Command consumer loop exited: %s", exc)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            try:
                await self._consumer.stop()
            except Exception:
                pass
            self._consumer = None
