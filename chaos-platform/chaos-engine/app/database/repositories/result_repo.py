"""Repository for ExperimentResult CRUD operations."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import ExperimentResult


class ResultRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> ExperimentResult:
        result = ExperimentResult(**kwargs)
        self.db.add(result)
        await self.db.commit()
        await self.db.refresh(result)
        return result

    async def get(self, result_id: str) -> Optional[ExperimentResult]:
        res = await self.db.execute(
            select(ExperimentResult).where(ExperimentResult.result_id == result_id)
        )
        return res.scalar_one_or_none()

    async def get_by_experiment(self, experiment_id: str) -> Optional[ExperimentResult]:
        res = await self.db.execute(
            select(ExperimentResult)
            .where(ExperimentResult.experiment_id == experiment_id)
            .order_by(ExperimentResult.started_at.desc())
        )
        return res.scalars().first()

    async def list_all(self, limit: int = 100) -> List[ExperimentResult]:
        res = await self.db.execute(
            select(ExperimentResult)
            .order_by(ExperimentResult.started_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    async def complete(self, result_id: str, **kwargs) -> None:
        result = await self.get(result_id)
        if result:
            for key, value in kwargs.items():
                setattr(result, key, value)
            result.completed_at = datetime.utcnow()
            await self.db.commit()
