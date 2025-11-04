"""Generates realistic HTTP requests against the target app endpoints.

Endpoint weight distribution (must sum to 1.0):
  60%  GET  /products       — browse product catalogue
  20%  GET  /orders         — check order history
  10%  POST /orders         — place a new order
  10%  GET  /stress         — chaos endpoint (intentionally slow/error-prone)

Each request carries:
  - X-Correlation-ID: unique per request for distributed tracing
  - X-Load-Test-ID:   test_id for filtering in Loki
  - Realistic User-Agent rotation
  - Think time (default 100ms) after each request to simulate real users
"""

import random
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "LoadTester/1.0 (chaos-platform; student-project)",
]

_ENDPOINTS: List[tuple] = [
    # (method, path, cumulative_weight, payload_builder_or_None)
    ("GET",  "/products",  0.60, None),
    ("GET",  "/orders",    0.80, None),
    ("POST", "/orders",    0.90, "_build_order"),
    ("GET",  "/stress",    1.00, None),
]


@dataclass
class HttpRequest:
    method: str
    url: str
    headers: Dict[str, str]
    json_payload: Optional[Dict[str, Any]]
    correlation_id: str
    endpoint: str            # path only, for labelling metrics
    test_id: str


def generate(target_url: str, test_id: str) -> HttpRequest:
    """Pick an endpoint according to weights and build a realistic request."""
    roll = random.random()
    chosen_method, chosen_path, _, payload_key = _ENDPOINTS[-1]
    for method, path, cumulative, pk in _ENDPOINTS:
        if roll <= cumulative:
            chosen_method, chosen_path, _, payload_key = method, path, cumulative, pk
            break

    correlation_id = str(uuid.uuid4())
    base = target_url.rstrip("/")

    # Add random query params for GET requests to avoid caching
    url = f"{base}{chosen_path}"
    if chosen_method == "GET" and chosen_path == "/products":
        url += f"?page={random.randint(1, 5)}&limit={random.choice([10, 20, 50])}"

    headers = {
        "X-Correlation-ID": correlation_id,
        "X-Load-Test-ID": test_id,
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }

    payload = None
    if payload_key == "_build_order":
        payload = {
            "user_id": random.randint(1, 10),
            "product_id": random.randint(1, 20),
            "quantity": random.randint(1, 5),
        }
        headers["Content-Type"] = "application/json"

    return HttpRequest(
        method=chosen_method,
        url=url,
        headers=headers,
        json_payload=payload,
        correlation_id=correlation_id,
        endpoint=chosen_path,
        test_id=test_id,
    )
