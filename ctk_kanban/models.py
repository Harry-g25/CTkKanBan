"""Public type definitions used by CTkKanbanBoard."""

from __future__ import annotations

from typing import Any, Callable, Literal, TypedDict


FieldType = Literal[
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
]


class _RequiredColumnDefinition(TypedDict):
    id: Any
    title: str


class ColumnDefinition(_RequiredColumnDefinition, total=False):
    """Dictionary shape accepted for a board column."""

    color: str | tuple[str, str] | None
    max_cards: int | None
    locked: bool
    show_count: bool
    show_add_button: bool
    show_menu: bool


class _RequiredCardDefinition(TypedDict):
    id: Any
    column: Any
    title: str


class CardDefinition(_RequiredCardDefinition, total=False):
    """Minimum card shape. Arbitrary additional keys are supported."""

    sort_order: int | float


class BoardData(TypedDict):
    """Snapshot of mutable board data for loading or persistence."""

    columns: list[dict[str, Any]]
    cards: list[dict[str, Any]]


class _RequiredFieldDefinition(TypedDict):
    key: str
    label: str


class FieldDefinition(_RequiredFieldDefinition, total=False):
    """Configuration for one custom card field."""

    type: FieldType
    required: bool
    default: Any
    placeholder: str
    options: list[Any] | tuple[Any, ...]
    show_on_card: bool
    show_in_form: bool
    searchable: bool
    filterable: bool
    sortable: bool
    read_only: bool
    validator: Callable[[Any, dict[str, Any]], bool | str | None]


class _RequiredContextMenuItem(TypedDict):
    label: str
    callback: Callable[[dict[str, Any]], Any]


class ContextMenuItem(_RequiredContextMenuItem, total=False):
    """Custom card context-menu action."""

    enabled: bool | Callable[[dict[str, Any]], bool]
    separator_before: bool


KanbanEvent = dict[str, Any]
KanbanCallback = Callable[[KanbanEvent], Any]
CardRenderer = Callable[[Any, dict[str, Any], list[dict[str, Any]], dict[str, Any]], None]


DEFAULT_FIELDS: list[dict[str, Any]] = [
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
        "sortable": True,
    },
    {
        "key": "description",
        "label": "Description",
        "type": "textarea",
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
    },
    {
        "key": "priority",
        "label": "Priority",
        "type": "badge",
        "show_on_card": True,
        "show_in_form": True,
        "filterable": True,
        "sortable": True,
    },
    {
        "key": "assignee",
        "label": "Assignee",
        "type": "text",
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
        "filterable": True,
    },
    {
        "key": "due_date",
        "label": "Due date",
        "type": "date",
        "show_on_card": True,
        "show_in_form": True,
        "filterable": True,
        "sortable": True,
    },
    {
        "key": "tags",
        "label": "Tags",
        "type": "tags",
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
        "filterable": True,
    },
]
