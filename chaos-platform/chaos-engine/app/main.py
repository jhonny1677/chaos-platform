"""Chaos Engine — FastAPI application entry point.

Startup sequence:
  1. Configure structured logging (JSON → stdout → Loki)
  2. Configure OpenTelemetry (traces → OTel Collector → Jaeger/Tempo)
  3. Initialise Kubernetes clients (in-cluster or kubeconfig for local dev)
  4. Run database migrations (create tables if not exist)
  5. Start Kafka producer
  6. Start experiment scheduler (background asyncio task)

Shutdown sequence:
  1. Stop scheduler
  2. Close Kafka producer
  3. Dispose SQLAlchemy engine
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import start_http_server

from app.api.routers import experiments, health, results, schedules
from app.core.kubernetes.client import init_kubernetes_client
from app.core.scheduler.experiment_scheduler import ExperimentScheduler
from app.database.connection import AsyncSessionLocal, init_db, engine
from app.messaging.kafka_producer import KafkaProducer
from app.messaging.event_publisher import EventPublisher
from app.core.steady_state.validator import SteadyStateValidator
from app.observability.logger import setup_logging
from app.observability.tracing import setup_tracing

_KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "chaos-events")
_PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus-kube-prometheus-prometheus.monitoring:9090",
)

_kafka_producer = KafkaProducer(bootstrap_servers=_KAFKA_SERVERS, topic=_KAFKA_TOPIC)
_scheduler: ExperimentScheduler = None


def _chaos_manager_factory(session):
    from app.core.chaos.chaos_manager import ChaosManager
    from app.database.repositories.experiment_repo import ExperimentRepository
    from app.database.repositories.result_repo import ResultRepository
    return ChaosManager(
        experiment_repo=ExperimentRepository(session),
        result_repo=ResultRepository(session),
        publisher=EventPublisher(_kafka_producer),
        validator=SteadyStateValidator(_PROMETHEUS_URL),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    setup_logging()
    setup_tracing("chaos-engine")

    init_kubernetes_client()
    await init_db()
    await _kafka_producer.start()

    _scheduler = ExperimentScheduler(
        get_db_session=AsyncSessionLocal,
        chaos_manager_factory=_chaos_manager_factory,
    )
    await _scheduler.start()

    yield

    await _scheduler.stop()
    await _kafka_producer.stop()
    await engine.dispose()


app = FastAPI(
    title="Chaos Engine",
    description="Controlled chaos injection and steady state validation for Kubernetes workloads",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)

app.include_router(health.router)
app.include_router(experiments.router)
app.include_router(results.router)
app.include_router(schedules.router)
