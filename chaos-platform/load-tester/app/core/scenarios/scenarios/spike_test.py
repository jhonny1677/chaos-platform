"""Spike Test — normal load, sudden spike, measure recovery.

Phases:
  1. Baseline:  10 users  for 2 minutes  (establish normal metrics)
  2. Spike:     100 users for 30 seconds (sudden traffic surge)
  3. Recovery:  10 users  (measure how long until error rate returns to baseline)
  4. Cooldown:  hold 10 users for 1 more minute after recovery confirmed

Recovery is defined as: error_rate ≤ baseline_error_rate + 2%
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from app.core.engine.load_engine import LoadEngine, LoadTestConfig
from app.core.engine.result_collector import LiveStats

logger = logging.getLogger("load-tester.scenario.spike")

BASELINE_USERS = 10
SPIKE_USERS = 100
BASELINE_SECONDS = 120
SPIKE_SECONDS = 30
COOLDOWN_SECONDS = 60
TOTAL_DURATION = BASELINE_SECONDS + SPIKE_SECONDS + COOLDOWN_SECONDS + 60


class _Phase(Enum):
    BASELINE = auto()
    SPIKE = auto()
    RECOVERY = auto()
    COOLDOWN = auto()


@dataclass
class SpikeTestResult:
    baseline_error_rate: float
    spike_peak_error_rate: float
    spike_peak_p99_ms: float
    recovered: bool
    recovery_time_seconds: Optional[float]
    total_requests: int
    elapsed_seconds: float


async def run(engine: LoadEngine) -> SpikeTestResult:
    phase = _Phase.BASELINE
    baseline_error_rate: Optional[float] = None
    spike_peak_error = 0.0
    spike_peak_p99 = 0.0
    spike_start_elapsed: Optional[float] = None
    recovery_time: Optional[float] = None

    original_callback = engine._collector._stats_callback

    async def _monitor(stats: LiveStats) -> None:
        nonlocal phase, baseline_error_rate, spike_peak_error
        nonlocal spike_peak_p99, spike_start_elapsed, recovery_time

        elapsed = stats.elapsed_seconds

        if phase == _Phase.BASELINE and elapsed >= BASELINE_SECONDS:
            # Capture baseline metrics before spike
            baseline_error_rate = stats.error_rate
            logger.info(
                "Spike: baseline established (error_rate=%.2f%%, elapsed=%.0fs)",
                baseline_error_rate, elapsed, extra={"test_id": engine.config.test_id},
            )
            engine._pool.set_target(SPIKE_USERS)
            spike_start_elapsed = elapsed
            phase = _Phase.SPIKE

        elif phase == _Phase.SPIKE:
            spike_peak_error = max(spike_peak_error, stats.error_rate)
            spike_peak_p99 = max(spike_peak_p99, stats.p99_ms)
            if elapsed >= BASELINE_SECONDS + SPIKE_SECONDS:
                logger.info(
                    "Spike: dropping back to %d users (peak_error=%.1f%% peak_p99=%.0fms)",
                    BASELINE_USERS, spike_peak_error, spike_peak_p99,
                    extra={"test_id": engine.config.test_id},
                )
                engine._pool.set_target(BASELINE_USERS)
                phase = _Phase.RECOVERY

        elif phase == _Phase.RECOVERY:
            threshold = (baseline_error_rate or 0.0) + 2.0
            if stats.error_rate <= threshold:
                recovery_time = elapsed - (BASELINE_SECONDS + SPIKE_SECONDS)
                logger.info(
                    "Spike: recovered in %.1fs (error_rate=%.2f%%)",
                    recovery_time, stats.error_rate, extra={"test_id": engine.config.test_id},
                )
                phase = _Phase.COOLDOWN
            if elapsed >= BASELINE_SECONDS + SPIKE_SECONDS + COOLDOWN_SECONDS:
                await engine.stop(reason="completed")

        elif phase == _Phase.COOLDOWN:
            if elapsed >= TOTAL_DURATION:
                await engine.stop(reason="completed")

        if original_callback:
            await original_callback(stats)

    engine._collector._stats_callback = _monitor

    final = await engine.run()

    return SpikeTestResult(
        baseline_error_rate=round(baseline_error_rate or 0.0, 2),
        spike_peak_error_rate=round(spike_peak_error, 2),
        spike_peak_p99_ms=round(spike_peak_p99, 2),
        recovered=recovery_time is not None,
        recovery_time_seconds=round(recovery_time, 2) if recovery_time else None,
        total_requests=final.total_requests,
        elapsed_seconds=final.elapsed_seconds,
    )


def build_config(test_id: str, target_url: str, name: str = "Spike Test") -> LoadTestConfig:
    return LoadTestConfig(
        test_id=test_id,
        name=name,
        target_url=target_url,
        scenario_type="spike",
        virtual_users=BASELINE_USERS,   # engine starts at baseline; scenario bumps mid-run
        duration_seconds=TOTAL_DURATION,
        ramp_strategy="instant",
        think_time_ms=100,
        start_users=BASELINE_USERS,
    )
