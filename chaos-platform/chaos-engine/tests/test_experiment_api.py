"""Integration tests for the experiments HTTP API."""

import pytest


class TestExperimentCRUD:
    async def test_create_experiment_returns_201(self, client):
        payload = {
            "name": "Kill one pod",
            "target_namespace": "target-app",
            "chaos_type": "pod_kill",
            "parameters": {"kill_percentage": 20},
            "steady_state_thresholds": {"error_rate_percent": 5.0},
        }
        resp = await client.post("/experiments", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Kill one pod"
        assert data["status"] == "pending"
        assert "experiment_id" in data

    async def test_list_experiments_returns_all(self, client):
        for i in range(3):
            await client.post(
                "/experiments",
                json={
                    "name": f"Experiment {i}",
                    "target_namespace": "target-app",
                    "chaos_type": "pod_kill",
                },
            )
        resp = await client.get("/experiments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3

    async def test_get_experiment_by_id(self, client):
        create_resp = await client.post(
            "/experiments",
            json={
                "name": "Get me",
                "target_namespace": "target-app",
                "chaos_type": "cpu_stress",
            },
        )
        exp_id = create_resp.json()["experiment_id"]
        resp = await client.get(f"/experiments/{exp_id}")
        assert resp.status_code == 200
        assert resp.json()["experiment_id"] == exp_id

    async def test_get_nonexistent_experiment_returns_404(self, client):
        resp = await client.get("/experiments/does-not-exist")
        assert resp.status_code == 404

    async def test_delete_experiment(self, client):
        create_resp = await client.post(
            "/experiments",
            json={
                "name": "Delete me",
                "target_namespace": "target-app",
                "chaos_type": "memory_stress",
            },
        )
        exp_id = create_resp.json()["experiment_id"]
        del_resp = await client.delete(f"/experiments/{exp_id}")
        assert del_resp.status_code == 204
        get_resp = await client.get(f"/experiments/{exp_id}")
        assert get_resp.status_code == 404

    async def test_invalid_chaos_type_returns_422(self, client):
        resp = await client.post(
            "/experiments",
            json={
                "name": "Bad type",
                "target_namespace": "target-app",
                "chaos_type": "rm_rf_everything",
            },
        )
        assert resp.status_code == 422


class TestCircuitBreaker:
    async def test_circuit_breaker_status(self, client):
        resp = await client.get("/experiments/circuit-breaker/status")
        assert resp.status_code == 200
        assert "circuit_open" in resp.json()

    async def test_circuit_breaker_reset(self, client):
        resp = await client.post("/experiments/circuit-breaker/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "circuit_breaker_reset"


class TestHealthEndpoints:
    async def test_liveness(self, client):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    async def test_readiness(self, client):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        assert "ready" in resp.json()
