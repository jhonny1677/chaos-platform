"""
Tests for the products endpoints: GET /products and GET /products/{id}.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import ProductDB


@pytest_asyncio.fixture
async def product(db_session: AsyncSession) -> ProductDB:
    """Insert one known product into the test DB and return it."""
    p = ProductDB(
        name="Test Gadget",
        price=42.99,
        stock=50,
        category="Test",
        description="A product that exists only in tests",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_list_products_status_code(client: AsyncClient):
    response = await client.get("/products")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_products_envelope(client: AsyncClient):
    body = (await client.get("/products")).json()
    assert body["status"] == "ok"
    assert isinstance(body["data"], list)
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_list_products_seeded_data(client: AsyncClient):
    """The seed fixture should have loaded 20 products."""
    data = (await client.get("/products")).json()["data"]
    assert len(data) >= 20


@pytest.mark.asyncio
async def test_list_products_item_fields(client: AsyncClient):
    """Each product must have the documented fields."""
    products = (await client.get("/products")).json()["data"]
    assert len(products) > 0
    item = products[0]
    for field in ("id", "name", "price", "stock", "category", "description"):
        assert field in item, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_list_products_price_is_positive(client: AsyncClient):
    products = (await client.get("/products")).json()["data"]
    assert all(p["price"] > 0 for p in products)


@pytest.mark.asyncio
async def test_get_product_by_id(client: AsyncClient, product: ProductDB):
    response = await client.get(f"/products/{product.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == product.id
    assert data["name"] == "Test Gadget"
    assert data["price"] == pytest.approx(42.99)
    assert data["category"] == "Test"


@pytest.mark.asyncio
async def test_get_product_not_found(client: AsyncClient):
    response = await client.get("/products/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_product_not_found_envelope(client: AsyncClient):
    body = (await client.get("/products/999999")).json()
    # FastAPI wraps HTTPException detail — verify the nested structure
    assert "detail" in body


@pytest.mark.asyncio
async def test_get_product_invalid_id_type(client: AsyncClient):
    """Non-integer ID should return 422 Unprocessable Entity."""
    response = await client.get("/products/not-a-number")
    assert response.status_code == 422
