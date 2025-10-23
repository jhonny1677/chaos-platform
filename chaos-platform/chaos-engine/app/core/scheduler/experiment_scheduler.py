"""Experiment Scheduler — asyncio background task that fires experiments on cron schedules.

The scheduler polls the `schedules` table every 30 seconds for enabled schedules
whose `next_run_at` is in the past. For each due schedule it creates an
Experiment row and hands it to ChaosManager. The schedule's `next_run_at` is
then advanced using croniter.

Design: one asyncio.Task runs the poll loop. Experiments themselves run in
separate Tasks so a slow experiment doesn't delay the next scheduled fire.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("chaos-engine.scheduler")

_poll_interval = 30  # seconds


class ExperimentScheduler:
    def __init__(self, get_db_session, chaos_manager_factory):
        """
        Args:
            get_db_session:      Async context manager that yields an AsyncSession.
            chaos_manager_factory: Callable that takes a session and returns ChaosManager.
        """
        self._get_db_session = get_db_session
        self._chaos_manager_factory = chaos_manager_factory
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="experiment-scheduler")
        logger.info("Experiment scheduler started (poll interval=%ds)", _poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Experiment scheduler stopped")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.error("Scheduler poll error: %s", exc)
            await asyncio.sleep(_poll_interval)

    async def _tick(self) -> None:
        from app.database.repositories.experiment_repo import ExperimentRepository
        from app.database.repositories.result_repo import ResultRepository

        async with self._get_db_session() as session:
            from sqlalchemy import select
            from app.database.models import Schedule

            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(Schedule).where(
                    Schedule.enabled == True,
                    Schedule.next_run_at <= now,
                )
            )
            due_schedules = result.scalars().all()

            for schedule in due_schedules:
                logger.info(
                    "Schedule '%s' due — firing experiment (chaos_type=%s)",
                    schedule.name, schedule.chaos_type,
                )
                asyncio.create_task(
                    self._fire_scheduled_experiment(schedule),
                    name=f"scheduled-{schedule.schedule_id[:8]}",
                )
                # Advance next_run_at immediately to prevent duplicate fires
                schedule.next_run_at = _next_run(schedule.cron_expression, now)
                schedule.last_run_at = now
                await session.commit()

    async def _fire_scheduled_experiment(self, schedule) -> None:
        from app.database.models import Experiment
        from app.database.repositories.experiment_repo import ExperimentRepository
        from app.database.repositories.result_repo import ResultRepository
        from app.messaging.kafka_producer import KafkaProducer
        from app.messaging.event_publisher import EventPublisher
        from app.core.steady_state.validator import SteadyStateValidator
        import os

        async with self._get_db_session() as session:
            exp_repo = ExperimentRepository(session)
            result_repo = ResultRepository(session)

            experiment = await exp_repo.create(
                name=f"Scheduled: {schedule.name}",
                description=f"Auto-triggered by schedule {schedule.schedule_id}",
                target_namespace=schedule.target_namespace,
                target_label_selector=schedule.target_label_selector,
                chaos_type=schedule.chaos_type,
                parameters=schedule.parameters,
                steady_state_thresholds=schedule.steady_state_thresholds,
                schedule_id=schedule.schedule_id,
                status="pending",
            )

            manager = self._chaos_manager_factory(session)
            await manager.run_experiment(experiment)


def _next_run(cron_expression: str, after: datetime) -> datetime:
    from croniter import croniter
    cron = croniter(cron_expression, after)
    return cron.get_next(datetime)
