"""Cron expression validation utilities."""

from datetime import datetime, timezone
from typing import Optional


def validate_cron(expression: str) -> Optional[str]:
    """Return None if valid, or an error message string if invalid."""
    try:
        from croniter import croniter
        if not croniter.is_valid(expression):
            return f"Invalid cron expression: {expression!r}"
        return None
    except Exception as exc:
        return str(exc)


def next_run_time(expression: str, after: Optional[datetime] = None) -> datetime:
    """Return the next datetime for the given cron expression."""
    from croniter import croniter
    base = after or datetime.now(timezone.utc)
    return croniter(expression, base).get_next(datetime)
