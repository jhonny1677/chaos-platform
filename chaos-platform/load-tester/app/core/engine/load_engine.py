"""Load Engine — central orchestrator for a single load test run.

Lifecycle:
  1. start()      → create worker pool, start result collector, start ramp controller, publish config to Redis
  2. run()        → block until duration elapsed or stop event set
  3. stop()       → drain workers, flush results, persist final summary
  4. abort()      → immediate cancellation, no draining

External command handling (from Kafka consumer):
  stop   → graceful stop
  pause  → pause sending (workers idle)
  resume → resume sending
  scale  → change worker count immediately
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.engine.worker_pool import WorkerPool
from app.core.engine.result_collector import ResultCollector, LiveStats
from app.core.ramp.ramp_controller import RampController
from app.core.ramp.ramp_strategies import RampConfig
from app.observability.metrics import TESTS_RUNNING, TESTS_TOTAL
from app.observability.tracing import get_tracer

logger = logging.getLogger("load-tester.engine")
tracer = get_tracer("load-tester.engine")


@dataclass
class LoadTestConfig:
    test_id: str
    name: str
    target_url: str
    scenario_type: str
    virtual_users: int
    duration_seconds: int
    ramp_strategy: str = "instant"
    think_time_ms: int = 100
    ramp_duration_seconds: float = 60.0
    start_users: int = 1
    step_size: int = 10
    step_interval_seconds: float = 30.0
    ramp_waypoints: List = field(default_factory=list)


class LoadEngine:
    def __init__(
        self,
        config: LoadTestConfig,
        redis_aggregator,
        kafka_producer,
        db_session_factory,
        command_consumer=None,
    ):
        self.config = config
        self._redis = redis_aggregator
        self._kafka = kafka_producer
        self._db_factory = db_session_factory
        self._cmd_consumer = command_consumer

        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()

        self._result_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._pool: Optional[WorkerPool] = None
        self._collector: Optional[ResultCollector] = None
        self._ramp: Optional[RampController] = None

        self._final_stats: Optional[LiveStats] = None
        self._started_at: Optional[datetime] = None

    async def start(self) -> None:
        with tracer.start_as_current_span("load_engine.start") as span:
            span.set_attribute("test_id", self.config.test_id)
            span.set_attribute("scenario_type", self.config.scenario_type)

            self._started_at = datetime.now(timezone.utc)
            cfg = self.config

            # Publish config to Redis so K8s workers can read it
            await self._redis.store_config(cfg.test_id, asdict(cfg))
            await self._redis.set_status(cfg.test_id, "running")

            # Build ramp config
            ramp_cfg = RampConfig(
                start_users=cfg.start_users,
                target_users=cfg.virtual_users,
                ramp_duration_seconds=cfg.ramp_duration_seconds,
                step_size=cfg.step_size,
                step_interval_seconds=cfg.step_interval_seconds,
                waypoints=cfg.ramp_waypoints,
            )

            # Worker pool
            self._pool = WorkerPool(
                test_id=cfg.test_id,
                target_url=cfg.target_url,
                result_queue=self._result_queue,
                think_time_ms=cfg.think_time_ms,
                stop_event=self._stop_event,
                pause_event=self._pause_event,
            )
            await self._pool.start(initial_workers=cfg.start_users)

            # Result collector
            self._collector = ResultCollector(
                test_id=cfg.test_id,
                queue=self._result_queue,
                redis_aggregator=self._redis,
                kafka_producer=self._kafka,
                db_session_factory=self._db_factory,
                stats_callback=self._on_stats,
            )
            await self._collector.start()

            # Ramp controller
            self._ramp = RampController(
                strategy_name=cfg.ramp_strategy,
                ramp_config=ramp_cfg,
                adjust_workers_callback=self._pool.set_target,
            )
            await self._ramp.start()

            # Register command handler
            if self._cmd_consumer:
                self._cmd_consumer.register(cfg.test_id, self._handle_command)

            TESTS_RUNNING.inc()
            logger.info(
                "Load engine started: test_id=%s scenario=%s vu=%d duration=%ds",
                cfg.test_id, cfg.scenario_type, cfg.virtual_users, cfg.duration_seconds,
                extra={"test_id": cfg.test_id},
            )

    async def run(self) -> LiveStats:
        """Block until the test duration elapses or stop() is called externally."""
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self.config.duration_seconds,
            )
        except asyncio.TimeoutError:
            pass  # normal completion — duration elapsed

        self._final_stats = await self.stop()
        return self._final_stats

    async def stop(self, reason: str = "completed") -> LiveStats:
        self._stop_event.set()
        await self._redis.set_status(self.config.test_id, "stopping")

        if self._ramp:
            await self._ramp.stop()
        if self._pool:
            await self._pool.stop()
        if self._collector:
            self._final_stats = await self._collector.stop()

        if self._cmd_consumer:
            self._cmd_consumer.unregister(self.config.test_id)

        TESTS_RUNNING.dec()
        status = "completed" if reason == "completed" else reason
        TESTS_TOTAL.labels(scenario_type=self.config.scenario_type, status=status).inc()

        await self._redis.set_status(self.config.test_id, "stopped")
        await self._redis.cleanup(self.config.test_id)

        logger.info(
            "Load engine stopped: test_id=%s total_requests=%d",
            self.config.test_id,
            self._final_stats.total_requests if self._final_stats else 0,
            extra={"test_id": self.config.test_id},
        )
        return self._final_stats

    async def abort(self) -> None:
        """Emergency abort — cancel everything immediately."""
        self._stop_event.set()
        if self._ramp:
            await self._ramp.stop()
        if self._pool:
            await self._pool.stop()
        if self._collector:
            self._collector._running = False
        TESTS_RUNNING.dec()
        await self._redis.set_status(self.config.test_id, "aborted")
        logger.warning("Load engine ABORTED: test_id=%s", self.config.test_id,
                      extra={"test_id": self.config.test_id})

    def active_workers(self) -> int:
        return self._pool.active_count() if self._pool else 0

    async def _on_stats(self, stats: LiveStats) -> None:
        """Called by ResultCollector every second with current stats."""
        stats.active_workers = self.active_workers()
        await self._kafka.send("load-test-stats", asdict(stats), key=self.config.test_id)

    async def _handle_command(self, command: str, payload: Dict[str, Any]) -> None:
        """Receives commands from Kafka load-test-commands topic."""
        logger.info("Received command %r for test %s", command, self.config.test_id,
                   extra={"test_id": self.config.test_id})
        if command == "stop":
            await self.stop(reason="stopped_by_command")
        elif command == "pause":
            self._pool.pause()
            await self._redis.set_status(self.config.test_id, "paused")
        elif command == "resume":
            self._pool.resume()
            await self._redis.set_status(self.config.test_id, "running")
        elif command == "scale":
            target_vu = int(payload.get("virtual_users", self.config.virtual_users))
            self._pool.set_target(target_vu)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()
