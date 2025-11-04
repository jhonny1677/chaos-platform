"""Factory that constructs a LoadTestConfig from user-supplied parameters.

For known scenario types (smoke/stress/spike/soak) the defaults are wired in
via each scenario module. For custom scenarios every parameter must be supplied.
"""

from typing import Any, Dict, Optional

from app.core.engine.load_engine import LoadTestConfig
from app.core.scenarios.scenarios import smoke_test, stress_test, spike_test, soak_test


_BUILDERS = {
    "smoke":  smoke_test.build_config,
    "stress": stress_test.build_config,
    "spike":  spike_test.build_config,
    "soak":   soak_test.build_config,
}

_VALID_RAMP_STRATEGIES = {"linear", "step", "instant", "custom"}


def build(
    test_id: str,
    name: str,
    target_url: str,
    scenario_type: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> LoadTestConfig:
    """Create a LoadTestConfig, applying any caller-supplied overrides on top of defaults.

    For known scenario types, sensible defaults are pre-filled.
    Overrides can change any LoadTestConfig field (e.g. virtual_users, duration_seconds).
    """
    builder = _BUILDERS.get(scenario_type.lower())
    if builder:
        cfg = builder(test_id=test_id, target_url=target_url, name=name)
    else:
        cfg = LoadTestConfig(
            test_id=test_id,
            name=name,
            target_url=target_url,
            scenario_type=scenario_type,
            virtual_users=10,
            duration_seconds=60,
        )

    if overrides:
        for key, value in overrides.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)

    # Validate ramp strategy
    if cfg.ramp_strategy not in _VALID_RAMP_STRATEGIES:
        raise ValueError(
            f"Invalid ramp_strategy {cfg.ramp_strategy!r}. Choose from {_VALID_RAMP_STRATEGIES}"
        )

    return cfg
