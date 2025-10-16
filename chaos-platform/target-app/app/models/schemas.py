from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any
from enum import Enum


class OrderStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderCreate(BaseModel):
    """Request body for POST /orders."""
    product_id: int = Field(gt=0, description="ID of the product to order")
    user_id: int = Field(gt=0, description="ID of the user placing the order")
    quantity: int = Field(gt=0, le=100, description="Units to purchase (1–100)")


class APIResponse(BaseModel):
    """Standard envelope for every API response.

    Every endpoint returns:
        {
            "status": "ok" | "error",
            "data":   <endpoint-specific payload>,
            "timestamp": "<ISO-8601 UTC>"
        }
    """
    status: str
    data: Any
    timestamp: str

    model_config = {"arbitrary_types_allowed": True}


def make_response(data: Any, status: str = "ok") -> dict:
    """Helper used by every router to build a consistent response envelope."""
    from datetime import timezone
    return {
        "status": status,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
