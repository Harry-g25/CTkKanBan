"""Schema definitions and value normalization for configurable card fields."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date, datetime
from typing import Any, Callable, Literal, TypeAlias, TypedDict, cast

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


class _Unset:
    def __repr__(self) -> str:
        return "<unset>"


_UNSET = _Unset()


def _field_label(key: str) -> str:
    """Turn a database-friendly key into a readable default label."""

    return key.replace("_", " ").replace("-", " ").strip().title()


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


@dataclass(frozen=True, slots=True)
class CardField:
    """Typed, concise definition for one card value and generated input.

    Unlike legacy field mappings, visible and searchable behavior is the
    convenience default. Use :class:`Field` when a fluent builder reads better.
    """

    key: str
    label: str | None = None
    type: FieldType = "text"
    card_role: CardRole = "metadata"
    required: bool = False
    default: Any = _UNSET
    placeholder: str = ""
    options: Sequence[Any] = ()
    show_on_card: bool = True
    show_in_editor: bool = True
    searchable: bool = True
    read_only: bool = False
    section: str = "Details"
    help_text: str = ""
    min: int | float | None = None
    max: int | float | None = None
    min_length: int | None = None
    max_length: int | None = None
    validator: FieldValidator | None = None
    formatter: FieldFormatter | None = None
    colors: Mapping[Any, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("CardField key must be a nonblank string")
        key = self.key.strip()
        if key in _RESERVED_KEYS:
            raise ValueError(f"CardField key {key!r} is reserved")
        label = _field_label(key) if self.label is None else self.label
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"CardField {key!r} label must be a nonblank string")
        if not isinstance(self.type, str) or self.type not in _FIELD_TYPES:
            raise ValueError(f"unsupported CardField type for {key!r}: {self.type!r}")
        if not isinstance(self.card_role, str) or self.card_role not in _CARD_ROLES:
            raise ValueError(f"unsupported card role for {key!r}: {self.card_role!r}")
        if isinstance(self.options, (str, bytes)) or not isinstance(self.options, Sequence):
            raise ValueError(f"CardField {key!r} options must be a sequence")
        if not isinstance(self.colors, Mapping):
            raise ValueError(f"CardField {key!r} colors must be a mapping")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "label", label.strip())
        object.__setattr__(self, "options", tuple(deepcopy(list(self.options))))
        object.__setattr__(self, "colors", dict(self.colors))
        if self.default is not _UNSET:
            object.__setattr__(self, "default", deepcopy(self.default))
        normalize_fields((self.to_definition(),))

    def to_definition(self) -> FieldDefinition:
        """Return the legacy mapping consumed by the existing field engine."""

        definition: dict[str, Any] = {
            "key": self.key,
            "label": cast(str, self.label),
            "type": self.type,
            "card_role": self.card_role,
            "required": self.required,
            "placeholder": self.placeholder,
            "options": tuple(deepcopy(list(self.options))),
            "show_on_card": self.show_on_card,
            "show_in_editor": self.show_in_editor,
            "searchable": self.searchable,
            "read_only": self.read_only,
            "section": self.section,
            "help_text": self.help_text,
        }
        if self.default is not _UNSET:
            definition["default"] = deepcopy(self.default)
        for name in ("min", "max", "min_length", "max_length"):
            value = getattr(self, name)
            if value is not None:
                definition[name] = value
        if self.validator is not None:
            definition["validator"] = self.validator
        if self.formatter is not None:
            definition["formatter"] = self.formatter
        if self.colors:
            definition["colors"] = dict(self.colors)
        return cast(FieldDefinition, definition)

    @classmethod
    def from_definition(
        cls,
        definition: CardField | Mapping[str, Any] | str,
    ) -> CardField:
        """Create a typed field from another field, mapping, or database key."""

        if isinstance(definition, cls):
            return definition
        if isinstance(definition, str):
            return cls(definition)
        if not isinstance(definition, Mapping):
            raise TypeError("Card fields must be CardField objects, mappings, or strings")
        if "key" not in definition:
            raise ValueError("Card field definitions require a 'key'")
        unknown = set(definition) - set(FieldDefinition.__optional_keys__) - set(
            FieldDefinition.__required_keys__
        )
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown field definition option(s): {names}")
        return cls(
            key=str(definition["key"]),
            label=definition.get("label"),
            type=cast(FieldType, definition.get("type", "text")),
            card_role=cast(CardRole, definition.get("card_role", "metadata")),
            required=cast(bool, definition.get("required", False)),
            default=definition.get("default", _UNSET),
            placeholder=str(definition.get("placeholder", "")),
            options=cast(Sequence[Any], definition.get("options", ())),
            show_on_card=cast(bool, definition.get("show_on_card", True)),
            show_in_editor=cast(bool, definition.get("show_in_editor", True)),
            searchable=cast(bool, definition.get("searchable", True)),
            read_only=cast(bool, definition.get("read_only", False)),
            section=str(definition.get("section", "Details")),
            help_text=str(definition.get("help_text", "")),
            min=cast(int | float | None, definition.get("min")),
            max=cast(int | float | None, definition.get("max")),
            min_length=cast(int | None, definition.get("min_length")),
            max_length=cast(int | None, definition.get("max_length")),
            validator=cast(FieldValidator | None, definition.get("validator")),
            formatter=cast(FieldFormatter | None, definition.get("formatter")),
            colors=cast(Mapping[Any, Any], definition.get("colors", {})),
        )


class Field(Mapping[str, Any]):
    """Fluent builder for a visible card value and its generated input."""

    def __init__(self, key: str) -> None:
        typed = CardField(key)
        self._data: dict[str, Any] = dict(typed.to_definition())

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def build(self) -> CardField:
        """Return an immutable typed copy of this builder."""

        return CardField.from_definition(self._data)

    def label(self, label: str) -> Field:
        self._data["label"] = label
        return self

    def text(self) -> Field:
        self._data["type"] = "text"
        return self

    def textarea(self) -> Field:
        self._data["type"] = "textarea"
        return self

    def number(self, *, minimum: float | None = None, maximum: float | None = None) -> Field:
        self._data["type"] = "number"
        return self._limits(minimum, maximum)

    def integer(self, *, minimum: int | None = None, maximum: int | None = None) -> Field:
        self._data["type"] = "integer"
        return self._limits(minimum, maximum)

    def select(self, options: Sequence[Any]) -> Field:
        self._data["type"] = "select"
        self._data["options"] = tuple(options)
        return self

    def multiselect(self, options: Sequence[Any]) -> Field:
        self._data["type"] = "multiselect"
        self._data["options"] = tuple(options)
        return self

    def date(self) -> Field:
        self._data["type"] = "date"
        return self

    def datetime(self) -> Field:
        self._data["type"] = "datetime"
        return self

    def checkbox(self) -> Field:
        self._data["type"] = "checkbox"
        return self

    def tags(self) -> Field:
        self._data["type"] = "tags"
        self._data["card_role"] = "tags"
        return self

    def title(self) -> Field:
        self._data.update(
            card_role="title",
            required=True,
            show_on_card=True,
            searchable=True,
        )
        return self

    def body(self) -> Field:
        self._data.update(card_role="body", show_on_card=True)
        return self

    def badge(self, *, colors: Mapping[Any, Any] | None = None) -> Field:
        self._data.update(card_role="badge", show_on_card=True)
        if colors is not None:
            self._data["colors"] = dict(colors)
        return self

    def metadata(self) -> Field:
        self._data.update(card_role="metadata", show_on_card=True)
        return self

    def card_only(self) -> Field:
        self._data.update(show_on_card=True, show_in_editor=False)
        return self

    def editor_only(self) -> Field:
        self._data.update(show_on_card=False, show_in_editor=True, card_role="hidden")
        return self

    def hide(self) -> Field:
        self._data.update(
            type="hidden",
            card_role="hidden",
            show_on_card=False,
            show_in_editor=False,
            searchable=False,
        )
        return self

    def read_only(self, enabled: bool = True) -> Field:
        self._data["read_only"] = enabled
        return self

    def required(self, enabled: bool = True) -> Field:
        self._data["required"] = enabled
        return self

    def searchable(self, enabled: bool = True) -> Field:
        self._data["searchable"] = enabled
        return self

    def section(self, title: str) -> Field:
        self._data["section"] = title
        return self

    def placeholder(self, text: str) -> Field:
        self._data["placeholder"] = text
        return self

    def help(self, text: str) -> Field:
        self._data["help_text"] = text
        return self

    def default(self, value: Any) -> Field:
        self._data["default"] = deepcopy(value)
        return self

    def length(self, *, minimum: int | None = None, maximum: int | None = None) -> Field:
        if minimum is not None:
            self._data["min_length"] = minimum
        if maximum is not None:
            self._data["max_length"] = maximum
        return self

    def validate(self, validator: FieldValidator) -> Field:
        self._data["validator"] = validator
        return self

    def fmt(self, formatter: FieldFormatter) -> Field:
        self._data["formatter"] = formatter
        return self

    def _limits(
        self,
        minimum: int | float | None,
        maximum: int | float | None,
    ) -> Field:
        if minimum is not None:
            self._data["min"] = minimum
        if maximum is not None:
            self._data["max"] = maximum
        return self


FieldInput: TypeAlias = str | CardField | Field | Mapping[str, Any]


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

def normalize_fields(
    fields: Iterable[FieldInput] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Validate concise/legacy definitions and return normalized mappings."""

    source: Iterable[FieldInput] = DEFAULT_FIELDS if fields is None else fields
    normalized: list[dict[str, Any]] = []
    known: set[str] = set()
    try:
        definitions = list(source)
    except TypeError as exc:
        raise ValueError("fields must be an iterable of field mappings") from exc

    for index, supplied in enumerate(definitions):
        raw: Mapping[str, Any]
        if isinstance(supplied, str):
            raw = Field(supplied)
        elif isinstance(supplied, CardField):
            raw = supplied.to_definition()
        else:
            raw = supplied
        if not isinstance(raw, Mapping):
            raise ValueError(f"field {index} must be a CardField, Field, mapping, or string")
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

    title_roles = [field for field in normalized if field["card_role"] == "title"]
    if not title_roles:
        normalized.insert(0, dict(DEFAULT_FIELDS[0]))
        title_roles = [normalized[0]]
    if len(title_roles) != 1:
        raise ValueError("exactly one field must use card_role='title'")
    title_field = title_roles[0]
    if title_field["type"] not in {"text", "textarea"}:
        raise ValueError("the title field must use text or textarea")
    title_field["required"] = True
    title_field["show_on_card"] = True
    title_field["card_role"] = "title"
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


def _field_value_name(field: Mapping[str, Any]) -> str:
    key = str(field["key"])
    label = str(field["label"])
    return label if label == key else f"{label} ({key})"


def normalize_field_value(
    field: Mapping[str, Any],
    raw_value: Any,
    card: Mapping[str, Any],
) -> Any:
    """Normalize and validate one value according to a field definition."""

    field_type = field["type"]
    value = raw_value

    if field_type in {"text", "textarea"}:
        if value is None:
            value = ""
        elif type(value) is not str:
            raise ValueError(f"{_field_value_name(field)} must be a string")
        value = value.strip()
    elif field_type == "date":
        if value in (None, ""):
            value = ""
        elif isinstance(value, datetime):
            raise ValueError(f"{_field_value_name(field)} must be a date without a time")
        elif isinstance(value, date):
            value = value.isoformat()
        elif isinstance(value, str):
            try:
                value = date.fromisoformat(value.strip()).isoformat()
            except ValueError as exc:
                raise ValueError(
                    f"{_field_value_name(field)} must use YYYY-MM-DD format"
                ) from exc
        else:
            raise ValueError(f"{_field_value_name(field)} must be a date or ISO date string")
    elif field_type == "datetime":
        if value in (None, ""):
            value = ""
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).isoformat()
            except ValueError as exc:
                raise ValueError(
                    f"{_field_value_name(field)} must be an ISO date and time"
                ) from exc
        else:
            raise ValueError(
                f"{_field_value_name(field)} must be a datetime or ISO datetime string"
            )
    elif field_type in {"number", "integer"}:
        if value in (None, ""):
            value = None
        elif isinstance(value, bool):
            raise ValueError(f"{_field_value_name(field)} must be a number")
        elif field_type == "integer":
            if type(value) is not int:
                try:
                    value = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{_field_value_name(field)} must be an integer") from exc
                if isinstance(raw_value, float) and not raw_value.is_integer():
                    raise ValueError(f"{_field_value_name(field)} must be an integer")
        else:
            if type(value) is not float:
                try:
                    value = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{_field_value_name(field)} must be a number") from exc
    elif field_type == "checkbox":
        if type(value) is not bool:
            raise ValueError(f"{_field_value_name(field)} must be a boolean")
    elif field_type in {"tags", "multiselect"}:
        if value is None:
            value = []
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise ValueError(f"{_field_value_name(field)} must be an iterable")
        items: list[Any] = []
        for item in value:
            normalized_item = item.strip() if isinstance(item, str) else deepcopy(item)
            if normalized_item in (None, ""):
                raise ValueError(f"{_field_value_name(field)} values must not be blank")
            if field_type == "tags" and (
                not isinstance(normalized_item, str) or "," in normalized_item
            ):
                raise ValueError(
                    f"{_field_value_name(field)} must contain strings without commas"
                )
            if normalized_item not in items:
                items.append(normalized_item)
        value = items
    elif field_type == "select":
        if type(value) not in (type(None), bool, int, float, str, bytes):
            value = deepcopy(value)
    else:
        value = deepcopy(value)

    empty = value is None or value == "" or value == []
    if field.get("required") and empty:
        raise ValueError(f"{_field_value_name(field)} is required")

    if field_type in {"select", "multiselect"}:
        options = field.get("options", ())
        if not empty and field_type == "select" and options and value not in options:
            raise ValueError(
                f"{_field_value_name(field)} must be one of: "
                f"{', '.join(map(str, options))}"
            )
        if field_type == "multiselect" and options:
            invalid = [item for item in value if item not in options]
            if invalid:
                raise ValueError(
                    f"{_field_value_name(field)} contains unsupported values: {invalid!r}"
                )
    if value is not None and field_type in {"number", "integer"}:
        if "min" in field and value < field["min"]:
            raise ValueError(
                f"{_field_value_name(field)} must be at least {field['min']}"
            )
        if "max" in field and value > field["max"]:
            raise ValueError(
                f"{_field_value_name(field)} must be at most {field['max']}"
            )
    if ("min_length" in field or "max_length" in field) and isinstance(value, (str, list)):
        if "min_length" in field and len(value) < field["min_length"]:
            raise ValueError(
                f"{_field_value_name(field)} must contain at least "
                f"{field['min_length']} characters/items"
            )
        if "max_length" in field and len(value) > field["max_length"]:
            raise ValueError(
                f"{_field_value_name(field)} must contain at most "
                f"{field['max_length']} characters/items"
            )

    validator = field.get("validator")
    if validator is not None:
        result = validator(value, card)
        if result is False:
            raise ValueError(f"{_field_value_name(field)} is invalid")
        if isinstance(result, str):
            raise ValueError(result or f"{_field_value_name(field)} is invalid")
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
    "CardField",
    "CardRole",
    "DEFAULT_FIELDS",
    "Field",
    "FieldDefinition",
    "FieldFormatter",
    "FieldInput",
    "FieldType",
    "FieldValidator",
    "default_for_field",
    "format_field_value",
    "normalize_field_value",
    "normalize_fields",
]
