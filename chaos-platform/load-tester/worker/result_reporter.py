"""Result Reporter — buffers request results and flushes to Kafka + Redis.

Used by the standalone K8s worker process (worker_main.py).
Flushes to Kafka every 100 results or every 2 seconds, whichever comes first.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import List

from worker.request_executor import RequestResult

logger = logging.getLogger("load-tester.worker.reporter")

_FLUSH_EVERY_N = 100
_FLUSH_EVERY_SECONDS = 2.0


class ResultReporter:
    def __init__(self, kafka_producer, redis_aggregator, test_id: str, worker_id: str):
        self._kafka = kafka_producer
        self._redis = redis_aggregator
        self.test_id = test_id
        self.worker_id = worker_id
        self._buffer: List[RequestResult] = []
        self._last_flush = time.monotonic()

    async def add(self, result: RequestResult) -> None:
        self._buffer.append(result)
        if (
            len(self._buffer) >= _FLUSH_EVERY_N
            or time.monotonic() - self._last_flush >= _FLUSH_EVERY_SECONDS
        ):
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.monotonic()

        for result in batch:
            await self._kafka.send("load-test-results", asdict(result), key=self.test_id)

        # Lightweight aggregate to Redis (counts only, not full records)
        success = sum(1 for r in batch if r.success)
        errors = len(batch) - success
        latencies = [r.latency_ms for r in batch]
        avg_ms = sum(latencies) / len(latencies) if latencies else 0

        summary = {
            "worker_id": self.worker_id,
            "test_id": self.test_id,
            "batch_size": len(batch),
            "success": success,
            "errors": errors,
            "avg_latency_ms": round(avg_ms, 2),
        }
        await self._kafka.send("load-test-stats", summary, key=self.test_id)
