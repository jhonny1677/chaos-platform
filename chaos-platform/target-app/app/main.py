"""
Chaos Platform — Target Application
=====================================
A fake e-commerce API built to be deliberately broken during chaos experiments.
It implements a realistic request lifecycle (DB reads/writes, latency, failures)
so that Prometheus metrics, Grafana dashboards, and AlertManager alerts all
show meaningful signal during chaos runs.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.routers import health, products, orders, users, chaos
from app.middleware.metrics import MetricsMiddleware
from app.middleware.logging import LoggingMiddleware, setup_logging
from app.database.connection import init_db, engine
from app.database.seed import seed_database
from app.models.schemas import make_response

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_NAME = os.getenv("APP_NAME", "target-app")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


def _setup_tracing() -> None:
    """Wire up OpenTelemetry with an OTLP exporter if an endpoint is configured.

    When OTEL_EXPORTER_OTLP_ENDPOINT is unset (local dev, unit tests) tracing
    is still active but spans are discarded — no side effects.
    """
    resource = Resource.create({
        "service.name": APP_NAME,
        "service.version": APP_VERSION,
        "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
        "k8s.pod.name": os.getenv("POD_NAME", "unknown"),
        "k8s.namespace.name": os.getenv("POD_NAMESPACE", "target-app"),
    })

    provider = TracerProvider(resource=resource)

    if OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup → serve traffic → graceful shutdown."""
    setup_logging()
    _setup_tracing()

    logger = logging.getLogger("target-app")
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    # Create DB tables then populate seed data (idempotent)
    await init_db()
    await seed_database()

    logger.info("Startup complete — ready to receive chaos")

    yield  # ── application serves requests ──

    # Graceful shutdown: drain DB connection pool so in-flight queries finish
    await engine.dispose()
    logger.info("Database pool closed — shutdown complete")


app = FastAPI(
    title="Chaos Platform Target App",
    description="Fake e-commerce API — built to be broken during chaos experiments",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — permissive for dev; tighten origins in prod via env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware order: LoggingMiddleware is outermost (first to run, last to return)
# so it captures the total request duration including MetricsMiddleware overhead.
app.add_middleware(LoggingMiddleware)
app.add_middleware(MetricsMiddleware)

# Instrument all routes with OpenTelemetry spans automatically
FastAPIInstrumentor.instrument_app(app)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["observability"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(orders.router, prefix="/orders", tags=["orders"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(chaos.router)   # chaos endpoints live at root: /stress /memory /slow /error


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so unhandled exceptions still return the standard envelope."""
    logger = logging.getLogger("target-app")
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=make_response({"detail": "Internal server error"}, status="error"),
    )
