import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from opentelemetry import trace

from app.database.connection import get_db, OrderDB, ProductDB
from app.models.schemas import OrderCreate, make_response

router = APIRouter()
tracer = trace.get_tracer("target-app.orders")


def _serialize(o: OrderDB) -> dict:
    return {
        "id": o.id,
        "product_id": o.product_id,
        "user_id": o.user_id,
        "quantity": o.quantity,
        "total_price": round(o.total_price, 2),
        "status": o.status,
        "created_at": o.created_at.isoformat(),
    }


@router.post("", status_code=201, summary="Create an order")
async def create_order(order_in: OrderCreate, db: AsyncSession = Depends(get_db)):
    """Creates a new order with a 100ms simulated DB write delay.

    The 100ms sleep models real-world database write latency. Under
    concurrent load this adds up quickly — 100 rps × 100ms = connection
    pool saturation, which shows up as 503 errors in the metrics.
    """
    with tracer.start_as_current_span("db.create_order") as span:
        span.set_attribute("order.product_id", order_in.product_id)
        span.set_attribute("order.quantity", order_in.quantity)

        result = await db.execute(
            select(ProductDB).where(ProductDB.id == order_in.product_id)
        )
        product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=404,
            detail=make_response(
                {"message": f"Product {order_in.product_id} not found"},
                status="error",
            ),
        )

    # Simulate realistic DB write latency — intentional chaos target
    await asyncio.sleep(0.1)

    order = OrderDB(
        product_id=order_in.product_id,
        user_id=order_in.user_id,
        quantity=order_in.quantity,
        total_price=round(product.price * order_in.quantity, 2),
        status="pending",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return make_response(_serialize(order))


@router.get("", summary="List recent orders")
async def list_orders(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Returns the most recent orders (default: last 50)."""
    with tracer.start_as_current_span("db.list_orders"):
        result = await db.execute(
            select(OrderDB).order_by(OrderDB.created_at.desc()).limit(limit)
        )
        orders = result.scalars().all()

    return make_response([_serialize(o) for o in orders])
