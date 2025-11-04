"""Results API — time-series snapshots and live Redis stats."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.result import LiveStatsResponse, ResultSnapshotList
from app.database.connection import get_db
from app.database.repositories.result_repo import ResultRepository

logger = logging.getLogger("load-tester.api.results")
router = APIRouter(prefix="/results", tags=["results"])


@router.get("/live/{test_id}", response_model=LiveStatsResponse)
async def get_live_stats(test_id: str):
    """Fetch the latest stats from Redis for a running test (real-time)."""
    from app.main import _redis
    stats = await _redis.get_stats(test_id)
    status = await _redis.get_status(test_id)
    return LiveStatsResponse(
        test_id=test_id,
        status=status,
        stats=stats,
        available=stats is not None,
    )


@router.get("/{test_id}", response_model=ResultSnapshotList)
async def get_test_snapshots(test_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch the persisted per-second snapshots for a completed or running test."""
    repo = ResultRepository(db)
    snapshots = await repo.list_for_test(test_id)
    return ResultSnapshotList(snapshots=snapshots, count=len(snapshots))
