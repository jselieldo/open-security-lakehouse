"""Optional, conservative event-time bounds for normalized Parquet objects."""

from datetime import UTC, datetime


def event_time_bounds(values: list[datetime]) -> dict[str, str]:
    return {
        "min_event_time": min(values).astimezone(UTC).isoformat(),
        "max_event_time": max(values).astimezone(UTC).isoformat(),
    }


def outside_time_range(
    bounds: object, start: datetime | None, end: datetime | None
) -> bool:
    """Unknown or malformed indexes must never remove a candidate object."""
    if not isinstance(bounds, dict):
        return False
    try:
        low = datetime.fromisoformat(bounds["min_event_time"])
        high = datetime.fromisoformat(bounds["max_event_time"])
        if low.tzinfo is None or high.tzinfo is None or low > high:
            return False
        return (start is not None and high < start) or (end is not None and low > end)
    except (KeyError, TypeError, ValueError):
        return False
