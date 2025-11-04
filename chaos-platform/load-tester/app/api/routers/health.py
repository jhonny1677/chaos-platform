"""Health and metrics endpoints."""

from fastapi import APIRouter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness():
    return {"status": "alive", "service": "load-tester"}


@router.get("/health/ready")
async def readiness():
    return {"ready": True}


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
