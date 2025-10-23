"""Test fixtures for the chaos engine.

Uses SQLite in-memory (aiosqlite) to avoid needing a real PostgreSQL.
Kubernetes and Kafka are mocked to avoid cluster dependencies in unit tests.
"""

import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock, patch

# Force SQLite before any app imports touch DATABASE_URL
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["PROMETHEUS_URL"] = "http://localhost:9090"

from app.database.connection import Base, get_db
from app.main import app


_TEST_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_TestSession = async_sessionmaker(_TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db():
    async with _TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    async with _TestSession() as session:
        yield session


@pytest.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # Patch Kafka producer and K8s clients so tests don't need real infra
    with (
        patch("app.api.routers.experiments._kafka_producer") as mock_kafka,
        patch("app.core.kubernetes.client.core_v1") as mock_core_v1,
    ):
        mock_kafka.send = AsyncMock(return_value=True)
        mock_core_v1.return_value = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()
