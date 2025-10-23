"""Health check endpoints — used by K8s liveness and readiness probes."""

import os
from fastapi import APIRouter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.core.chaos.chaos_manager import is_circuit_open
from app.core.kubernetes import client as k8s

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    checks = {
        "kubernetes": k8s.core_v1 is not None,
        "circuit_breaker": not is_circuit_open(),
    }
    all_ok = all(checks.values())
    return {"ready": all_ok, "checks": checks}


@router.get("/metrics")
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
