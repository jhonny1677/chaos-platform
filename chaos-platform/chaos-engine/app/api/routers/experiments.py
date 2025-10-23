"""Experiments API — CRUD + trigger."""

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.experiment import ExperimentCreate, ExperimentList, ExperimentResponse
from app.core.chaos.chaos_manager import ChaosManager, is_circuit_open, reset_circuit_breaker
from app.core.steady_state.validator import SteadyStateValidator
from app.database.connection import get_db, AsyncSessionLocal
from app.database.repositories.experiment_repo import ExperimentRepository
from app.database.repositories.result_repo import ResultRepository
from app.messaging.event_publisher import EventPublisher
from app.messaging.kafka_producer import KafkaProducer

logger = logging.getLogger("chaos-engine.api.experiments")
router = APIRouter(prefix="/experiments", tags=["experiments"])

_PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus-kube-prometheus-prometheus.monitoring:9090",
)
_KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "chaos-events")

_kafka_producer = KafkaProducer(bootstrap_servers=_KAFKA_SERVERS, topic=_KAFKA_TOPIC)


def _make_manager(session: AsyncSession) -> ChaosManager:
    return ChaosManager(
        experiment_repo=ExperimentRepository(session),
        result_repo=ResultRepository(session),
        publisher=EventPublisher(_kafka_producer),
        validator=SteadyStateValidator(_PROMETHEUS_URL),
    )


@router.post("", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    payload: ExperimentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if is_circuit_open():
        raise HTTPException(
            status_code=503,
            detail="Circuit breaker is OPEN — experiments are paused. POST /experiments/circuit-breaker/reset to resume.",
        )

    repo = ExperimentRepository(db)
    exp = await repo.create(
        name=payload.name,
        description=payload.description,
        target_namespace=payload.target_namespace,
        target_label_selector=payload.target_label_selector,
        chaos_type=payload.chaos_type,
        parameters=payload.parameters,
        steady_state_thresholds=payload.steady_state_thresholds,
        status="pending",
    )

    # Run the experiment asynchronously without blocking the HTTP response
    background_tasks.add_task(_run_experiment_task, exp.experiment_id)

    logger.info("Created experiment %s", exp.experiment_id)
    return exp


async def _run_experiment_task(experiment_id: str) -> None:
    async with AsyncSessionLocal() as session:
        repo = ExperimentRepository(session)
        exp = await repo.get(experiment_id)
        if exp:
            manager = _make_manager(session)
            await manager.run_experiment(exp)


@router.get("", response_model=ExperimentList)
async def list_experiments(db: AsyncSession = Depends(get_db)):
    repo = ExperimentRepository(db)
    experiments = await repo.list_all()
    return ExperimentList(experiments=experiments, count=len(experiments))


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, db: AsyncSession = Depends(get_db)):
    repo = ExperimentRepository(db)
    exp = await repo.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id!r} not found")
    return exp


@router.delete("/{experiment_id}", status_code=204)
async def delete_experiment(experiment_id: str, db: AsyncSession = Depends(get_db)):
    repo = ExperimentRepository(db)
    deleted = await repo.delete(experiment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id!r} not found")


@router.post("/circuit-breaker/reset")
async def reset_circuit():
    """Manually re-open the circuit breaker after consecutive failures."""
    reset_circuit_breaker()
    return {"status": "circuit_breaker_reset"}


@router.get("/circuit-breaker/status")
async def circuit_status():
    return {"circuit_open": is_circuit_open()}
