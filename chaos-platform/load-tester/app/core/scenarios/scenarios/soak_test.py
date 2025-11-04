"""Soak Test — sustained load to detect memory leaks and latency drift.

Config: 20 virtual users for 30 minutes (1800 seconds).
Alert condition: p99 latency increases > 50% from the 60-second baseline.

The baseline is captured during the first 60 seconds. Every subsequent minute
the latest p99 is compared against the baseline; if drift exceeds 50% the test
fails and the engine is stopped.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.engine.load_engine import LoadEngine, LoadTestConfig
from app.core.engine.result_collector import LiveStats

logger = logging.getLogger("load-tester.scenario.soak")

VIRTUAL_USERS = 20
DURATION_SECONDS = 1800  # 30 minutes
BASELINE_WINDOW_SECONDS = 60
MAX_P99_DRIFT_PCT = 50.0


@dataclass
class SoakTestResult:
    passed: bool
    failure_reason: Optional[str]
    baseline_p99_ms: Optional[float]
    final_p99_ms: float
    p99_drift_pct: Optional[float]
    total_requests: int
    error_rate: float
    elapsed_seconds: float


async def run(engine: LoadEngine) -> SoakTestResult:
    baseline_p99: Optional[float] = None
    baseline_samples = []
    failure_reason: Optional[str] = None

    original_callback = engine._collector._stats_callback

    async def _monitor(stats: LiveStats) -> None:
        nonlocal baseline_p99, failure_reason

        elapsed = stats.elapsed_seconds

        # Collect baseline samples for the first 60 seconds
        if elapsed <= BASELINE_WINDOW_SECONDS:
            if stats.p99_ms > 0:
                baseline_samples.append(stats.p99_ms)
            return

        # Set baseline once after baseline window closes
        if baseline_p99 is None and baseline_samples:
            baseline_p99 = sum(baseline_samples) / len(baseline_samples)
            logger.info(
                "Soak test baseline established: p99=%.0fms (elapsed=%.0fs)",
                baseline_p99, elapsed, extra={"test_id": engine.config.test_id},
            )

        # Check for latency drift every minute
        if baseline_p99 and elapsed % 60 < 5 and stats.p99_ms > 0:
            drift_pct = ((stats.p99_ms - baseline_p99) / baseline_p99) * 100
            logger.info(
                "Soak check: p99=%.0fms baseline=%.0fms drift=%.1f%% (elapsed=%.0fs)",
                stats.p99_ms, baseline_p99, drift_pct, elapsed,
                extra={"test_id": engine.config.test_id},
            )
            if drift_pct > MAX_P99_DRIFT_PCT:
                failure_reason = (
                    f"p99_latency_drift={drift_pct:.1f}% > threshold={MAX_P99_DRIFT_PCT}% "
                    f"(baseline={baseline_p99:.0f}ms current={stats.p99_ms:.0f}ms)"
                )
                logger.error(
                    "Soak test FAILING: %s", failure_reason,
                    extra={"test_id": engine.config.test_id},
                )
                await engine.stop(reason="soak_test_failed")

        if original_callback:
            await original_callback(stats)

    engine._collector._stats_callback = _monitor

    final = await engine.run()

    p99_drift = None
    if baseline_p99 and final.p99_ms > 0:
        p99_drift = round(((final.p99_ms - baseline_p99) / baseline_p99) * 100, 2)

    passed = failure_reason is None
    return SoakTestResult(
        passed=passed,
        failure_reason=failure_reason,
        baseline_p99_ms=round(baseline_p99, 2) if baseline_p99 else None,
        final_p99_ms=round(final.p99_ms, 2),
        p99_drift_pct=p99_drift,
        total_requests=final.total_requests,
        error_rate=final.error_rate,
        elapsed_seconds=final.elapsed_seconds,
    )


def build_config(test_id: str, target_url: str, name: str = "Soak Test") -> LoadTestConfig:
    return LoadTestConfig(
        test_id=test_id,
        name=name,
        target_url=target_url,
        scenario_type="soak",
        virtual_users=VIRTUAL_USERS,
        duration_seconds=DURATION_SECONDS,
        ramp_strategy="linear",
        think_time_ms=100,
        start_users=5,
        ramp_duration_seconds=60.0,
    )
