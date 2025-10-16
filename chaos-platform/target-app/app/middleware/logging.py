import os
import uuid
import time
import json
import logging
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

POD_NAME = os.getenv("POD_NAME", "unknown")


class JsonFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON object.

    This format is directly parseable by Loki, CloudWatch Logs Insights,
    and any log aggregator that supports structured JSON input.
    """

    # Fields that exist on every LogRecord but don't belong in the JSON output
    _SKIP = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pod_name": POD_NAME,
        }

        # Merge any extra= fields passed at the call site
        for key, value in record.__dict__.items():
            if key not in self._SKIP:
                entry[key] = value

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


def setup_logging() -> None:
    """Replace the default logging config with JSON-structured output."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Suppress noisy internal loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request as structured JSON including correlation ID and pod name."""

    def __init__(self, app):
        super().__init__(app)
        self.logger = logging.getLogger("target-app.access")

    async def dispatch(self, request: Request, call_next):
        # Propagate caller's correlation ID or generate a new one
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        start = time.perf_counter()

        response = await call_next(request)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        self.logger.info(
            "%s %s %d",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.url.query),
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "pod_name": POD_NAME,
                "correlation_id": correlation_id,
                "user_agent": request.headers.get("user-agent", ""),
            },
        )

        # Echo IDs back so callers can correlate client and server logs
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Pod-Name"] = POD_NAME

        return response
