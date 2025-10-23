"""Pydantic v2 schemas for the schedules API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.core.scheduler.cron_manager import validate_cron


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    cron_expression: str
    target_namespace: str = Field(..., min_length=1)
    target_label_selector: Optional[str] = None
    chaos_type: str = Field(..., pattern=r"^(pod_kill|cpu_stress|memory_stress|network_delay)$")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    steady_state_thresholds: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        error = validate_cron(v)
        if error:
            raise ValueError(error)
        return v


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    cron_expression: Optional[str] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            error = validate_cron(v)
            if error:
                raise ValueError(error)
        return v


class ScheduleResponse(BaseModel):
    schedule_id: str
    name: str
    description: str
    cron_expression: str
    target_namespace: str
    target_label_selector: Optional[str]
    chaos_type: str
    parameters: Dict[str, Any]
    steady_state_thresholds: Dict[str, Any]
    enabled: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleList(BaseModel):
    schedules: List[ScheduleResponse]
    count: int
