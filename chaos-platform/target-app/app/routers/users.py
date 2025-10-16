from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from opentelemetry import trace

from app.database.connection import get_db, UserDB
from app.models.schemas import make_response

router = APIRouter()
tracer = trace.get_tracer("target-app.users")


@router.get("", summary="List all users")
async def list_users(db: AsyncSession = Depends(get_db)):
    """Returns the 10 seeded fake users."""
    with tracer.start_as_current_span("db.select_users"):
        result = await db.execute(select(UserDB).order_by(UserDB.id))
        users = result.scalars().all()

    return make_response([
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "address": u.address,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ])
