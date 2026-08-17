"""Schema definitions and value normalization for configurable card fields."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Callable, Literal, TypedDict

FieldType = Literal[
    "text",
    "textarea",
    "number",
    "integer",
    "select",
    "multiselect",
    "date",
    "datetime",
    "checkbox",
    "tags",
    "hidden",
]
CardRole = Literal["title", "body", "badge", "tags", "metadata", "hidden"]
FieldValidator = Callable[[Any, Mapping[str, Any]], bool | str | None]
FieldFormatter = Callable[[Any, Mapping[str, Any]], str]


class _RequiredFieldDefinition(TypedDict):
    key: str
    label: str


class FieldDefinition(_RequiredFieldDefinition, total=False):
    """Public mapping shape used to define a card data field."""

    type: FieldType
    required: bool
    default: Any
    placeholder: str
    options: Sequence[Any]
    show_on_card: bool
    show_in_editor: bool
    searchable: bool
    read_only: bool
    section: str
    card_role: CardRole
    help_text: str
    min: int | float
    max: int | float
    min_length: int
    max_length: int
    validator: FieldValidator
    formatter: FieldFormatter
    colors: Mapping[Any, Any]


DEFAULT_FIELDS: tuple[FieldDefinition, ...] = (
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "placeholder": "Card title",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "section": "Details",
        "card_role": "title",
    },
    {
        "key": "description",
        "label": "Description",
        "type": "textarea",
        "default": "",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "section": "Details",
        "card_role": "body",
    },
    {
        "key": "priority",
        "label": "Priority",
        "type": "select",
        "default": "",
        "options": ("", "Low", "Medium", "High", "Critical"),
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "section": "Organisation",
        "card_role": "badge",
    },
    {
        "key": "tags",
        "label": "Tags",
        "type": "tags",
        "default": (),
        "placeholder": "Type a tag",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "section": "Organisation",
        "card_role": "tags",
    },
)

_FIELD_TYPES = {
    "text",
    "textarea",
    "number",
    "integer",
    "select",
    "multiselect",
    "date",
    "datetime",
    "checkbox",
    "tags",
    "hidden",
}
_CARD_ROLES = {"title", "body", "badge", "tags", "metadata", "hidden"}
_RESERVED_KEYS = {"id", "column", "column_id"}


def normalize_fields(
    fields: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Validate field definitions and return detached normalized mappings."""

    source: Iterable[Mapping[str, Any]] = DEFAULT_FIELDS if fields is None else fields
    normalized: list[dict[str, Any]] = []
    known: set[str] = set()
    try:
        definitions = list(source)
    except TypeError as exc:
        raise ValueError("fields must be an iterable of field mappings") from exc

    for index, raw in enumerate(definitions):
        if not isinstance(raw, Mapping):
            raise ValueError(f"field {index} must be a mapping")
        unknown = set(raw) - set(FieldDefinition.__optional_keys__) - set(
            FieldDefinition.__required_keys__
        )
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown field definition option(s): {names}")
        key = raw.get("key")
        label = raw.get("label")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("field key must be a nonblank string")
        key = key.strip()
        if key in _RESERVED_KEYS:
            raise ValueError(f"field key {key!r} is reserved")
        if key in known:
            raise ValueError(f"duplicate field key: {key!r}")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"field {key!r} label must be a nonblank string")

        field_type = raw.get("type", "text")
        if not isinstance(field_type, str):
            raise ValueError(f"field {key!r} type must be a string")
        if field_type not in _FIELD_TYPES:
            raise ValueError(f"unsupported field type for {key!r}: {field_type!r}")
        role = raw.get("card_role")
        if role is None:
            role = "metadata" if raw.get("show_on_card", False) else "hidden"
        if not isinstance(role, str):
            raise ValueError(f"field {key!r} card_role must be a string")
        if role not in _CARD_ROLES:
            raise ValueError(f"unsupported card role for {key!r}: {role!r}")
        for name in (
            "required",
            "show_on_card",
            "show_in_editor",
            "searchable",
            "read_only",
        ):
            if name in raw and not isinstance(raw[name], bool):
                raise ValueError(f"field {key!r} {name} must be a bool")

        value = dict(raw)
        value.update(
            {
                "key": key,
                "label": label.strip(),
                "type": field_type,
                "required": bool(raw.get("required", False)),
                "show_on_card": bool(raw.get("show_on_card", role != "hidden")),
                "show_in_editor": bool(raw.get("show_in_editor", field_type != "hidden")),
                "searchable": bool(raw.get("searchable", False)),
                "read_only": bool(raw.get("read_only", False)),
                "section": str(raw.get("section", "Details")).strip() or "Details",
                "card_role": role,
                "placeholder": str(raw.get("placeholder", "")),
                "help_text": str(raw.get("help_text", "")),
            }
        )
        if key == "title":
            if field_type not in {"text", "textarea"}:
                raise ValueError("the title field must use text or textarea")
            value["required"] = True
            value["show_on_card"] = True
            value["card_role"] = "title"

        for name in ("min", "max"):
            if name in value and (
                isinstance(value[name], bool) or not isinstance(value[name], (int, float))
            ):
                raise ValueError(f"field {key!r} {name} must be a number")
        for name in ("min_length", "max_length"):
            if name in value and (
                isinstance(value[name], bool)
                or not isinstance(value[name], int)
                or value[name] < 0
            ):
                raise ValueError(f"field {key!r} {name} must be a nonnegative integer")
        if "min" in value and "max" in value and value["min"] > value["max"]:
            raise ValueError(f"field {key!r} min must not exceed max")
        if (
            "min_length" in value
            and "max_length" in value
            and value["min_length"] > value["max_length"]
        ):
            raise ValueError(f"field {key!r} min_length must not exceed max_length")

        if "options" in value:
            options = value["options"]
            if isinstance(options, (str, bytes)) or not isinstance(options, Sequence):
                raise ValueError(f"field {key!r} options must be a sequence")
            value["options"] = tuple(deepcopy(list(options)))
        elif field_type in {"select", "multiselect"}:
            value["options"] = ()
        for name in ("validator", "formatter"):
            if name in value and not callable(value[name]):
                raise ValueError(f"field {key!r} {name} must be callable")
        if "colors" in value:
            if not isinstance(value["colors"], Mapping):
                raise ValueError(f"field {key!r} colors must be a mapping")
            value["colors"] = dict(value["colors"])

        if "default" in value:
            value["default"] = deepcopy(value["default"])
        normalized.append(value)
        known.add(key)

    if "title" not in known:
        normalized.insert(0, dict(DEFAULT_FIELDS[0]))
    title_roles = [field for field in normalized if field["card_role"] == "title"]
    if len(title_roles) != 1 or title_roles[0]["key"] != "title":
        raise ValueError("title must be the only field with card_role='title'")
    return tuple(normalized)


def default_for_field(field: Mapping[str, Any]) -> Any:
    """Return a detached default suitable for a new editor control."""

    if "default" in field:
        return deepcopy(field["default"])
    field_type = field["type"]
    if field_type in {"multiselect", "tags"}:
        return []
    if field_type == "checkbox":
        return False
    if field_type in {"number", "integer"}:
        return None
    return ""


def normalize_field_value(
    field: Mapping[str, Any],
    raw_value: Any,
    card: Mapping[str, Any],
) -> Any:
    """Normalize and validate one value according to a field definition."""

    key = str(field["key"])
    label = str(field["label"])
    name = label if label == key else f"{label} ({key})"
    field_type = field["type"]
    value = raw_value

    if field_type in {"text", "textarea"}:
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        value = value.strip()
    elif field_type == "date":
        if value in (None, ""):
            value = ""
        elif isinstance(value, datetime):
            raise ValueError(f"{name} must be a date without a time")
        elif isinstance(value, date):
            value = value.isoformat()
        elif isinstance(value, str):
            try:
                value = date.fromisoformat(value.strip()).isoformat()
            except ValueError as exc:
                raise ValueError(f"{name} must use YYYY-MM-DD format") from exc
        else:
            raise ValueError(f"{name} must be a date or ISO date string")
    elif field_type == "datetime":
        if value in (None, ""):
            value = ""
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).isoformat()
            except ValueError as exc:
                raise ValueError(f"{name} must be an ISO date and time") from exc
        else:
            raise ValueError(f"{name} must be a datetime or ISO datetime string")
    elif field_type in {"number", "integer"}:
        if value in (None, ""):
            value = None
        elif isinstance(value, bool):
            raise ValueError(f"{name} must be a number")
        elif field_type == "integer":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer") from exc
            if isinstance(raw_value, float) and not raw_value.is_integer():
                raise ValueError(f"{name} must be an integer")
        else:
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a number") from exc
    elif field_type == "checkbox":
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean")
    elif field_type in {"tags", "multiselect"}:
        if value is None:
            value = []
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise ValueError(f"{name} must be an iterable")
        items: list[Any] = []
        for item in value:
            normalized_item = item.strip() if isinstance(item, str) else deepcopy(item)
            if normalized_item in (None, ""):
                raise ValueError(f"{name} values must not be blank")
            if field_type == "tags" and (
                not isinstance(normalized_item, str) or "," in normalized_item
            ):
                raise ValueError(f"{name} must contain strings without commas")
            if normalized_item not in items:
                items.append(normalized_item)
        value = items
    elif field_type == "select":
        value = deepcopy(value)
    else:
        value = deepcopy(value)

    empty = value is None or value == "" or value == []
    if field.get("required") and empty:
        raise ValueError(f"{name} is required")

    options = tuple(field.get("options", ()))
    if not empty and field_type == "select" and options and value not in options:
        raise ValueError(f"{name} must be one of: {', '.join(map(str, options))}")
    if field_type == "multiselect" and options:
        invalid = [item for item in value if item not in options]
        if invalid:
            raise ValueError(f"{name} contains unsupported values: {invalid!r}")
    if value is not None and field_type in {"number", "integer"}:
        if "min" in field and value < field["min"]:
            raise ValueError(f"{name} must be at least {field['min']}")
        if "max" in field and value > field["max"]:
            raise ValueError(f"{name} must be at most {field['max']}")
    if isinstance(value, (str, list)):
        if "min_length" in field and len(value) < field["min_length"]:
            raise ValueError(f"{name} must contain at least {field['min_length']} characters/items")
        if "max_length" in field and len(value) > field["max_length"]:
            raise ValueError(f"{name} must contain at most {field['max_length']} characters/items")

    validator = field.get("validator")
    if validator is not None:
        result = validator(value, card)
        if result is False:
            raise ValueError(f"{name} is invalid")
        if isinstance(result, str):
            raise ValueError(result or f"{name} is invalid")
    return value


def format_field_value(
    field: Mapping[str, Any],
    value: Any,
    card: Mapping[str, Any],
) -> str:
    """Format a field value for its compact card representation."""

    formatter = field.get("formatter")
    if formatter is not None:
        return str(formatter(value, card))
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


__all__ = [
    "CardRole",
    "DEFAULT_FIELDS",
    "FieldDefinition",
    "FieldFormatter",
    "FieldType",
    "FieldValidator",
    "default_for_field",
    "format_field_value",
    "normalize_field_value",
    "normalize_fields",
]
