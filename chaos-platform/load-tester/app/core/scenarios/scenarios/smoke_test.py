"""Smoke Test — quick sanity check that the target app is responsive.

Config: 10 virtual users, 60 seconds, instant ramp.
Pass criteria: error rate ≤ 1% throughout the run.
Fail fast: if error rate exceeds 1% at any second, stop immediately and fail.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.engine.load_engine import LoadEngine, LoadTestConfig
from app.core.engine.result_collector import LiveStats

logger = logging.getLogger("load-tester.scenario.smoke")

VIRTUAL_USERS = 10
DURATION_SECONDS = 60
MAX_ERROR_RATE_PCT = 1.0


@dataclass
class SmokeTestResult:
    passed: bool
    failure_reason: Optional[str]
    total_requests: int
    error_rate: float
    p99_ms: float
    duration_seconds: float


async def run(engine: LoadEngine) -> SmokeTestResult:
    """Execute a smoke test using an already-configured engine.

    The engine must be started before calling run().
    """
    failure_reason: Optional[str] = None
    last_stats: Optional[LiveStats] = None

    original_callback = engine._collector._stats_callback

    async def _monitor(stats: LiveStats) -> None:
        nonlocal failure_reason, last_stats
        last_stats = stats
        if stats.error_rate > MAX_ERROR_RATE_PCT and stats.total_requests >= 10:
            failure_reason = (
                f"error_rate={stats.error_rate:.1f}% exceeded threshold={MAX_ERROR_RATE_PCT}% "
                f"at {stats.elapsed_seconds:.0f}s"
            )
            logger.warning(
                "Smoke test FAILING: %s", failure_reason,
                extra={"test_id": engine.config.test_id},
            )
            await engine.stop(reason="smoke_test_failed")
        if original_callback:
            await original_callback(stats)

    engine._collector._stats_callback = _monitor

    final = await engine.run()

    passed = failure_reason is None and (final.error_rate <= MAX_ERROR_RATE_PCT)
    return SmokeTestResult(
        passed=passed,
        failure_reason=failure_reason,
        total_requests=final.total_requests,
        error_rate=final.error_rate,
        p99_ms=final.p99_ms,
        duration_seconds=final.elapsed_seconds,
    )


def build_config(test_id: str, target_url: str, name: str = "Smoke Test") -> LoadTestConfig:
    return LoadTestConfig(
        test_id=test_id,
        name=name,
        target_url=target_url,
        scenario_type="smoke",
        virtual_users=VIRTUAL_USERS,
        duration_seconds=DURATION_SECONDS,
        ramp_strategy="instant",
        think_time_ms=100,
        start_users=VIRTUAL_USERS,
    )
