"""Schedules API — CRUD for recurring chaos schedules."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.schedule import ScheduleCreate, ScheduleList, ScheduleResponse, ScheduleUpdate
from app.core.scheduler.cron_manager import next_run_time
from app.database.connection import get_db
from app.database.models import Schedule

logger = logging.getLogger("chaos-engine.api.schedules")
router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(payload: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    next_at = next_run_time(payload.cron_expression)
    schedule = Schedule(
        name=payload.name,
        description=payload.description,
        cron_expression=payload.cron_expression,
        target_namespace=payload.target_namespace,
        target_label_selector=payload.target_label_selector,
        chaos_type=payload.chaos_type,
        parameters=payload.parameters,
        steady_state_thresholds=payload.steady_state_thresholds,
        enabled=payload.enabled,
        next_run_at=next_at,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    logger.info("Created schedule %s (%s)", schedule.schedule_id, schedule.cron_expression)
    return schedule


@router.get("", response_model=ScheduleList)
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Schedule).order_by(Schedule.created_at.desc()))
    schedules = list(result.scalars().all())
    return ScheduleList(schedules=schedules, count=len(schedules))


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    schedule = await _get_or_404(schedule_id, db)
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
):
    schedule = await _get_or_404(schedule_id, db)
    if payload.enabled is not None:
        schedule.enabled = payload.enabled
    if payload.cron_expression is not None:
        schedule.cron_expression = payload.cron_expression
        schedule.next_run_at = next_run_time(payload.cron_expression)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    schedule = await _get_or_404(schedule_id, db)
    await db.delete(schedule)
    await db.commit()


async def _get_or_404(schedule_id: str, db: AsyncSession) -> Schedule:
    result = await db.execute(select(Schedule).where(Schedule.schedule_id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id!r} not found")
    return schedule
