"""Request executor — shared between in-process workers and standalone K8s worker pods.

Stateless: given a target URL and test config, execute HTTP requests and return results.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from opentelemetry import trace

logger = logging.getLogger("load-tester.worker.executor")
tracer = trace.get_tracer("load-tester.worker")

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass
class RequestResult:
    test_id: str
    worker_id: str
    timestamp: str
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    success: bool
    error: Optional[str] = None


async def execute_one(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    json_payload: Optional[dict],
    endpoint: str,
    test_id: str,
    worker_id: str,
) -> RequestResult:
    start = time.monotonic()
    status_code = 0
    success = False
    error = None

    with tracer.start_as_current_span("worker.request") as span:
        span.set_attribute("http.method", method)
        span.set_attribute("http.url", url)
        span.set_attribute("test_id", test_id)
        try:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_payload,
            )
            status_code = resp.status_code
            success = status_code < 500
            span.set_attribute("http.status_code", status_code)
        except httpx.TimeoutException as exc:
            error = f"timeout"
            span.set_attribute("error", True)
        except httpx.RequestError as exc:
            error = f"connection_error: {type(exc).__name__}"
            span.set_attribute("error", True)

    latency_ms = (time.monotonic() - start) * 1000
    return RequestResult(
        test_id=test_id,
        worker_id=worker_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        latency_ms=round(latency_ms, 2),
        success=success,
        error=error,
    )
