"""Unit tests for the load engine components."""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.engine.request_generator import generate, ENDPOINT_WEIGHTS
from app.core.engine.worker_pool import WorkerPool
from app.core.engine.result_collector import RequestResult, _percentiles
from app.core.ramp.ramp_strategies import RampConfig, linear, step, instant, custom


# ── Request Generator ──────────────────────────────────────────────────────────

class TestRequestGenerator:
    def test_generates_request_with_correlation_id(self):
        req = generate("http://target-app.target-app:8000", "test-001")
        assert req.correlation_id
        assert len(req.correlation_id) == 36

    def test_respects_endpoint_distribution_roughly(self):
        """60% should be GET /products over 1000 samples."""
        counts = {}
        for _ in range(1000):
            req = generate("http://target-app:8000", "test-001")
            counts[req.endpoint] = counts.get(req.endpoint, 0) + 1
        # /products should be the most common by a wide margin
        assert counts.get("/products", 0) > 400

    def test_post_orders_has_payload(self):
        """Force POST /orders by patching random."""
        with patch("app.core.engine.request_generator.random.random", return_value=0.85):
            req = generate("http://target-app:8000", "test-001")
            assert req.method == "POST"
            assert req.json_payload is not None
            assert "user_id" in req.json_payload

    def test_get_requests_have_no_payload(self):
        with patch("app.core.engine.request_generator.random.random", return_value=0.1):
            req = generate("http://target-app:8000", "test-001")
            assert req.method == "GET"
            assert req.json_payload is None

    def test_test_id_in_headers(self):
        req = generate("http://target-app:8000", "my-test-id")
        assert req.headers["X-Load-Test-ID"] == "my-test-id"


# ── Latency Percentiles ────────────────────────────────────────────────────────

class TestPercentiles:
    def test_empty_returns_zeros(self):
        assert _percentiles([]) == (0.0, 0.0, 0.0, 0.0)

    def test_single_value(self):
        p50, p95, p99, avg = _percentiles([100.0])
        assert p50 == 100.0
        assert avg == 100.0

    def test_sorted_list(self):
        data = list(range(1, 101))  # 1..100
        p50, p95, p99, avg = _percentiles(data)
        assert 48 <= p50 <= 52
        assert 93 <= p95 <= 97
        assert 98 <= p99 <= 100
        assert avg == 50.5


# ── Ramp Strategies ───────────────────────────────────────────────────────────

class TestRampStrategies:
    def test_instant_returns_target_immediately(self):
        cfg = RampConfig(start_users=1, target_users=50)
        assert instant(0, cfg) == 50
        assert instant(300, cfg) == 50

    def test_linear_at_start(self):
        cfg = RampConfig(start_users=1, target_users=100, ramp_duration_seconds=100)
        assert linear(0, cfg) == 1

    def test_linear_at_midpoint(self):
        cfg = RampConfig(start_users=0, target_users=100, ramp_duration_seconds=100)
        result = linear(50, cfg)
        assert 48 <= result <= 52

    def test_linear_at_end(self):
        cfg = RampConfig(start_users=1, target_users=100, ramp_duration_seconds=100)
        assert linear(100, cfg) == 100
        assert linear(200, cfg) == 100  # capped at target

    def test_step_increases_correctly(self):
        cfg = RampConfig(start_users=10, target_users=50, step_size=10, step_interval_seconds=30)
        assert step(0, cfg) == 10
        assert step(30, cfg) == 20
        assert step(60, cfg) == 30
        assert step(90, cfg) == 40

    def test_step_caps_at_target(self):
        cfg = RampConfig(start_users=10, target_users=30, step_size=10, step_interval_seconds=10)
        assert step(500, cfg) == 30

    def test_custom_interpolates(self):
        cfg = RampConfig(waypoints=[(0, 10), (60, 50), (120, 100)])
        assert custom(0, cfg) == 10
        assert custom(120, cfg) == 100
        result = custom(60, cfg)
        assert 48 <= result <= 52

    def test_custom_clamps_past_last_waypoint(self):
        cfg = RampConfig(waypoints=[(0, 10), (100, 50)])
        assert custom(200, cfg) == 50


# ── Worker Pool ───────────────────────────────────────────────────────────────

class TestWorkerPool:
    async def test_set_target_adjusts_worker_count(self):
        queue = asyncio.Queue()
        stop = asyncio.Event()

        with patch("app.core.engine.worker_pool.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            pool = WorkerPool(
                test_id="test-001",
                target_url="http://target:8000",
                result_queue=queue,
                stop_event=stop,
            )
            pool._client = AsyncMock()

            # Manually add fake tasks
            for i in range(5):
                task = asyncio.create_task(asyncio.sleep(3600))
                pool._workers[f"w{i}"] = task

            assert pool.active_count() == 5

            # Reduce to 3
            stop.set()  # prevent new workers from being spawned in _on_worker_done
            pool.set_target(3)
            assert len(pool._workers) == 3

            # Cleanup
            for t in list(pool._workers.values()):
                t.cancel()
            await asyncio.gather(*pool._workers.values(), return_exceptions=True)
