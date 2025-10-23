"""Pydantic v2 schemas for the experiments API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    target_namespace: str = Field(..., min_length=1)
    target_label_selector: Optional[str] = None
    chaos_type: str = Field(..., pattern=r"^(pod_kill|cpu_stress|memory_stress|network_delay)$")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    steady_state_thresholds: Dict[str, Any] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    experiment_id: str
    name: str
    description: str
    target_namespace: str
    target_label_selector: Optional[str]
    chaos_type: str
    parameters: Dict[str, Any]
    steady_state_thresholds: Dict[str, Any]
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result_summary: Optional[Dict[str, Any]]
    schedule_id: Optional[str]

    model_config = {"from_attributes": True}


class ExperimentList(BaseModel):
    experiments: List[ExperimentResponse]
    count: int
