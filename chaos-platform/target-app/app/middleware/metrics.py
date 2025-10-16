import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from prometheus_client import Counter, Histogram, Gauge

# ── Metric definitions ────────────────────────────────────────────────────────
# Module-level so all middleware instances share the same registry objects.

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ACTIVE_CONNECTIONS = Gauge(
    "active_connections",
    "Number of currently open HTTP connections",
)

DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Configured maximum database connection pool size",
)

# Incremented by the /error endpoint to track chaos-induced failures
CHAOS_ERRORS = Counter(
    "chaos_errors_total",
    "Total chaos-injected HTTP 500 errors from the /error endpoint",
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records per-request Prometheus metrics for every endpoint."""

    async def dispatch(self, request: Request, call_next):
        # Don't instrument the /metrics endpoint itself — it would inflate counts
        if request.url.path == "/metrics":
            return await call_next(request)

        ACTIVE_CONNECTIONS.inc()
        start = time.perf_counter()
        status_code = 500  # default if an unhandled exception escapes

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            ACTIVE_CONNECTIONS.dec()

            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=str(status_code),
            ).inc()

            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration)
