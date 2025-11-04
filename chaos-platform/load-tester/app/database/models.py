"""SQLAlchemy ORM models for the load tester.

LoadTest   — one row per test run, tracks lifecycle and summarised results
TestResult — aggregated stats snapshot stored once per second during the test
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.connection import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class LoadTest(Base):
    __tablename__ = "load_tests"

    test_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(500), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Config stored as JSON so we don't need a separate table
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Denormalised result summary for quick listing
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=True)


class TestResult(Base):
    """One row per stats snapshot (written every second during a test)."""

    __tablename__ = "test_results"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    test_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    active_workers: Mapped[int] = mapped_column(Integer, default=0)
    requests_this_second: Mapped[int] = mapped_column(Integer, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    current_rps: Mapped[float] = mapped_column(Float, default=0.0)
    p50_ms: Mapped[float] = mapped_column(Float, default=0.0)
    p95_ms: Mapped[float] = mapped_column(Float, default=0.0)
    p99_ms: Mapped[float] = mapped_column(Float, default=0.0)
    avg_ms: Mapped[float] = mapped_column(Float, default=0.0)
