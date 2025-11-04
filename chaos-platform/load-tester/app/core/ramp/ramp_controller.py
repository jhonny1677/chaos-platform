"""Ramp controller — adjusts worker count over time according to a strategy.

The controller runs as a background asyncio task and calls back into the
WorkerPool whenever the target user count changes. This keeps the ramp logic
completely decoupled from the worker implementation.
"""

import asyncio
import logging
import time
from typing import Callable, Optional

from app.core.ramp.ramp_strategies import RampConfig, get_strategy

logger = logging.getLogger("load-tester.ramp")


class RampController:
    def __init__(
        self,
        strategy_name: str,
        ramp_config: RampConfig,
        adjust_workers_callback: Callable[[int], None],
        poll_interval: float = 5.0,
    ):
        self.strategy = get_strategy(strategy_name)
        self.cfg = ramp_config
        self._adjust = adjust_workers_callback
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._start_time: Optional[float] = None
        self._last_target = 0

    async def start(self) -> None:
        self._running = True
        self._start_time = time.monotonic()
        # Apply initial worker count immediately
        initial = self.strategy(0.0, self.cfg)
        self._adjust(initial)
        self._last_target = initial
        self._task = asyncio.create_task(self._ramp_loop(), name="ramp-controller")
        logger.info(
            "Ramp controller started: strategy=%s start=%d target=%d",
            self.cfg.__class__.__name__, self.cfg.start_users, self.cfg.target_users,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _ramp_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._poll_interval)
            elapsed = time.monotonic() - self._start_time
            target = self.strategy(elapsed, self.cfg)
            if target != self._last_target:
                logger.info(
                    "Ramp: adjusting workers %d → %d (elapsed=%.0fs)",
                    self._last_target, target, elapsed,
                )
                self._adjust(target)
                self._last_target = target
