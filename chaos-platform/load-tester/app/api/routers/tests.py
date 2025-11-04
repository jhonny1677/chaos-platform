"""Tests API — CRUD + trigger load tests.

POST /tests        → create + immediately run test in a background task
GET  /tests        → list all tests
GET  /tests/:id    → get one test
DELETE /tests/:id  → delete test record
POST /tests/:id/stop → gracefully stop a running test
POST /tests/:id/abort → immediate abort
"""

import asyncio
import logging
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.workers import register_engine, unregister_engine
from app.api.schemas.test import TestCreate, TestList, TestResponse
from app.core.scenarios.scenario_builder import build
from app.core.scenarios.scenario_runner import ScenarioRunner
from app.database.connection import AsyncSessionLocal, get_db
from app.database.repositories.test_repo import TestRepository

logger = logging.getLogger("load-tester.api.tests")
router = APIRouter(prefix="/tests", tags=["tests"])

# Running scenario runners keyed by test_id
_runners: Dict[str, ScenarioRunner] = {}


@router.post("", response_model=TestResponse, status_code=201)
async def create_test(
    payload: TestCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    overrides = {
        k: v for k, v in payload.model_dump(exclude={"name", "target_url", "scenario_type"}).items()
        if v is not None
    }

    # Build config with scenario defaults + user overrides
    from app.database.repositories.test_repo import TestRepository
    repo = TestRepository(db)

    config = build(
        test_id="",   # will be replaced after DB insert
        name=payload.name,
        target_url=payload.target_url,
        scenario_type=payload.scenario_type,
        overrides=overrides,
    )

    test = await repo.create(
        name=payload.name,
        target_url=payload.target_url,
        scenario_type=payload.scenario_type,
        config={
            "virtual_users": config.virtual_users,
            "duration_seconds": config.duration_seconds,
            "ramp_strategy": config.ramp_strategy,
            "think_time_ms": config.think_time_ms,
        },
        status="pending",
    )

    # Rebuild config with the actual test_id
    config = build(
        test_id=test.test_id,
        name=payload.name,
        target_url=payload.target_url,
        scenario_type=payload.scenario_type,
        overrides={**overrides, "test_id": test.test_id},
    )
    config.test_id = test.test_id

    background_tasks.add_task(_run_test, test.test_id, config)
    logger.info("Created test %s (%s)", test.test_id, payload.scenario_type)
    return test


async def _run_test(test_id: str, config) -> None:
    from app.main import _redis, _kafka, _cmd_consumer
    async with AsyncSessionLocal() as session:
        repo = TestRepository(session)
        runner = ScenarioRunner(
            config=config,
            redis_aggregator=_redis,
            kafka_producer=_kafka,
            db_session_factory=AsyncSessionLocal,
            command_consumer=_cmd_consumer,
            db_test_repo=repo,
        )
        _runners[test_id] = runner
        if runner._engine:
            register_engine(test_id, runner._engine)
        try:
            await runner.run()
        except Exception as exc:
            logger.error("Test %s failed: %s", test_id, exc)
        finally:
            _runners.pop(test_id, None)
            unregister_engine(test_id)


@router.get("", response_model=TestList)
async def list_tests(db: AsyncSession = Depends(get_db)):
    repo = TestRepository(db)
    tests = await repo.list_all()
    return TestList(tests=tests, count=len(tests))


@router.get("/{test_id}", response_model=TestResponse)
async def get_test(test_id: str, db: AsyncSession = Depends(get_db)):
    repo = TestRepository(db)
    test = await repo.get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail=f"Test {test_id!r} not found")
    return test


@router.delete("/{test_id}", status_code=204)
async def delete_test(test_id: str, db: AsyncSession = Depends(get_db)):
    repo = TestRepository(db)
    deleted = await repo.delete(test_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Test {test_id!r} not found")


@router.post("/{test_id}/stop")
async def stop_test(test_id: str):
    runner = _runners.get(test_id)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Test {test_id!r} is not running")
    if runner._engine:
        await runner._engine.stop(reason="stopped_by_api")
    return {"status": "stopping", "test_id": test_id}


@router.post("/{test_id}/abort")
async def abort_test(test_id: str):
    runner = _runners.get(test_id)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Test {test_id!r} is not running")
    await runner.abort()
    return {"status": "aborted", "test_id": test_id}


@router.get("/{test_id}/status")
async def test_status(test_id: str):
    runner = _runners.get(test_id)
    is_running = runner is not None and runner.is_running()
    return {"test_id": test_id, "running": is_running}
