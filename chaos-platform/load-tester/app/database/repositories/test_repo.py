"""Repository for LoadTest CRUD."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database.models import LoadTest


class TestRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> LoadTest:
        test = LoadTest(**kwargs)
        self.db.add(test)
        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def get(self, test_id: str) -> Optional[LoadTest]:
        result = await self.db.execute(
            select(LoadTest).where(LoadTest.test_id == test_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100) -> List[LoadTest]:
        result = await self.db.execute(
            select(LoadTest).order_by(LoadTest.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        test_id: str,
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
            update(LoadTest).where(LoadTest.test_id == test_id).values(**values)
        )
        await self.db.commit()

    async def delete(self, test_id: str) -> bool:
        test = await self.get(test_id)
        if not test:
            return False
        await self.db.delete(test)
        await self.db.commit()
        return True
