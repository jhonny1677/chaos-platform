"""Workers API — expose live worker counts and K8s heartbeat status."""

import logging
from fastapi import APIRouter, HTTPException
from app.api.schemas.worker import WorkerList, WorkerStatus, ActiveTestWorkers

logger = logging.getLogger("load-tester.api.workers")
router = APIRouter(prefix="/workers", tags=["workers"])

# Registry of running engines — populated by tests router
_active_engines = {}


def register_engine(test_id: str, engine) -> None:
    _active_engines[test_id] = engine


def unregister_engine(test_id: str) -> None:
    _active_engines.pop(test_id, None)


@router.get("", response_model=WorkerList)
async def list_workers():
    from app.main import _redis
    live = await _redis.list_live_workers()
    workers = [
        WorkerStatus(worker_id=w, test_id="unknown", status="active", last_heartbeat="")
        for w in live
    ]
    return WorkerList(workers=workers, count=len(workers), active_count=len(workers))


@router.get("/{test_id}", response_model=ActiveTestWorkers)
async def get_test_workers(test_id: str):
    engine = _active_engines.get(test_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"No running engine for test {test_id!r}")
    return ActiveTestWorkers(
        test_id=test_id,
        active_workers=engine.active_workers(),
        target_workers=engine.config.virtual_users,
    )
