from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from opentelemetry import trace

from app.database.connection import get_db, ProductDB
from app.models.schemas import make_response

router = APIRouter()
tracer = trace.get_tracer("target-app.products")


def _serialize(p: ProductDB) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "price": p.price,
        "stock": p.stock,
        "category": p.category,
        "description": p.description,
        "created_at": p.created_at.isoformat(),
    }


@router.get("", summary="List all products")
async def list_products(db: AsyncSession = Depends(get_db)):
    """Returns all 20 seeded products.

    Under chaos load: this endpoint exercises the DB connection pool.
    Watch db_pool_size and active_connections gauges in Grafana when
    the load tester floods this endpoint concurrently.
    """
    with tracer.start_as_current_span("db.select_products"):
        result = await db.execute(select(ProductDB).order_by(ProductDB.id))
        products = result.scalars().all()

    return make_response([_serialize(p) for p in products])


@router.get("/{product_id}", summary="Get a single product")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Returns a single product by ID, or 404 if not found."""
    with tracer.start_as_current_span("db.select_product_by_id") as span:
        span.set_attribute("product.id", product_id)
        result = await db.execute(
            select(ProductDB).where(ProductDB.id == product_id)
        )
        product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=404,
            detail=make_response(
                {"message": f"Product {product_id} not found"},
                status="error",
            ),
        )

    return make_response(_serialize(product))
