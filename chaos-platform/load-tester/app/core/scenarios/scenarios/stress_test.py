"""Stress Test — finds the system breaking point by stepping up virtual users.

Progression:
  - Start at 10 users
  - Add 10 users every 30 seconds (step ramp)
  - Stop condition: error_rate > 20% OR virtual users reach 200
  - Result: breaking_point_users (first count where error > 20%)

Tracks the peak stable throughput and the exact point of degradation.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.engine.load_engine import LoadEngine, LoadTestConfig
from app.core.engine.result_collector import LiveStats

logger = logging.getLogger("load-tester.scenario.stress")

START_USERS = 10
MAX_USERS = 200
STEP_SIZE = 10
STEP_INTERVAL_SECONDS = 30
MAX_ERROR_RATE_PCT = 20.0


@dataclass
class StressTestResult:
    breaking_point_users: Optional[int]
    max_stable_users: int
    peak_rps: float
    total_requests: int
    final_error_rate: float
    degradation_at_seconds: Optional[float]
    reason: str  # "error_rate_exceeded" | "max_users_reached" | "aborted"


async def run(engine: LoadEngine) -> StressTestResult:
    breaking_point: Optional[int] = None
    max_stable = START_USERS
    peak_rps = 0.0
    degradation_at: Optional[float] = None
    last_good_workers = START_USERS

    original_callback = engine._collector._stats_callback

    async def _monitor(stats: LiveStats) -> None:
        nonlocal breaking_point, max_stable, peak_rps, degradation_at, last_good_workers

        current_workers = engine.active_workers()
        if stats.current_rps > peak_rps:
            peak_rps = stats.current_rps

        if stats.error_rate <= MAX_ERROR_RATE_PCT:
            max_stable = current_workers
            last_good_workers = current_workers
        elif breaking_point is None:
            breaking_point = current_workers
            degradation_at = stats.elapsed_seconds
            logger.warning(
                "Breaking point reached at %d users (error_rate=%.1f%% at %.0fs)",
                breaking_point, stats.error_rate, stats.elapsed_seconds,
                extra={"test_id": engine.config.test_id},
            )
            await engine.stop(reason="breaking_point_found")

        if original_callback:
            await original_callback(stats)

    engine._collector._stats_callback = _monitor

    final = await engine.run()

    reason = "error_rate_exceeded" if breaking_point else "max_users_reached"
    return StressTestResult(
        breaking_point_users=breaking_point,
        max_stable_users=max_stable,
        peak_rps=round(peak_rps, 2),
        total_requests=final.total_requests,
        final_error_rate=final.error_rate,
        degradation_at_seconds=degradation_at,
        reason=reason,
    )


def build_config(test_id: str, target_url: str, name: str = "Stress Test") -> LoadTestConfig:
    # Max duration: enough steps to reach max users + buffer
    steps = (MAX_USERS - START_USERS) // STEP_SIZE
    max_duration = steps * STEP_INTERVAL_SECONDS + 120

    return LoadTestConfig(
        test_id=test_id,
        name=name,
        target_url=target_url,
        scenario_type="stress",
        virtual_users=MAX_USERS,
        duration_seconds=max_duration,
        ramp_strategy="step",
        think_time_ms=100,
        start_users=START_USERS,
        step_size=STEP_SIZE,
        step_interval_seconds=STEP_INTERVAL_SECONDS,
    )
