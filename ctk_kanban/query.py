"""Reusable client and adapter-side search, filter, and sort helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from .utils import comparable_value, parse_temporal, searchable_text


def card_matches_search(card: Mapping[str, Any], query: str, keys: Iterable[str] | None = None) -> bool:
    text = str(query or "").strip().casefold()
    if not text:
        return True
    values = keys or card.keys()
    return any(text in searchable_text(card.get(key)) for key in values)


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "contains":
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return searchable_text(expected) in searchable_text(actual)
    if operator == "not_contains":
        return not _compare(actual, "contains", expected)
    if operator == "in":
        return actual in expected
    if operator == "not_in":
        return actual not in expected
    if operator == "empty":
        return actual in (None, "", [])
    if operator == "not_empty":
        return actual not in (None, "", [])
    left = comparable_value(actual)
    right = comparable_value(expected)
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "between" and isinstance(expected, (list, tuple)) and len(expected) == 2:
        return comparable_value(expected[0]) <= left <= comparable_value(expected[1])
    return actual == expected


def card_matches_filters(
    card: Mapping[str, Any],
    filters: Mapping[str, Any],
    *,
    completion_field: str = "completed",
    completed_columns: Iterable[Any] = (),
    now: datetime | None = None,
) -> bool:
    current_time = now or datetime.now(timezone.utc)
    completed_column_ids = set(completed_columns)
    for key, condition in filters.items():
        if key == "overdue_only":
            if condition:
                if card.get(completion_field) or card.get("column") in completed_column_ids:
                    return False
                raw_due = card.get("due_date")
                if isinstance(raw_due, date) and not isinstance(raw_due, datetime):
                    overdue = raw_due < current_time.date()
                elif isinstance(raw_due, str) and len(raw_due.strip()) == 10:
                    try:
                        overdue = date.fromisoformat(raw_due.strip()) < current_time.date()
                    except ValueError:
                        overdue = False
                else:
                    due = parse_temporal(raw_due)
                    overdue = due is not None and due.astimezone(current_time.tzinfo) < current_time
                if not overdue:
                    return False
            continue
        actual = card.get("column") if key in {"column", "status"} else card.get(key)
        if callable(condition):
            if not condition(actual, dict(card)):
                return False
            continue
        if isinstance(condition, Mapping) and "op" in condition:
            if not _compare(actual, str(condition["op"]), condition.get("value")):
                return False
            continue
        if isinstance(actual, (list, tuple, set)):
            expected = condition if isinstance(condition, (list, tuple, set)) else [condition]
            if not any(item in actual for item in expected):
                return False
        elif isinstance(condition, (list, tuple, set)):
            if actual not in condition:
                return False
        elif actual != condition:
            return False
    return True


def sort_cards(cards: Iterable[dict[str, Any]], sort_key: str, reverse: bool = False) -> list[dict[str, Any]]:
    sort_key = {
        "created_date": "created_at",
        "updated_date": "updated_at",
    }.get(sort_key, sort_key)
    result = list(cards)
    key: Callable[[dict[str, Any]], Any]
    if sort_key == "manual":

        def key(card: dict[str, Any]) -> Any:
            return comparable_value(card.get("sort_order"))
    elif sort_key == "priority":
        ranking = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def key(card: dict[str, Any]) -> Any:
            return (
                ranking.get(str(card.get("priority", "")).casefold(), 99),
                searchable_text(card.get("priority")),
            )
    else:

        def key(card: dict[str, Any]) -> Any:
            value = card.get(sort_key)
            if sort_key == "created_at" and "created_at" not in card:
                value = card.get("created_date")
            elif sort_key == "updated_at" and "updated_at" not in card:
                value = card.get("updated_date")
            return comparable_value(value)

    return sorted(result, key=key, reverse=reverse)
