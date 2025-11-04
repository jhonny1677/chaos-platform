"""Pydantic v2 schemas for the results API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ResultSnapshotResponse(BaseModel):
    result_id: str
    test_id: str
    snapshot_at: datetime
    elapsed_seconds: float
    active_workers: int
    requests_this_second: int
    total_requests: int
    success_count: int
    error_count: int
    success_rate: float
    error_rate: float
    current_rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    avg_ms: float

    model_config = {"from_attributes": True}


class ResultSnapshotList(BaseModel):
    snapshots: List[ResultSnapshotResponse]
    count: int


class LiveStatsResponse(BaseModel):
    test_id: str
    status: Optional[str]
    stats: Optional[Dict[str, Any]]
    available: bool
