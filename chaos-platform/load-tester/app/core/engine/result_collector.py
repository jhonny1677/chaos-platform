"""Result Collector — consumes from asyncio Queue, computes live stats, publishes to Redis/Kafka.

Stats cycle (every second):
  1. Drain queue into buffer
  2. Calculate p50/p95/p99 from this second's latencies
  3. Publish to Redis (TTL 60s) and pub/sub channel
  4. Persist snapshot to DB

Kafka batch (every 5 seconds):
  - Publish a batch summary to load-test-stats topic
  - Individual request records are published by workers to load-test-results
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("load-tester.result-collector")

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


@dataclass
class RequestResult:
    test_id: str
    worker_id: str
    timestamp: str
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class LiveStats:
    test_id: str
    timestamp: str
    elapsed_seconds: float
    active_workers: int
    requests_this_second: int
    total_requests: int
    success_count: int
    error_count: int
    success_rate: float
    error_rate: float
    current_rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    avg_ms: float
    anomaly: Optional[str] = None


def _percentiles(latencies: List[float]) -> tuple:
    if not latencies:
        return 0.0, 0.0, 0.0, 0.0
    if _HAS_NUMPY:
        arr = np.array(latencies)
        return (
            float(np.percentile(arr, 50)),
            float(np.percentile(arr, 95)),
            float(np.percentile(arr, 99)),
            float(np.mean(arr)),
        )
    s = sorted(latencies)
    n = len(s)
    def p(pct): return s[min(int(n * pct / 100), n - 1)]
    return p(50), p(95), p(99), sum(s) / n


class ResultCollector:
    def __init__(
        self,
        test_id: str,
        queue: asyncio.Queue,
        redis_aggregator,
        kafka_producer,
        db_session_factory,
        stats_callback=None,    # optional async callable(LiveStats)
    ):
        self.test_id = test_id
        self._queue = queue
        self._redis = redis_aggregator
        self._kafka = kafka_producer
        self._db_factory = db_session_factory
        self._stats_callback = stats_callback

        self._total = 0
        self._success = 0
        self._errors = 0
        self._start_time = time.monotonic()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Per-second window
        self._window_results: List[RequestResult] = []
        self._window_start = time.monotonic()

        # For anomaly detection
        self._baseline_error_rate: Optional[float] = None
        self._baseline_p99: Optional[float] = None
        self._kafka_batch: List[RequestResult] = []
        self._last_kafka_flush = time.monotonic()

    async def start(self) -> None:
        self._running = True
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(self._collect_loop(), name="result-collector")
        logger.info("Result collector started for test %s", self.test_id)

    async def stop(self) -> LiveStats:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return await self._finalize()

    async def _collect_loop(self) -> None:
        while self._running:
            # Drain queue with a 1-second deadline
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                try:
                    result = self._queue.get_nowait()
                    self._ingest(result)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.01)

            await self._flush_window()

    def _ingest(self, result: RequestResult) -> None:
        self._total += 1
        if result.success:
            self._success += 1
        else:
            self._errors += 1
        self._window_results.append(result)
        self._kafka_batch.append(result)

        from app.observability.metrics import REQUESTS_TOTAL, REQUEST_LATENCY
        status_label = "success" if result.success else ("timeout" if result.error and "timeout" in result.error.lower() else "error")
        REQUESTS_TOTAL.labels(endpoint=result.endpoint, method=result.method, status=status_label).inc()
        REQUEST_LATENCY.labels(endpoint=result.endpoint).observe(result.latency_ms)

    async def _flush_window(self) -> None:
        now = time.monotonic()
        window = self._window_results.copy()
        self._window_results.clear()

        elapsed = now - self._start_time
        latencies = [r.latency_ms for r in window]
        p50, p95, p99, avg = _percentiles(latencies)
        rps_window = len(window)
        error_rate = (self._errors / self._total * 100) if self._total else 0.0
        success_rate = 100.0 - error_rate

        anomaly = self._detect_anomaly(error_rate, p99)

        stats = LiveStats(
            test_id=self.test_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=round(elapsed, 1),
            active_workers=0,  # updated by engine
            requests_this_second=rps_window,
            total_requests=self._total,
            success_count=self._success,
            error_count=self._errors,
            success_rate=round(success_rate, 2),
            error_rate=round(error_rate, 2),
            current_rps=float(rps_window),
            p50_ms=round(p50, 2),
            p95_ms=round(p95, 2),
            p99_ms=round(p99, 2),
            avg_ms=round(avg, 2),
            anomaly=anomaly,
        )

        from app.observability.metrics import CURRENT_RPS, ERROR_RATE
        CURRENT_RPS.set(rps_window)
        ERROR_RATE.set(error_rate)

        await self._redis.publish_stats(self.test_id, asdict(stats))
        await self._persist_snapshot(stats)

        if self._stats_callback:
            try:
                await self._stats_callback(stats)
            except Exception:
                pass

        # Kafka batch every 5 seconds
        if now - self._last_kafka_flush >= 5.0 and self._kafka_batch:
            await self._flush_kafka_batch()
            self._last_kafka_flush = now

        if anomaly:
            logger.warning(
                "Anomaly detected for test %s: %s (error_rate=%.1f%%, p99=%.0fms)",
                self.test_id, anomaly, error_rate, p99,
                extra={"test_id": self.test_id},
            )

    def _detect_anomaly(self, error_rate: float, p99: float) -> Optional[str]:
        if self._total < 10:
            return None
        # Establish baseline from first 10 seconds
        if self._baseline_error_rate is None and self._total >= 20:
            self._baseline_error_rate = error_rate
            self._baseline_p99 = p99
            return None
        if self._baseline_error_rate is not None:
            if error_rate > self._baseline_error_rate + 10:
                return f"error_rate_spike: {error_rate:.1f}% (baseline {self._baseline_error_rate:.1f}%)"
            if self._baseline_p99 and p99 > self._baseline_p99 * 2:
                return f"latency_degradation: p99={p99:.0f}ms (baseline {self._baseline_p99:.0f}ms)"
        return None

    async def _flush_kafka_batch(self) -> None:
        batch = self._kafka_batch.copy()
        self._kafka_batch.clear()
        for r in batch:
            await self._kafka.send("load-test-results", asdict(r), key=self.test_id)

    async def _persist_snapshot(self, stats: LiveStats) -> None:
        try:
            async with self._db_factory() as session:
                from app.database.repositories.result_repo import ResultRepository
                repo = ResultRepository(session)
                await repo.save_snapshot(
                    test_id=stats.test_id,
                    elapsed_seconds=stats.elapsed_seconds,
                    active_workers=stats.active_workers,
                    requests_this_second=stats.requests_this_second,
                    total_requests=stats.total_requests,
                    success_count=stats.success_count,
                    error_count=stats.error_count,
                    success_rate=stats.success_rate,
                    error_rate=stats.error_rate,
                    current_rps=stats.current_rps,
                    p50_ms=stats.p50_ms,
                    p95_ms=stats.p95_ms,
                    p99_ms=stats.p99_ms,
                    avg_ms=stats.avg_ms,
                )
        except Exception as exc:
            logger.debug("Snapshot persist failed: %s", exc)

    async def _finalize(self) -> LiveStats:
        """Drain remaining queue and compute final aggregate stats."""
        while not self._queue.empty():
            try:
                self._ingest(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        all_results: List[RequestResult] = []
        # We don't store individual results in memory for long tests, so compute from counters
        elapsed = time.monotonic() - self._start_time
        error_rate = (self._errors / self._total * 100) if self._total else 0.0

        return LiveStats(
            test_id=self.test_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=round(elapsed, 1),
            active_workers=0,
            requests_this_second=0,
            total_requests=self._total,
            success_count=self._success,
            error_count=self._errors,
            success_rate=round(100.0 - error_rate, 2),
            error_rate=round(error_rate, 2),
            current_rps=round(self._total / elapsed, 2) if elapsed > 0 else 0.0,
            p50_ms=0.0, p95_ms=0.0, p99_ms=0.0, avg_ms=0.0,
        )
