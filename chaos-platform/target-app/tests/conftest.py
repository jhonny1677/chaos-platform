"""
Test configuration and shared fixtures.

Uses SQLite in-memory so tests run without a real PostgreSQL instance.
The get_db dependency is overridden to inject the test session.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.database.connection import Base, get_db
from app.database.seed import seed_database

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """HTTP test client wired to the in-memory test database."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # Seed the test DB with products and users so endpoint tests have data
    from app.database.connection import AsyncSessionLocal
    from unittest.mock import patch
    # Patch AsyncSessionLocal so seed_database uses the test session
    import app.database.seed as seed_module
    original = seed_module.AsyncSessionLocal

    class _TestSessionFactory:
        def __aenter__(self):
            return db_session.__aenter__()
        def __aexit__(self, *args):
            return db_session.__aexit__(*args)

    seed_module.AsyncSessionLocal = _TestSessionFactory  # type: ignore
    await seed_database()
    seed_module.AsyncSessionLocal = original

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
