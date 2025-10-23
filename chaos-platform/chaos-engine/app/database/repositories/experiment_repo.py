"""Repository for Experiment CRUD operations."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database.models import Experiment


class ExperimentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> Experiment:
        exp = Experiment(**kwargs)
        self.db.add(exp)
        await self.db.commit()
        await self.db.refresh(exp)
        return exp

    async def get(self, experiment_id: str) -> Optional[Experiment]:
        result = await self.db.execute(
            select(Experiment).where(Experiment.experiment_id == experiment_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100) -> List[Experiment]:
        result = await self.db.execute(
            select(Experiment).order_by(Experiment.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        experiment_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        result_summary: Optional[dict] = None,
    ) -> None:
        values: dict = {"status": status}
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if result_summary is not None:
            values["result_summary"] = result_summary

        await self.db.execute(
            update(Experiment)
            .where(Experiment.experiment_id == experiment_id)
            .values(**values)
        )
        await self.db.commit()

    async def delete(self, experiment_id: str) -> bool:
        exp = await self.get(experiment_id)
        if not exp:
            return False
        await self.db.delete(exp)
        await self.db.commit()
        return True
