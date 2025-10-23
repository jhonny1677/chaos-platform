"""Pydantic v2 schemas for the results API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ResultResponse(BaseModel):
    result_id: str
    experiment_id: str
    pods_targeted: List[str]
    pods_killed: List[str]
    actions_taken: List[Any]
    timeline: List[Any]
    hypothesis_passed: bool
    hypothesis_result: Optional[Dict[str, Any]]
    error_rate_before: float
    error_rate_during: float
    error_rate_after: float
    latency_p99_before_ms: float
    latency_p99_after_ms: float
    peak_latency_ms: float
    recovery_time_seconds: Optional[float]
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ResultList(BaseModel):
    results: List[ResultResponse]
    count: int
