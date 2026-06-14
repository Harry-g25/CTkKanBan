"""Helpers for consistent, future-friendly callback events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def create_event(event_type: str, source: str = "api", **payload: Any) -> dict[str, Any]:
    """Create a callback event with common metadata."""

    return {
        "type": event_type,
        **payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }


def cancellation_reason(result: Any) -> str | None:
    """Return a reason when a callback result requests cancellation."""

    if result is False:
        return "Action cancelled by callback"
    if isinstance(result, dict) and result.get("cancel") is True:
        return str(result.get("reason") or "Action cancelled by callback")
    return None

