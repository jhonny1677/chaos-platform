"""
Tests for the observability endpoints: /health, /ready, /metrics.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_status_code(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_envelope(client: AsyncClient):
    """Every endpoint must return the standard {status, data, timestamp} envelope."""
    body = (await client.get("/health")).json()
    assert "status" in body
    assert "data" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_health_status_is_ok(client: AsyncClient):
    body = (await client.get("/health")).json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_health_data_contains_required_fields(client: AsyncClient):
    data = (await client.get("/health")).json()["data"]
    assert data["status"] == "healthy"
    assert "version" in data
    assert "pod_name" in data
    assert "uptime_seconds" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_uptime_is_positive(client: AsyncClient):
    data = (await client.get("/health")).json()["data"]
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_ready_status_code(client: AsyncClient):
    response = await client.get("/ready")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ready_database_connected(client: AsyncClient):
    data = (await client.get("/ready")).json()["data"]
    assert data["database"] == "connected"
    assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_format(client: AsyncClient):
    response = await client.get("/metrics")
    assert response.status_code == 200
    # Prometheus text format starts with # HELP or a metric name
    assert b"http_requests_total" in response.content or b"# HELP" in response.content


@pytest.mark.asyncio
async def test_metrics_content_type(client: AsyncClient):
    response = await client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]
