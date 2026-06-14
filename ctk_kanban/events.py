"""Helpers for consistent, future-friendly callback events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .contracts import coerce_mutation_result


def create_event(event_type: str, source: str = "api", **payload: Any) -> dict[str, Any]:
    """Create a callback event with common metadata."""

    return {
        "type": event_type,
        **payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "event_id": str(payload.get("event_id") or uuid4()),
        "transaction_id": str(payload.get("transaction_id") or uuid4()),
    }


def cancellation_reason(result: Any) -> str | None:
    """Return a reason when a callback result requests cancellation."""

    normalized = coerce_mutation_result(result)
    if normalized.cancelled:
        return normalized.reason or "Action cancelled by callback"
    return None
