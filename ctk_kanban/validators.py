"""Validation and normalization for public Kanban data."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any, Iterable, Mapping

from .exceptions import (
    KanbanDuplicateIDError,
    KanbanUnknownColumnError,
    KanbanValidationError,
)
from .models import DEFAULT_FIELDS
from .utils import parse_temporal

SUPPORTED_FIELD_TYPES = {
    "text",
    "textarea",
    "number",
    "select",
    "multiselect",
    "date",
    "datetime",
    "checkbox",
    "tag",
    "tags",
    "badge",
    "hidden",
}


def _validate_identifier(value: Any, label: str) -> None:
    if value is None or value == "":
        raise KanbanValidationError(f"{label} is required")
    try:
        hash(value)
    except TypeError as exc:
        raise KanbanValidationError(f"{label} must be hashable") from exc
    if isinstance(value, float) and not isfinite(value):
        raise KanbanValidationError(f"{label} must be finite")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KanbanValidationError(f"{label} must be a dictionary-like mapping")
    return value


def _iter_collection(value: Any, label: str) -> Iterable[Any]:
    """Return a validated non-string iterable for collection APIs."""

    if isinstance(value, (str, bytes, Mapping)):
        raise KanbanValidationError(f"{label} must be an iterable of mappings")
    try:
        return iter(value)
    except TypeError as exc:
        raise KanbanValidationError(f"{label} must be an iterable of mappings") from exc


def validate_column(column: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one column definition."""

    source = _require_mapping(column, "Column")
    if "id" not in source:
        raise KanbanValidationError("Column is missing required field 'id'")
    _validate_identifier(source["id"], "Column 'id'")
    if not str(source.get("title", "")).strip():
        raise KanbanValidationError(f"Column {source['id']!r} is missing required field 'title'")
    normalized = deepcopy(dict(source))
    normalized["title"] = str(normalized["title"]).strip()
    normalized.setdefault("color", None)
    normalized.setdefault("max_cards", None)
    normalized.setdefault("locked", False)
    max_cards = normalized["max_cards"]
    if max_cards is not None and (not isinstance(max_cards, int) or isinstance(max_cards, bool) or max_cards < 0):
        raise KanbanValidationError("Column 'max_cards' must be a non-negative integer or None")
    for option_name in ("locked", "show_count", "show_add_button", "show_menu"):
        if option_name in normalized and not isinstance(normalized[option_name], bool):
            raise KanbanValidationError(
                f"Column {source['id']!r} {option_name!r} must be a boolean"
            )
    return normalized


def validate_columns(columns: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate a complete ordered column collection."""

    normalized: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for column in _iter_collection(columns, "Columns"):
        item = validate_column(column)
        if item["id"] in seen:
            raise KanbanDuplicateIDError(f"Duplicate column ID: {item['id']!r}")
        seen.add(item["id"])
        normalized.append(item)
    return normalized


def validate_card(card: Mapping[str, Any], column_ids: set[Any]) -> dict[str, Any]:
    """Validate one card while preserving all custom fields."""

    source = _require_mapping(card, "Card")
    for key in ("id", "column", "title"):
        if key not in source or source[key] is None or (key != "title" and source[key] == ""):
            raise KanbanValidationError(f"Card is missing required field {key!r}")
    _validate_identifier(source["id"], "Card 'id'")
    _validate_identifier(source["column"], "Card 'column'")
    if not str(source["title"]).strip():
        raise KanbanValidationError(f"Card {source['id']!r} has an empty title")
    if source["column"] not in column_ids:
        raise KanbanUnknownColumnError(
            f"Card {source['id']!r} references unknown column {source['column']!r}"
        )
    normalized = deepcopy(dict(source))
    normalized["title"] = str(normalized["title"]).strip()
    sort_order = normalized.get("sort_order")
    if sort_order is not None:
        if not isinstance(sort_order, (int, float)) or isinstance(sort_order, bool):
            raise KanbanValidationError("Card 'sort_order' must be numeric when supplied")
        if not isfinite(sort_order):
            raise KanbanValidationError("Card 'sort_order' must be finite")
    return normalized


def validate_cards(cards: Iterable[Mapping[str, Any]], column_ids: set[Any]) -> list[dict[str, Any]]:
    """Validate a complete card collection and reject duplicate IDs."""

    normalized: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for card in _iter_collection(cards, "Cards"):
        item = validate_card(card, column_ids)
        if item["id"] in seen:
            raise KanbanDuplicateIDError(f"Duplicate card ID: {item['id']!r}")
        seen.add(item["id"])
        normalized.append(item)
    return normalized


def validate_field(field: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and fill defaults for one field definition."""

    source = _require_mapping(field, "Field")
    key = str(source.get("key", "")).strip()
    if not key:
        raise KanbanValidationError("Field is missing required field 'key'")
    field_type = str(source.get("type", "text")).lower()
    if field_type not in SUPPORTED_FIELD_TYPES:
        raise KanbanValidationError(f"Unsupported field type {field_type!r} for field {key!r}")
    validator = source.get("validator")
    normalized = deepcopy({key: value for key, value in source.items() if key != "validator"})
    if "validator" in source:
        normalized["validator"] = validator
    normalized["key"] = key
    label = str(normalized.get("label") or key.replace("_", " ").title()).strip()
    normalized["label"] = label or key.replace("_", " ").title()
    normalized["type"] = field_type
    normalized.setdefault("required", False)
    normalized.setdefault("default", None)
    normalized.setdefault("placeholder", "")
    normalized.setdefault("options", [])
    normalized.setdefault("show_on_card", field_type != "hidden")
    normalized.setdefault("show_in_form", field_type != "hidden")
    normalized.setdefault("searchable", False)
    normalized.setdefault("filterable", False)
    normalized.setdefault("sortable", False)
    normalized.setdefault("read_only", False)
    normalized.setdefault("help_text", "")
    normalized.setdefault("checkbox_text", "")
    normalized.setdefault("empty_value", None)
    for option_name in (
        "required",
        "show_on_card",
        "show_in_form",
        "searchable",
        "filterable",
        "sortable",
        "read_only",
    ):
        if not isinstance(normalized[option_name], bool):
            raise KanbanValidationError(f"Field {key!r} {option_name!r} must be a boolean")
    if field_type in {"select", "multiselect"} and not isinstance(normalized["options"], (list, tuple)):
        raise KanbanValidationError(f"Field {key!r} options must be a list or tuple")
    if field_type in {"select", "multiselect"}:
        display_values = [str(option) for option in normalized["options"]]
        if len(display_values) != len(set(display_values)):
            raise KanbanValidationError(
                f"Field {key!r} options must have unique text representations"
            )
    if validator is not None and not callable(validator):
        raise KanbanValidationError(f"Field {key!r} validator must be callable or None")
    if key == "title":
        if field_type not in {"text", "textarea"}:
            raise KanbanValidationError("Field 'title' must use type 'text' or 'textarea'")
        normalized["required"] = True
    default = normalized.get("default")
    if default not in (None, "", []) and normalized["options"]:
        if field_type == "multiselect":
            if isinstance(default, (str, bytes)) or not isinstance(default, (list, tuple, set)):
                raise KanbanValidationError(f"Field {key!r} default must be a collection")
            invalid = [item for item in default if item not in normalized["options"]]
            if invalid:
                raise KanbanValidationError(
                    f"Field {key!r} has invalid default value {invalid[0]!r}"
                )
        elif field_type == "select" and default not in normalized["options"]:
            raise KanbanValidationError(f"Field {key!r} has invalid default value {default!r}")
    return normalized


def validate_fields(fields: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate field definitions or return the package defaults."""

    source = DEFAULT_FIELDS if fields is None else fields
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in _iter_collection(source, "Fields"):
        item = validate_field(field)
        if item["key"] in seen:
            raise KanbanDuplicateIDError(f"Duplicate field key: {item['key']!r}")
        seen.add(item["key"])
        normalized.append(item)
    if "title" not in seen:
        normalized.insert(0, validate_field(DEFAULT_FIELDS[0]))
    return normalized


def validate_card_values(card: Mapping[str, Any], fields: Iterable[Mapping[str, Any]]) -> None:
    """Apply required, option, and custom validation rules to card values."""

    for field in fields:
        key = str(field["key"])
        value = card.get(key)
        if field.get("required") and (value is None or value == "" or value == []):
            raise KanbanValidationError(f"{field['label']} is required")
        field_type = field.get("type")
        if value not in (None, "", []):
            if field_type == "number":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise KanbanValidationError(f"{field['label']} must be numeric")
                if not isfinite(value):
                    raise KanbanValidationError(f"{field['label']} must be finite")
            elif field_type == "checkbox" and not isinstance(value, bool):
                raise KanbanValidationError(f"{field['label']} must be a boolean")
            elif field_type in {"multiselect", "tags"} and (
                isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set))
            ):
                raise KanbanValidationError(f"{field['label']} must be a list, tuple, or set")
            elif field_type in {"date", "datetime"} and parse_temporal(value) is None:
                raise KanbanValidationError(f"{field['label']} must be a valid ISO date or datetime")
            if isinstance(value, (int, float)):
                minimum = field.get("min")
                maximum = field.get("max")
                if minimum is not None and value < minimum:
                    raise KanbanValidationError(f"{field['label']} must be at least {minimum}")
                if maximum is not None and value > maximum:
                    raise KanbanValidationError(f"{field['label']} must be at most {maximum}")
            if isinstance(value, str):
                minimum_length = field.get("min_length")
                maximum_length = field.get("max_length")
                if minimum_length is not None and len(value) < minimum_length:
                    raise KanbanValidationError(
                        f"{field['label']} must be at least {minimum_length} characters"
                    )
                if maximum_length is not None and len(value) > maximum_length:
                    raise KanbanValidationError(
                        f"{field['label']} must be at most {maximum_length} characters"
                    )
        options = field.get("options") or []
        if value not in (None, "", []) and options:
            if field_type == "multiselect":
                selected = value if isinstance(value, (list, tuple, set)) else []
                invalid = [item for item in selected if item not in options]
                if invalid:
                    raise KanbanValidationError(f"Invalid {field['label']} value: {invalid[0]!r}")
            elif field_type == "select" and value not in options:
                raise KanbanValidationError(f"Invalid {field['label']} value: {value!r}")
        validator = field.get("validator")
        if callable(validator):
            result = validator(value, deepcopy(dict(card)))
            if result is False:
                raise KanbanValidationError(f"Invalid value for {field['label']}")
            if isinstance(result, str) and result:
                raise KanbanValidationError(result)


def validate_context_menu_items(items: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate custom card context-menu definitions."""

    if items is None:
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(_iter_collection(items, "Context menu items")):
        source = _require_mapping(item, f"Context menu item {index}")
        label = str(source.get("label", "")).strip()
        if not label:
            raise KanbanValidationError(f"Context menu item {index} requires a label")
        callback = source.get("callback")
        if not callable(callback):
            raise KanbanValidationError(
                f"Context menu item {label!r} callback must be callable"
            )
        enabled = source.get("enabled", True)
        if not isinstance(enabled, bool) and not callable(enabled):
            raise KanbanValidationError(
                f"Context menu item {label!r} enabled must be a boolean or callable"
            )
        separator_before = source.get("separator_before", False)
        if not isinstance(separator_before, bool):
            raise KanbanValidationError(
                f"Context menu item {label!r} separator_before must be a boolean"
            )
        normalized.append(
            {
                **dict(source),
                "label": label,
                "callback": callback,
                "enabled": enabled,
                "separator_before": separator_before,
            }
        )
    return normalized
