"""Tests for scenario builders and runner."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core.scenarios.scenario_builder import build
from app.core.scenarios.scenarios import smoke_test, stress_test, spike_test, soak_test
from app.core.ramp.ramp_strategies import RampConfig, get_strategy


class TestScenarioBuilder:
    def test_smoke_defaults(self):
        cfg = build("t1", "Smoke", "http://target:8000", "smoke")
        assert cfg.scenario_type == "smoke"
        assert cfg.virtual_users == smoke_test.VIRTUAL_USERS
        assert cfg.duration_seconds == smoke_test.DURATION_SECONDS
        assert cfg.ramp_strategy == "instant"

    def test_stress_defaults(self):
        cfg = build("t2", "Stress", "http://target:8000", "stress")
        assert cfg.scenario_type == "stress"
        assert cfg.virtual_users == stress_test.MAX_USERS
        assert cfg.ramp_strategy == "step"
        assert cfg.step_size == stress_test.STEP_SIZE

    def test_spike_defaults(self):
        cfg = build("t3", "Spike", "http://target:8000", "spike")
        assert cfg.scenario_type == "spike"
        assert cfg.virtual_users == spike_test.BASELINE_USERS

    def test_soak_defaults(self):
        cfg = build("t4", "Soak", "http://target:8000", "soak")
        assert cfg.scenario_type == "soak"
        assert cfg.virtual_users == soak_test.VIRTUAL_USERS
        assert cfg.duration_seconds == soak_test.DURATION_SECONDS

    def test_overrides_applied(self):
        cfg = build("t5", "Custom", "http://target:8000", "smoke",
                    overrides={"virtual_users": 50, "think_time_ms": 200})
        assert cfg.virtual_users == 50
        assert cfg.think_time_ms == 200

    def test_invalid_ramp_raises(self):
        with pytest.raises(ValueError, match="Invalid ramp_strategy"):
            build("t6", "Bad", "http://target:8000", "smoke",
                  overrides={"ramp_strategy": "turbo_boost"})

    def test_unknown_scenario_type_gets_defaults(self):
        cfg = build("t7", "Custom", "http://target:8000", "custom_thing")
        assert cfg.virtual_users == 10
        assert cfg.duration_seconds == 60


class TestGetStrategy:
    def test_returns_callable_for_all_strategies(self):
        for name in ["linear", "step", "instant", "custom"]:
            fn = get_strategy(name)
            assert callable(fn)

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            get_strategy("warp_speed")

    def test_case_insensitive(self):
        fn = get_strategy("LINEAR")
        assert callable(fn)


class TestSmokeTestConfig:
    def test_build_config_has_correct_scenario_type(self):
        cfg = smoke_test.build_config("t1", "http://target:8000")
        assert cfg.scenario_type == "smoke"
        assert cfg.name == "Smoke Test"

    def test_build_config_accepts_custom_name(self):
        cfg = smoke_test.build_config("t1", "http://target:8000", name="My Smoke")
        assert cfg.name == "My Smoke"


class TestStressTestConfig:
    def test_duration_covers_all_steps(self):
        cfg = stress_test.build_config("t1", "http://target:8000")
        steps = (stress_test.MAX_USERS - stress_test.START_USERS) // stress_test.STEP_SIZE
        min_duration = steps * stress_test.STEP_INTERVAL_SECONDS
        assert cfg.duration_seconds > min_duration
