import os
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.database.connection import get_db, engine
from app.middleware.metrics import DB_POOL_SIZE
from app.models.schemas import make_response

router = APIRouter()

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
POD_NAME = os.getenv("POD_NAME", "unknown")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
_START_TIME = time.monotonic()


@router.get("/health", summary="Liveness probe")
async def health():
    """Always returns 200 while the process is alive.

    Kubernetes uses this as the liveness probe. If it returns non-200,
    the pod is restarted. The chaos engine's kill simulation is visible
    here: between kill and restart, the endpoint stops responding entirely.
    """
    return make_response({
        "status": "healthy",
        "version": APP_VERSION,
        "pod_name": POD_NAME,
        "environment": ENVIRONMENT,
        "uptime_seconds": round(time.monotonic() - _START_TIME, 2),
    })


@router.get("/ready", summary="Readiness probe")
async def ready(db: AsyncSession = Depends(get_db)):
    """Returns 200 only when the database connection is healthy.

    Kubernetes uses this as the readiness probe. During chaos experiments
    that kill the database pod, this endpoint returns 503 and Kubernetes
    stops routing traffic to this pod — demonstrating graceful degradation.
    """
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=make_response(
                {"database": "unreachable", "error": str(exc)},
                status="error",
            ),
        )

    # Keep the DB pool size metric current
    pool = engine.pool
    DB_POOL_SIZE.set(pool.size() if hasattr(pool, "size") else 10)

    return make_response({"database": "connected", "status": "ready"})


@router.get("/metrics", summary="Prometheus metrics scrape endpoint")
async def metrics():
    """Exposes all Prometheus metrics in text exposition format.

    Prometheus scrapes this every 15 seconds. Grafana reads from Prometheus.
    During load tests you'll see http_requests_total climb and
    http_request_duration_seconds p99 spike on /stress and /slow endpoints.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
