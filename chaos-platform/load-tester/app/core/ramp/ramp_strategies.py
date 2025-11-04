"""Ramp-up strategy implementations.

Each strategy is a callable that takes (elapsed_seconds, config) and returns
the target virtual user count at that point in time.

Usage:
    strategy = get_strategy("linear")
    target_vu = strategy(elapsed=30, **config)
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class RampConfig:
    start_users: int = 1
    target_users: int = 10
    ramp_duration_seconds: float = 60.0
    step_size: int = 10           # for step ramp
    step_interval_seconds: float = 30.0  # for step ramp
    waypoints: List[Tuple[float, int]] = field(default_factory=list)  # [(time, users), ...]


def linear(elapsed: float, cfg: RampConfig) -> int:
    """Linearly interpolate from start_users to target_users over ramp_duration."""
    if cfg.ramp_duration_seconds <= 0:
        return cfg.target_users
    if elapsed >= cfg.ramp_duration_seconds:
        return cfg.target_users
    fraction = elapsed / cfg.ramp_duration_seconds
    users = cfg.start_users + (cfg.target_users - cfg.start_users) * fraction
    return max(1, round(users))


def step(elapsed: float, cfg: RampConfig) -> int:
    """Increase by step_size every step_interval_seconds."""
    if cfg.step_interval_seconds <= 0:
        return cfg.target_users
    steps_taken = int(elapsed // cfg.step_interval_seconds)
    users = cfg.start_users + steps_taken * cfg.step_size
    return max(cfg.start_users, min(users, cfg.target_users))


def instant(elapsed: float, cfg: RampConfig) -> int:
    """Jump to target_users immediately on first tick."""
    return cfg.target_users


def custom(elapsed: float, cfg: RampConfig) -> int:
    """Interpolate between (time, users) waypoints.

    Waypoints must be sorted by time ascending.
    Example: [(0, 10), (60, 50), (120, 100)]
    """
    waypoints = sorted(cfg.waypoints, key=lambda w: w[0])
    if not waypoints:
        return cfg.target_users
    if elapsed <= waypoints[0][0]:
        return waypoints[0][1]
    if elapsed >= waypoints[-1][0]:
        return waypoints[-1][1]

    # Linear interpolation between surrounding waypoints
    for i in range(len(waypoints) - 1):
        t0, u0 = waypoints[i]
        t1, u1 = waypoints[i + 1]
        if t0 <= elapsed <= t1:
            fraction = (elapsed - t0) / (t1 - t0)
            return max(1, round(u0 + (u1 - u0) * fraction))
    return waypoints[-1][1]


_STRATEGIES = {
    "linear": linear,
    "step": step,
    "instant": instant,
    "custom": custom,
}


def get_strategy(name: str):
    fn = _STRATEGIES.get(name.lower())
    if not fn:
        raise ValueError(f"Unknown ramp strategy: {name!r}. Choose from {list(_STRATEGIES)}")
    return fn
