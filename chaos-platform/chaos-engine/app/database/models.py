"""SQLAlchemy ORM models for the chaos engine.

Three tables:
  experiments — one row per experiment run (status tracks lifecycle)
  schedules   — recurring experiment definitions with cron expressions
  experiment_results — detailed outcome stored after each run completes
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.connection import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # Target
    target_namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    target_label_selector: Mapped[str] = mapped_column(String(500), nullable=True)

    # Chaos config
    chaos_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    steady_state_thresholds: Mapped[dict] = mapped_column(JSON, default=dict)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Result summary (denormalised for quick listing)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Link back to schedule that triggered this run (nullable for ad-hoc)
    schedule_id: Mapped[str] = mapped_column(String(36), nullable=True)


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    pods_targeted: Mapped[list] = mapped_column(JSON, default=list)
    pods_killed: Mapped[list] = mapped_column(JSON, default=list)
    actions_taken: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[list] = mapped_column(JSON, default=list)

    # Hypothesis
    hypothesis_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    hypothesis_result: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Metrics during experiment
    error_rate_before: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate_during: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate_after: Mapped[float] = mapped_column(Float, default=0.0)
    latency_p99_before_ms: Mapped[float] = mapped_column(Float, default=0.0)
    latency_p99_after_ms: Mapped[float] = mapped_column(Float, default=0.0)
    peak_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    recovery_time_seconds: Mapped[float] = mapped_column(Float, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    target_namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    target_label_selector: Mapped[str] = mapped_column(String(500), nullable=True)

    chaos_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    steady_state_thresholds: Mapped[dict] = mapped_column(JSON, default=dict)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
