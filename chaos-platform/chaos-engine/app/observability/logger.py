"""Structured JSON logging for the chaos engine.

Every log line includes pod_name and, when available, experiment_id so
Loki queries like `{namespace="chaos-engine"} | json | experiment_id="abc"` work.
"""

import os
import json
import logging
from datetime import datetime, timezone

POD_NAME = os.getenv("POD_NAME", "unknown")


class JsonFormatter(logging.Formatter):
    _SKIP = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pod_name": POD_NAME,
        }
        for key, val in record.__dict__.items():
            if key not in self._SKIP:
                entry[key] = val
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("kubernetes").setLevel(logging.WARNING)
    logging.getLogger("aiokafka").setLevel(logging.WARNING)
