"""Scenario Runner — wires together the LoadEngine with a scenario module.

Usage:
    runner = ScenarioRunner(config, redis, kafka, db_factory, cmd_consumer)
    result = await runner.run()
"""

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.engine.load_engine import LoadEngine, LoadTestConfig
from app.core.scenarios.scenarios import smoke_test, stress_test, spike_test, soak_test

logger = logging.getLogger("load-tester.scenario-runner")

_RUNNERS = {
    "smoke":  smoke_test.run,
    "stress": stress_test.run,
    "spike":  spike_test.run,
    "soak":   soak_test.run,
}


class ScenarioRunner:
    def __init__(
        self,
        config: LoadTestConfig,
        redis_aggregator,
        kafka_producer,
        db_session_factory,
        command_consumer=None,
        db_test_repo=None,
    ):
        self.config = config
        self._redis = redis_aggregator
        self._kafka = kafka_producer
        self._db_factory = db_session_factory
        self._cmd_consumer = command_consumer
        self._db_test_repo = db_test_repo
        self._engine: Optional[LoadEngine] = None

    async def run(self) -> Dict[str, Any]:
        """Start the engine, run the scenario-specific logic, persist result."""
        cfg = self.config
        scenario_fn = _RUNNERS.get(cfg.scenario_type)
        if not scenario_fn:
            raise ValueError(f"Unknown scenario_type: {cfg.scenario_type!r}")

        self._engine = LoadEngine(
            config=cfg,
            redis_aggregator=self._redis,
            kafka_producer=self._kafka,
            db_session_factory=self._db_factory,
            command_consumer=self._cmd_consumer,
        )

        if self._db_test_repo:
            await self._db_test_repo.update_status(
                cfg.test_id, "running",
                started_at=datetime.now(timezone.utc),
            )

        await self._engine.start()

        try:
            scenario_result = await scenario_fn(self._engine)
        except Exception as exc:
            logger.error(
                "Scenario %s failed with exception: %s", cfg.scenario_type, exc,
                extra={"test_id": cfg.test_id},
            )
            await self._engine.abort()
            if self._db_test_repo:
                await self._db_test_repo.update_status(
                    cfg.test_id, "failed",
                    completed_at=datetime.now(timezone.utc),
                    result_summary={"error": str(exc)},
                )
            raise

        result_dict = asdict(scenario_result)
        final_stats = self._engine._final_stats

        summary = {
            "scenario_type": cfg.scenario_type,
            **result_dict,
            "total_requests": getattr(final_stats, "total_requests", 0) if final_stats else 0,
            "success_rate": getattr(final_stats, "success_rate", 0.0) if final_stats else 0.0,
            "avg_latency_ms": getattr(final_stats, "avg_ms", 0.0) if final_stats else 0.0,
            "p95_latency_ms": getattr(final_stats, "p95_ms", 0.0) if final_stats else 0.0,
            "p99_latency_ms": getattr(final_stats, "p99_ms", 0.0) if final_stats else 0.0,
            "peak_rps": getattr(final_stats, "current_rps", 0.0) if final_stats else 0.0,
        }

        status = "completed"
        if hasattr(scenario_result, "passed") and not scenario_result.passed:
            status = "failed"
        if hasattr(scenario_result, "reason") and scenario_result.reason == "breaking_point_found":
            status = "completed"

        if self._db_test_repo:
            await self._db_test_repo.update_status(
                cfg.test_id, status,
                completed_at=datetime.now(timezone.utc),
                result_summary=summary,
            )

        logger.info(
            "Scenario %s finished: status=%s test_id=%s",
            cfg.scenario_type, status, cfg.test_id,
            extra={"test_id": cfg.test_id},
        )
        return summary

    async def abort(self) -> None:
        if self._engine:
            await self._engine.abort()

    def is_running(self) -> bool:
        return self._engine is not None and not self._engine.is_stopped()
