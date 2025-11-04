"""Pydantic v2 schemas for the tests API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class TestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    target_url: str = Field(..., min_length=1)
    scenario_type: str = Field(..., pattern=r"^(smoke|stress|spike|soak)$")

    # Optional overrides — if not set, scenario defaults are used
    virtual_users: Optional[int] = Field(None, ge=1, le=500)
    duration_seconds: Optional[int] = Field(None, ge=10, le=7200)
    ramp_strategy: Optional[str] = Field(None, pattern=r"^(linear|step|instant|custom)$")
    think_time_ms: Optional[int] = Field(None, ge=0, le=10000)
    ramp_duration_seconds: Optional[float] = Field(None, ge=0)
    start_users: Optional[int] = Field(None, ge=1)
    step_size: Optional[int] = Field(None, ge=1)
    step_interval_seconds: Optional[float] = Field(None, ge=5)
    ramp_waypoints: Optional[List[List[float]]] = None  # [[time, users], ...]


class TestResponse(BaseModel):
    test_id: str
    name: str
    target_url: str
    scenario_type: str
    config: Dict[str, Any]
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result_summary: Optional[Dict[str, Any]]

    model_config = {"from_attributes": True}


class TestList(BaseModel):
    tests: List[TestResponse]
    count: int
