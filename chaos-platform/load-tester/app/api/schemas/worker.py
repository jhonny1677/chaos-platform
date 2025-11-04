"""Pydantic v2 schemas for the workers API."""

from typing import List
from pydantic import BaseModel


class WorkerStatus(BaseModel):
    worker_id: str
    test_id: str
    status: str          # active | idle | dead
    last_heartbeat: str


class WorkerList(BaseModel):
    workers: List[WorkerStatus]
    count: int
    active_count: int


class ActiveTestWorkers(BaseModel):
    test_id: str
    active_workers: int
    target_workers: int
