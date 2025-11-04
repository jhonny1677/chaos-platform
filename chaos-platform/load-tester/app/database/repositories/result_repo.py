"""Repository for TestResult snapshots."""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import TestResult


class ResultRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_snapshot(self, **kwargs) -> TestResult:
        result = TestResult(**kwargs)
        self.db.add(result)
        await self.db.commit()
        return result

    async def list_for_test(self, test_id: str, limit: int = 3600) -> List[TestResult]:
        res = await self.db.execute(
            select(TestResult)
            .where(TestResult.test_id == test_id)
            .order_by(TestResult.snapshot_at.asc())
            .limit(limit)
        )
        return list(res.scalars().all())

    async def latest_for_test(self, test_id: str) -> Optional[TestResult]:
        res = await self.db.execute(
            select(TestResult)
            .where(TestResult.test_id == test_id)
            .order_by(TestResult.snapshot_at.desc())
        )
        return res.scalars().first()
