"""Small data and widget helpers shared by the package."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Iterable, Iterator
from uuid import uuid4


def clone(value: Any) -> Any:
    """Deep-copy public data before storing it or returning it to callers."""

    return deepcopy(value)


def display_value(value: Any) -> str:
    """Convert a card value to concise display text."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


def searchable_text(value: Any) -> str:
    """Flatten a value for case-insensitive searching."""

    return display_value(value).casefold()


def parse_temporal(value: Any) -> datetime | None:
    """Best-effort conversion of dates and ISO strings to a datetime."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
            except ValueError:
                return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def comparable_value(value: Any) -> tuple[int, int, Any]:
    """Produce a stable sort value across common card field types."""

    if value is None or value == "":
        return (1, 0, "")
    parsed = parse_temporal(value)
    if parsed is not None and isinstance(value, (date, datetime, str)):
        return (0, 1, parsed)
    if isinstance(value, bool):
        return (0, 0, int(value))
    if isinstance(value, (int, float)):
        if isfinite(value):
            return (0, 0, value)
        return (0, 3, str(value))
    if isinstance(value, str):
        return (0, 2, value.casefold())
    return (0, 3, searchable_text(value))


def parse_list_value(value: Any) -> list[str]:
    """Normalize form values for tag and multiselect fields."""

    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def generate_card_id(existing_ids: Iterable[Any]) -> Any:
    """Generate a practical ID that follows the board's existing ID style."""

    existing = set(existing_ids)
    if existing and all(isinstance(item, int) and not isinstance(item, bool) for item in existing):
        return max(existing, default=0) + 1
    candidate = str(uuid4())
    while candidate in existing:
        candidate = str(uuid4())
    return candidate


def iter_widget_tree(widget: Any) -> Iterator[Any]:
    """Yield a widget and every descendant currently attached to it."""

    yield widget
    for child in widget.winfo_children():
        yield from iter_widget_tree(child)
