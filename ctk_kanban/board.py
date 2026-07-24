"""Main CTkKanbanBoard widget and public data API."""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from datetime import date, datetime, timezone
from math import isfinite
from tkinter import messagebox
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

import customtkinter as ctk

from .card import CTkKanbanCard
from .column import CTkKanbanColumn
from .contracts import CardQuery, MutationEvent, MutationResult, PersistenceState, coerce_mutation_result
from .datasource import KanbanDataSource, PersistenceCoordinator, RetryPolicy
from .dialogs import CardFormDialog, CardFormFrame, FilterDialog
from .drag import DragDropMixin
from .events import cancellation_reason, create_event
from .exceptions import (
    KanbanDuplicateIDError,
    KanbanPersistenceError,
    KanbanUnknownColumnError,
    KanbanValidationError,
)
from .models import BoardData, CardRenderer, ContextMenuItem, KanbanCallback
from .query import card_matches_filters
from .rendering import RenderingMixin
from .themes import DEFAULT_PRIORITY_COLORS, merge_theme
from .utils import (
    clone,
    comparable_value,
    generate_card_id,
    iter_widget_tree,
    parse_temporal,
    searchable_text,
)
from .validators import (
    validate_card,
    validate_card_values,
    validate_cards,
    validate_column,
    validate_columns,
    validate_context_menu_items,
    validate_fields,
)

_SORT_KEY_ALIASES = {
    "created_date": "created_at",
    "updated_date": "updated_at",
}

_HistoryEntry = tuple[dict[str, Any], dict[str, Any]]
_HistorySnapshot = tuple[list[_HistoryEntry], list[_HistoryEntry]]


def _canonical_sort_key(sort_key: str) -> str:
    """Return the persisted timestamp field for legacy date sort aliases."""

    return _SORT_KEY_ALIASES.get(sort_key, sort_key)


def _card_sort_value(card: Mapping[str, Any], sort_key: str) -> Any:
    """Read canonical timestamps while retaining legacy-record compatibility."""

    value = card.get(sort_key)
    if value is None and sort_key == "created_at":
        return card.get("created_date")
    if value is None and sort_key == "updated_at":
        return card.get("updated_date")
    return value


def _validated_int(value: Any, name: str, *, minimum: int) -> int:
    """Validate integer constructor options without silently truncating values."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise KanbanValidationError(f"{name} must be an integer")
    if value < minimum:
        raise KanbanValidationError(f"{name} must be at least {minimum}")
    return value


def _validated_opacity(value: Any) -> float:
    """Validate and clamp drag-preview opacity to the supported range."""

    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
        raise KanbanValidationError("drag_preview_opacity must be a finite number")
    return min(1.0, max(0.1, float(value)))


def _validated_index(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise KanbanValidationError(f"{name} must be an integer")
    return value


def _validated_mapping(value: Any, name: str) -> Mapping[str, Any] | None:
    if value is not None and not isinstance(value, Mapping):
        raise KanbanValidationError(f"{name} must be a mapping or None")
    return value


class CTkKanbanBoard(RenderingMixin, DragDropMixin, ctk.CTkFrame):
    """A reusable, configurable Kanban board for CustomTkinter.

    The board owns defensive copies of column and card dictionaries. All
    persistent operations are exposed through callbacks so applications can
    save to any database. Use ``on_data_changed`` for a single full-snapshot
    persistence hook, or the more specific mutation callbacks for fine-grained
    control. Returning ``False`` or ``{"cancel": True}`` from a mutation
    callback restores the previous board state.
    """

    def __init__(
        self,
        master: Any,
        columns: Iterable[Mapping[str, Any]] | None = None,
        cards: Iterable[Mapping[str, Any]] | None = None,
        fields: Iterable[Mapping[str, Any]] | None = None,
        *,
        # Layout
        enable_horizontal_scroll: bool = True,
        enable_column_scroll: bool = True,
        column_width: int = 300,
        column_height: int = 600,
        column_gap: int = 12,
        board_padding: int | None = None,
        responsive_columns: bool = True,
        min_column_width: int = 240,
        max_column_width: int = 420,
        column_control_size: int = 30,
        # Toolbar
        show_toolbar: bool = True,
        show_search: bool = True,
        show_filter_button: bool = True,
        show_sort_button: bool = True,
        show_add_card_button: bool = True,
        show_clear_filters_button: bool = True,
        # Columns
        show_card_count: bool = True,
        show_column_add_button: bool = True,
        show_column_menu: bool = True,
        enforce_column_limits: bool = True,
        enable_column_drag: bool = True,
        # Cards
        card_mode: str = "detailed",
        card_density: str = "comfortable",
        show_drag_handles: bool = True,
        max_visible_tags: int = 6,
        tags_per_row: int = 3,
        enable_card_hover: bool = True,
        enable_card_selection: bool = True,
        enable_card_context_menu: bool = True,
        enable_card_double_click: bool = True,
        enable_inline_card_editing: bool = True,
        enable_builtin_card_form: bool = True,
        card_form_mode: str = "popup",
        confirm_delete: bool = True,
        confirm_discard_changes: bool = True,
        # Drag and drop
        enable_card_drag: bool = True,
        enable_card_reorder: bool = True,
        enable_drag_preview: bool = True,
        drag_preview_opacity: float = 1.0,
        show_drop_indicator: bool = True,
        enable_horizontal_autoscroll: bool = True,
        enable_vertical_autoscroll: bool = True,
        incremental_card_rendering: bool = True,
        incremental_column_rendering: bool = True,
        drag_update_interval_ms: int = 16,
        autoscroll_interval_ms: int = 45,
        cleanup_time_budget_ms: int = 8,
        # Search/filter/sort
        enable_search: bool = True,
        enable_filters: bool = True,
        enable_sorting: bool = True,
        allow_column_sorting: bool = True,
        default_sort: str = "manual",
        filter_mode: str = "hide",
        show_no_results: bool = True,
        highlight_search_matches: bool = True,
        # Styling and extension points
        theme: Mapping[str, Any] | None = None,
        style: Mapping[str, Any] | None = None,
        priority_colors: Mapping[str, str] | None = None,
        tag_colors: Mapping[str, str] | None = None,
        font_config: Mapping[str, Any] | None = None,
        card_renderer: CardRenderer | None = None,
        card_context_menu_items: Iterable[ContextMenuItem] | None = None,
        # Data source and durable state
        data_source: KanbanDataSource | None = None,
        board_id: str = "default",
        actor_id: str | None = None,
        auto_load: bool = False,
        server_side_query: bool = False,
        page_size: int = 100,
        poll_interval_ms: int = 0,
        retry_policy: RetryPolicy | None = None,
        disable_while_saving: bool = True,
        id_factory: Callable[[], Any] | None = None,
        use_temporary_ids: bool = True,
        immutable_card_ids: bool = True,
        immutable_column_ids: bool = True,
        conflict_strategy: str = "server_wins",
        undo_limit: int = 50,
        completion_field: str = "completed",
        completed_columns: Iterable[Any] | None = None,
        timezone_name: str = "UTC",
        locale_name: str | None = None,
        normalize_empty_values: bool = True,
        logger: logging.Logger | None = None,
        # Callbacks
        on_card_clicked: KanbanCallback | None = None,
        on_card_double_clicked: KanbanCallback | None = None,
        on_card_right_clicked: KanbanCallback | None = None,
        on_card_moved: KanbanCallback | None = None,
        on_card_reordered: KanbanCallback | None = None,
        on_card_created: KanbanCallback | None = None,
        on_card_updated: KanbanCallback | None = None,
        on_card_deleted: KanbanCallback | None = None,
        on_column_created: KanbanCallback | None = None,
        on_column_updated: KanbanCallback | None = None,
        on_column_deleted: KanbanCallback | None = None,
        on_column_reordered: KanbanCallback | None = None,
        on_data_changed: KanbanCallback | None = None,
        on_filter_changed: KanbanCallback | None = None,
        on_search_changed: KanbanCallback | None = None,
        on_sort_changed: KanbanCallback | None = None,
        on_action_cancelled: KanbanCallback | None = None,
        on_error: KanbanCallback | None = None,
        on_add_card_requested: KanbanCallback | None = None,
        on_edit_card_requested: KanbanCallback | None = None,
        on_persistence_status: KanbanCallback | None = None,
        on_conflict: KanbanCallback | None = None,
        **kwargs: Any,
    ) -> None:
        column_width = _validated_int(column_width, "column_width", minimum=160)
        column_height = _validated_int(column_height, "column_height", minimum=180)
        column_gap = _validated_int(column_gap, "column_gap", minimum=0)
        min_column_width = _validated_int(min_column_width, "min_column_width", minimum=160)
        max_column_width = _validated_int(max_column_width, "max_column_width", minimum=min_column_width)
        column_control_size = _validated_int(column_control_size, "column_control_size", minimum=28)
        max_visible_tags = _validated_int(max_visible_tags, "max_visible_tags", minimum=1)
        tags_per_row = _validated_int(tags_per_row, "tags_per_row", minimum=1)
        drag_update_interval_ms = _validated_int(
            drag_update_interval_ms,
            "drag_update_interval_ms",
            minimum=0,
        )
        autoscroll_interval_ms = _validated_int(
            autoscroll_interval_ms,
            "autoscroll_interval_ms",
            minimum=0,
        )
        cleanup_time_budget_ms = _validated_int(
            cleanup_time_budget_ms,
            "cleanup_time_budget_ms",
            minimum=1,
        )
        page_size = _validated_int(page_size, "page_size", minimum=1)
        poll_interval_ms = _validated_int(poll_interval_ms, "poll_interval_ms", minimum=0)
        undo_limit = _validated_int(undo_limit, "undo_limit", minimum=0)
        drag_preview_opacity = _validated_opacity(drag_preview_opacity)
        theme = _validated_mapping(theme, "theme")
        style = _validated_mapping(style, "style")
        priority_colors = _validated_mapping(priority_colors, "priority_colors")
        tag_colors = _validated_mapping(tag_colors, "tag_colors")
        font_config = _validated_mapping(font_config, "font_config")
        style_overrides = dict(theme or {})
        style_overrides.update(dict(style or {}))
        style_font_config = style_overrides.pop("font_config", style_overrides.pop("fonts", None))
        style_priority_colors = style_overrides.pop("priority_colors", None)
        style_tag_colors = style_overrides.pop("tag_colors", None)
        style_font_config = _validated_mapping(style_font_config, "style font_config")
        style_priority_colors = _validated_mapping(style_priority_colors, "style priority_colors")
        style_tag_colors = _validated_mapping(style_tag_colors, "style tag_colors")
        if style_font_config is not None:
            merged_font_config = dict(style_font_config)
            merged_font_config.update(dict(font_config or {}))
            font_config = merged_font_config
        if style_priority_colors is not None:
            merged_priority_colors = dict(style_priority_colors)
            merged_priority_colors.update(dict(priority_colors or {}))
            priority_colors = merged_priority_colors
        if style_tag_colors is not None:
            merged_tag_colors = dict(style_tag_colors)
            merged_tag_colors.update(dict(tag_colors or {}))
            tag_colors = merged_tag_colors
        if card_mode not in {"compact", "detailed"}:
            raise KanbanValidationError("card_mode must be 'compact' or 'detailed'")
        if card_density not in {"compact", "comfortable", "spacious"}:
            raise KanbanValidationError("card_density must be 'compact', 'comfortable', or 'spacious'")
        if filter_mode not in {"hide", "dim"}:
            raise KanbanValidationError("filter_mode must be 'hide' or 'dim'")
        if card_form_mode not in {"popup", "sidepanel"}:
            raise KanbanValidationError("card_form_mode must be 'popup' or 'sidepanel'")
        boolean_options = {
            "enable_horizontal_scroll": enable_horizontal_scroll,
            "responsive_columns": responsive_columns,
            "enable_column_scroll": enable_column_scroll,
            "show_toolbar": show_toolbar,
            "show_search": show_search,
            "show_filter_button": show_filter_button,
            "show_sort_button": show_sort_button,
            "show_add_card_button": show_add_card_button,
            "show_clear_filters_button": show_clear_filters_button,
            "show_card_count": show_card_count,
            "show_column_add_button": show_column_add_button,
            "show_column_menu": show_column_menu,
            "enforce_column_limits": enforce_column_limits,
            "enable_column_drag": enable_column_drag,
            "enable_card_hover": enable_card_hover,
            "show_drag_handles": show_drag_handles,
            "enable_card_selection": enable_card_selection,
            "enable_card_context_menu": enable_card_context_menu,
            "enable_card_double_click": enable_card_double_click,
            "enable_inline_card_editing": enable_inline_card_editing,
            "enable_builtin_card_form": enable_builtin_card_form,
            "confirm_delete": confirm_delete,
            "confirm_discard_changes": confirm_discard_changes,
            "enable_card_drag": enable_card_drag,
            "enable_card_reorder": enable_card_reorder,
            "enable_drag_preview": enable_drag_preview,
            "show_drop_indicator": show_drop_indicator,
            "enable_horizontal_autoscroll": enable_horizontal_autoscroll,
            "enable_vertical_autoscroll": enable_vertical_autoscroll,
            "incremental_card_rendering": incremental_card_rendering,
            "incremental_column_rendering": incremental_column_rendering,
            "enable_search": enable_search,
            "enable_filters": enable_filters,
            "enable_sorting": enable_sorting,
            "allow_column_sorting": allow_column_sorting,
            "show_no_results": show_no_results,
            "highlight_search_matches": highlight_search_matches,
        }
        for option_name, option_value in boolean_options.items():
            if not isinstance(option_value, bool):
                raise KanbanValidationError(f"{option_name} must be a boolean")

        normalized_columns = validate_columns(columns if columns is not None else [])
        normalized_cards = validate_cards(
            cards if cards is not None else [],
            {column["id"] for column in normalized_columns},
        )
        normalized_fields = validate_fields(fields)
        for card in normalized_cards:
            validate_card_values(card, normalized_fields)
        normalized_context_items = validate_context_menu_items(card_context_menu_items)
        allowed_sort_keys = {
            "manual",
            "priority",
            "due_date",
            "created_date",
            "created_at",
            "updated_date",
            "updated_at",
            "title",
        }
        allowed_sort_keys.update(field["key"] for field in normalized_fields if field.get("sortable"))
        if not isinstance(default_sort, str) or default_sort not in allowed_sort_keys:
            raise KanbanValidationError(f"Unsupported default sort key: {default_sort!r}")
        default_sort = _canonical_sort_key(default_sort)

        callbacks: dict[str, KanbanCallback | None] = {
            "on_card_clicked": on_card_clicked,
            "on_card_double_clicked": on_card_double_clicked,
            "on_card_right_clicked": on_card_right_clicked,
            "on_card_moved": on_card_moved,
            "on_card_reordered": on_card_reordered,
            "on_card_created": on_card_created,
            "on_card_updated": on_card_updated,
            "on_card_deleted": on_card_deleted,
            "on_column_created": on_column_created,
            "on_column_updated": on_column_updated,
            "on_column_deleted": on_column_deleted,
            "on_column_reordered": on_column_reordered,
            "on_data_changed": on_data_changed,
            "on_filter_changed": on_filter_changed,
            "on_search_changed": on_search_changed,
            "on_sort_changed": on_sort_changed,
            "on_action_cancelled": on_action_cancelled,
            "on_error": on_error,
            "on_add_card_requested": on_add_card_requested,
            "on_edit_card_requested": on_edit_card_requested,
            "on_persistence_status": on_persistence_status,
            "on_conflict": on_conflict,
        }
        for callback_name, callback in callbacks.items():
            if callback is not None and not callable(callback):
                raise KanbanValidationError(f"{callback_name} must be callable or None")
        if card_renderer is not None and not callable(card_renderer):
            raise KanbanValidationError("card_renderer must be callable or None")
        if data_source is not None and on_data_changed is not None:
            raise KanbanValidationError(
                "Use either data_source or on_data_changed, not both; two persistence writers can diverge"
            )
        if data_source is not None and not isinstance(data_source, KanbanDataSource):
            raise KanbanValidationError("data_source does not implement the KanbanDataSource protocol")
        if id_factory is not None and not callable(id_factory):
            raise KanbanValidationError("id_factory must be callable or None")
        if conflict_strategy not in {"server_wins", "local_wins", "callback"}:
            raise KanbanValidationError(
                "conflict_strategy must be 'server_wins', 'local_wins', or 'callback'"
            )
        if timezone_name.upper() in {"UTC", "ETC/UTC", "GMT"}:
            configured_timezone = timezone.utc
        else:
            try:
                configured_timezone = ZoneInfo(timezone_name)
            except (KeyError, ValueError) as exc:
                raise KanbanValidationError(f"Unknown timezone: {timezone_name!r}") from exc

        self.theme = merge_theme(style_overrides)
        self.style = self.theme
        for font_name, font_value in dict(font_config or {}).items():
            self.theme[f"{font_name}_font"] = font_value
        font_defaults = {
            "card_title_font": {"size": 14, "weight": "bold"},
            "card_body_font": {"size": 11},
            "card_metadata_font": {"size": 11},
            "badge_font": {"size": 9, "weight": "bold"},
            "column_title_font": {"size": 13, "weight": "bold"},
            "column_count_font": {"size": 11, "weight": "bold"},
            "form_title_font": {"size": 20, "weight": "bold"},
            "form_label_font": {"size": 11, "weight": "bold"},
            "filter_title_font": {"size": 19, "weight": "bold"},
            "toolbar_font": {"size": 11, "weight": "bold"},
            "button_font": {"size": 12, "weight": "bold"},
            "secondary_button_font": {"size": 12, "weight": "bold"},
            "input_font": {"size": 12},
        }
        for font_key, options in font_defaults.items():
            if font_key not in self.theme:
                self.theme[font_key] = ctk.CTkFont(**options)
        padding_value = self.theme["board_padding"] if board_padding is None else board_padding
        board_padding = _validated_int(padding_value, "board_padding", minimum=0)
        kwargs.setdefault("fg_color", self.theme["board_fg_color"])
        kwargs.setdefault("corner_radius", self.theme.get("board_corner_radius", 0))
        super().__init__(master, **kwargs)

        self._columns_data = normalized_columns
        self._cards: dict[Any, dict[str, Any]] = {card["id"]: card for card in normalized_cards}
        self.fields = normalized_fields
        self._searchable_field_keys = [field["key"] for field in self.fields if field.get("searchable")]
        if not self._searchable_field_keys:
            self._searchable_field_keys = ["title", "description"]
        self.priority_colors = {**DEFAULT_PRIORITY_COLORS, **dict(priority_colors or {})}
        self.tag_colors = dict(tag_colors or {})
        self.font_config = dict(font_config or {})
        self.card_renderer = card_renderer
        self.card_context_menu_items = normalized_context_items

        self.enable_horizontal_scroll = enable_horizontal_scroll
        self.enable_column_scroll = enable_column_scroll
        self.column_width = column_width
        self.column_height = column_height
        self.column_gap = column_gap
        self.responsive_columns = responsive_columns
        self.min_column_width = min_column_width
        self.max_column_width = max_column_width
        self.column_control_size = column_control_size
        self.board_padding = board_padding
        self.show_toolbar = show_toolbar
        self.show_search = show_search and enable_search
        self.show_filter_button = show_filter_button and enable_filters
        self.show_sort_button = show_sort_button and enable_sorting
        self.show_add_card_button = show_add_card_button
        self.show_clear_filters_button = show_clear_filters_button
        self.show_card_count = show_card_count
        self.show_column_add_button = show_column_add_button
        self.show_column_menu = show_column_menu
        self.enforce_column_limits = enforce_column_limits
        self.enable_column_drag = enable_column_drag
        self.card_mode = card_mode
        self.card_density = card_density
        self.show_drag_handles = show_drag_handles
        self.max_visible_tags = max_visible_tags
        self.tags_per_row = tags_per_row
        self.enable_card_hover = enable_card_hover
        self.enable_card_selection = enable_card_selection
        self.enable_card_context_menu = enable_card_context_menu
        self.enable_card_double_click = enable_card_double_click
        self.enable_inline_card_editing = enable_inline_card_editing
        self.enable_builtin_card_form = enable_builtin_card_form
        self.card_form_mode = card_form_mode
        self.confirm_delete = confirm_delete
        self.confirm_discard_changes = confirm_discard_changes
        self.enable_card_drag = enable_card_drag
        self.enable_card_reorder = enable_card_reorder
        self.enable_drag_preview = enable_drag_preview
        self.drag_preview_opacity = drag_preview_opacity
        self.show_drop_indicator = show_drop_indicator
        self.enable_horizontal_autoscroll = enable_horizontal_autoscroll
        self.enable_vertical_autoscroll = enable_vertical_autoscroll
        self.incremental_card_rendering = incremental_card_rendering
        self.incremental_column_rendering = incremental_column_rendering
        self.drag_update_interval_ms = drag_update_interval_ms
        self.autoscroll_interval_ms = autoscroll_interval_ms
        self.cleanup_time_budget_ms = cleanup_time_budget_ms
        self.enable_search = enable_search
        self.enable_filters = enable_filters
        self.enable_sorting = enable_sorting
        self.allow_column_sorting = allow_column_sorting
        self.filter_mode = filter_mode
        self.show_no_results = show_no_results
        self.highlight_search_matches = highlight_search_matches

        self._callbacks = callbacks

        self.data_source = data_source
        self.board_id = str(board_id)
        self.actor_id = actor_id
        self.auto_load = auto_load
        self.server_side_query = server_side_query
        self.page_size = page_size
        self.poll_interval_ms = poll_interval_ms
        self.disable_while_saving = disable_while_saving
        self.id_factory = id_factory
        self.use_temporary_ids = use_temporary_ids
        self.immutable_card_ids = immutable_card_ids
        self.immutable_column_ids = immutable_column_ids
        self.conflict_strategy = conflict_strategy
        self.undo_limit = undo_limit
        self.completion_field = str(completion_field)
        self.completed_columns = set(completed_columns or [])
        self.timezone = configured_timezone
        self.timezone_name = timezone_name
        self.locale_name = locale_name
        self.normalize_empty_values = normalize_empty_values
        self.logger = logger or logging.getLogger("ctk_kanban.board")
        self._board_revision: int | str | None = None
        self._persistence_state: PersistenceState = "idle"
        self._persistence_message: str | None = None
        self._mutation_locked = False
        self._column_totals: dict[Any, int] = {
            column["id"]: sum(1 for card in normalized_cards if card["column"] == column["id"])
            for column in normalized_columns
        }
        self._loaded_offsets: dict[Any, int] = {
            column["id"]: sum(1 for card in normalized_cards if card["column"] == column["id"])
            for column in normalized_columns
        }
        self._loaded_offsets[None] = len(normalized_cards)
        self._has_more = False
        self._poll_after_id: str | None = None
        self._history_undo: list[_HistoryEntry] = []
        self._history_redo: list[_HistoryEntry] = []
        self._history_suspended = False
        self._batch_events: list[MutationEvent] | None = None
        self._persistence: PersistenceCoordinator | None = None
        self._ui_queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._ui_after_id: str | None = None

        self._search_query = ""
        self._filters: dict[str, Any] = {}
        self._global_sort: tuple[str, bool] = (default_sort, False)
        self._column_sorts: dict[Any, tuple[str, bool]] = {}
        self._selected_card_id: Any | None = None
        self._column_widgets: dict[Any, CTkKanbanColumn] = {}
        self._card_widgets: dict[Any, CTkKanbanCard] = {}
        self._hidden_card_widgets: dict[Any, CTkKanbanCard] = {}
        self._retired_card_widgets: list[CTkKanbanCard] = []
        self._retire_after_id: str | None = None
        self._empty_label: Any | None = None
        self._status_overlay: ctk.CTkFrame | None = None
        self._drag_state: dict[str, Any] | None = None
        self._drag_preview: tk.Toplevel | None = None
        self._drag_preview_position: tuple[int, int] | None = None
        self._indicator_column: CTkKanbanColumn | None = None
        self._highlighted_column: CTkKanbanColumn | None = None
        self._last_cancellation_reason: str | None = None
        self._last_callback_result = MutationResult()
        self._card_form_panel: CardFormFrame | None = None
        self._card_form_dialog: CardFormDialog | None = None
        self._inline_edit_card: CTkKanbanCard | None = None
        self._inline_outside_click_binding: (
            tuple[Any, Any, str, str, str, list[Any], str] | None
        ) = None
        self._inline_outside_click_dispatching = False
        self._inline_outside_unbind_after_id: str | None = None
        self._inline_outside_release_blocked = False

        self._build_board()
        self._ui_after_id = self.after(10, self._drain_ui_queue)
        if self.data_source is not None:
            self._persistence = PersistenceCoordinator(
                self.data_source,
                schedule=self._ui_queue.put,
                on_status=self._set_persistence_status,
                retry_policy=retry_policy,
                logger=self.logger,
            )
            if self.auto_load:
                self.after_idle(self.refresh_from_source)
            if self.poll_interval_ms:
                self._schedule_poll()

    def destroy(self) -> None:
        """Close persistence exactly once before the widget tears down callbacks."""

        persistence = getattr(self, "_persistence", None)
        self._persistence = None
        if persistence is not None:
            persistence.close()
        active_inline_card = getattr(self, "_inline_edit_card", None)
        if active_inline_card is not None:
            try:
                if (
                    active_inline_card.winfo_exists()
                    and active_inline_card.editing_field_key is not None
                ):
                    active_inline_card.cancel_inline_edit()
            except tk.TclError:
                pass
            self._inline_edit_card = None
        self._unbind_inline_outside_click()
        super().destroy()

    # ------------------------------------------------------------------
    # Callback and error handling
    # ------------------------------------------------------------------
    def _set_persistence_status(self, state: PersistenceState, message: str | None) -> None:
        """Update storage status and make it visible to the host and toolbar."""

        self._persistence_state = state
        self._persistence_message = message
        self._mutation_locked = self.disable_while_saving and state in {"saving", "retrying"}
        if hasattr(self, "toolbar") and hasattr(self.toolbar, "set_persistence_status"):
            self.toolbar.set_persistence_status(state, message)
        if state == "loading" and not self._cards:
            self._show_status_overlay(message or "Loading...", retry=False)
        elif state in {"offline", "conflict", "error"} and not self._cards:
            self._show_status_overlay(message or "Unable to load board", retry=True)
        elif state in {"idle", "saved"}:
            self._hide_status_overlay()
        event = create_event(
            "persistence_status",
            source="persistence",
            board_id=self.board_id,
            state=state,
            message=message,
            queued_count=self._persistence.queued_count if self._persistence is not None else 0,
        )
        self._invoke_callback("on_persistence_status", event)

    def _show_status_overlay(self, text: str, *, retry: bool) -> None:
        if self._status_overlay is not None:
            self._status_overlay.destroy()
        frame = ctk.CTkFrame(self.board_area, fg_color=self.theme["column_fg_color"])
        frame.grid(row=0, column=0, padx=30, pady=30)
        ctk.CTkLabel(frame, text=text, wraplength=340).pack(padx=24, pady=(20, 8))
        if retry:
            ctk.CTkButton(frame, text="Retry", command=self.retry_last_save).pack(pady=(0, 20))
        self._status_overlay = frame

    def _hide_status_overlay(self) -> None:
        if self._status_overlay is not None:
            self._status_overlay.destroy()
            self._status_overlay = None

    def get_persistence_status(self) -> dict[str, Any]:
        """Return current save state for custom status bars and diagnostics."""

        return {
            "state": self._persistence_state,
            "message": self._persistence_message,
            "board_revision": self._board_revision,
            "queued_count": self._persistence.queued_count if self._persistence is not None else 0,
        }

    def retry_last_save(self) -> bool:
        """Retry the most recent rejected or failed durable mutation."""

        if self._persistence is None:
            return False
        if self._persistence.retry_last():
            return True
        return self.refresh_from_source()

    def set_online(self, online: bool) -> None:
        """Control offline queueing for applications that monitor connectivity."""

        if self._persistence is not None:
            self._persistence.set_online(bool(online))

    def _ensure_mutation_allowed(self) -> None:
        if self._mutation_locked:
            raise KanbanPersistenceError("Please wait for the current save to finish")

    def _operation_payload(self, event: Mapping[str, Any]) -> dict[str, Any]:
        excluded = {
            "type",
            "timestamp",
            "source",
            "event_id",
            "transaction_id",
            "board_id",
            "actor_id",
            "expected_revision",
        }
        return {key: clone(value) for key, value in event.items() if key not in excluded}

    def _record_history(self, before: dict[str, Any] | None, after: dict[str, Any] | None = None) -> None:
        if before is None or self._history_suspended or self.undo_limit == 0:
            return
        after = self._capture_internal_state() if after is None else clone(after)
        if before == after:
            return
        self._history_undo.append((clone(before), after))
        if len(self._history_undo) > self.undo_limit:
            del self._history_undo[0 : len(self._history_undo) - self.undo_limit]
        self._history_redo.clear()

    def can_undo(self) -> bool:
        return bool(self._history_undo)

    def can_redo(self) -> bool:
        return bool(self._history_redo)

    def _capture_internal_state(self) -> dict[str, Any]:
        """Capture board state together with paging metadata for safe rollback."""

        return {
            **self.get_state(),
            "__column_totals": clone(self._column_totals),
            "__loaded_offsets": clone(self._loaded_offsets),
            "__has_more": self._has_more,
        }

    def _restore_internal_state(self, state: Mapping[str, Any]) -> None:
        """Restore a state captured by :meth:`_capture_internal_state`."""

        self.set_state(state)
        self._restore_paging_metadata(state)

    def _capture_history_snapshot(self) -> _HistorySnapshot:
        """Capture both history stacks before an asynchronous undo or redo."""

        return (clone(self._history_undo), clone(self._history_redo))

    def _restore_history_snapshot(self, snapshot: _HistorySnapshot) -> None:
        """Restore history after durable undo/redo persistence is rejected."""

        self._history_undo = clone(snapshot[0])
        self._history_redo = clone(snapshot[1])

    def _restore_paging_metadata(self, state: Mapping[str, Any]) -> None:
        """Restore paging metadata after a public bulk setter recomputes it."""

        raw_totals = state.get("__column_totals")
        if isinstance(raw_totals, Mapping):
            self._column_totals = {key: max(0, int(value)) for key, value in raw_totals.items()}
        raw_offsets = state.get("__loaded_offsets")
        if isinstance(raw_offsets, Mapping):
            self._loaded_offsets = {key: max(0, int(value)) for key, value in raw_offsets.items()}
        self._has_more = bool(state.get("__has_more", self._has_more))
        self._sync_paging_metadata_view()

    def _clear_history(self) -> None:
        """Discard snapshots that no longer describe the currently loaded page."""

        self._history_undo.clear()
        self._history_redo.clear()

    def undo(self) -> bool:
        """Restore the state before the latest accepted mutation."""

        self._ensure_mutation_allowed()
        if not self._history_undo:
            return False
        history_before = self._capture_history_snapshot()
        before, after = self._history_undo.pop()
        self._history_suspended = True
        try:
            self._restore_internal_state(before)
        finally:
            self._history_suspended = False
        self._history_redo.append((before, after))
        self._persist_state_replacement(
            "undo",
            rollback_state=after,
            rollback_history=history_before,
        )
        return True

    def redo(self) -> bool:
        """Reapply the latest undone mutation."""

        self._ensure_mutation_allowed()
        if not self._history_redo:
            return False
        history_before = self._capture_history_snapshot()
        before, after = self._history_redo.pop()
        self._history_suspended = True
        try:
            self._restore_internal_state(after)
        finally:
            self._history_suspended = False
        self._history_undo.append((before, after))
        self._persist_state_replacement(
            "redo",
            rollback_state=before,
            rollback_history=history_before,
        )
        return True

    def _persist_state_replacement(
        self,
        source: str,
        rollback_state: dict[str, Any],
        rollback_history: _HistorySnapshot,
    ) -> None:
        if self._persistence is not None:
            events = self._state_delta_events(rollback_state, self._capture_internal_state(), source=source)
            if not events:
                return
            self._set_persistence_status("saving", f"Saving {source}...")

            def succeeded(result: MutationResult) -> None:
                self._board_revision = result.board_revision or self._board_revision
                self._apply_canonical_result({}, result)

            def failed(error: Exception | MutationResult) -> None:
                self._history_suspended = True
                try:
                    if isinstance(error, MutationResult) and error.conflict and error.conflict.server_data:
                        self.set_data(error.conflict.server_data)
                        self._board_revision = error.conflict.actual_revision
                        self._clear_history()
                        self.refresh_from_source()
                    else:
                        self._restore_internal_state(rollback_state)
                        self._restore_history_snapshot(rollback_history)
                finally:
                    self._history_suspended = False
                reason = error.reason if isinstance(error, MutationResult) else str(error)
                self._action_cancelled(
                    create_event(f"{source}_failed", source=source),
                    reason or f"Unable to save {source}",
                )

            self._persistence.submit_batch(events, on_success=succeeded, on_failure=failed)
            return
        event = create_event(
            "board_replaced",
            source=source,
            columns=self.get_columns(),
            cards=self.get_all_cards(),
        )
        reason = self._invoke_data_changed(event, rollback_state=rollback_state, record_history=False)
        if reason:
            self._history_suspended = True
            try:
                self._restore_internal_state(rollback_state)
                self._restore_history_snapshot(rollback_history)
            finally:
                self._history_suspended = False
            self._action_cancelled(event, reason)

    def _state_delta_events(
        self,
        previous: Mapping[str, Any],
        current: Mapping[str, Any],
        *,
        source: str,
    ) -> list[MutationEvent]:
        """Describe a state transition without replacing unseen server records."""

        previous_columns = [dict(column) for column in previous.get("columns", [])]
        current_columns = [dict(column) for column in current.get("columns", [])]
        previous_cards = [dict(card) for card in previous.get("cards", [])]
        current_cards = [dict(card) for card in current.get("cards", [])]
        previous_columns_by_id = {column["id"]: column for column in previous_columns}
        current_columns_by_id = {column["id"]: column for column in current_columns}
        previous_cards_by_id = {card["id"]: card for card in previous_cards}
        current_cards_by_id = {card["id"]: card for card in current_cards}
        transaction_id = str(uuid4())
        events: list[MutationEvent] = []
        renamed_columns: dict[Any, Any] = {}

        for old_column, new_column in zip(previous_columns, current_columns):
            old_id = old_column["id"]
            new_id = new_column["id"]
            if (
                old_id != new_id
                and old_id not in current_columns_by_id
                and new_id not in previous_columns_by_id
            ):
                renamed_columns[old_id] = new_id

        def append(event_type: str, **payload: Any) -> None:
            action = create_event(event_type, source=source, transaction_id=transaction_id, **payload)
            events.append(
                MutationEvent.from_mapping(
                    {
                        **action,
                        "payload": self._operation_payload(action),
                        "board_id": self.board_id,
                        "actor_id": self.actor_id,
                        "expected_revision": self._board_revision,
                    }
                )
            )

        for old_id, new_id in renamed_columns.items():
            old = previous_columns_by_id[old_id]
            column = current_columns_by_id[new_id]
            append(
                "column_updated",
                column_id=new_id,
                old_column_id=old_id,
                column_data=clone(column),
                old_column_data=clone(old),
                changed_fields={
                    key: clone(value) for key, value in column.items() if old.get(key) != value
                },
            )
        renamed_targets = set(renamed_columns.values())
        for index, column in enumerate(current_columns):
            if column["id"] not in previous_columns_by_id and column["id"] not in renamed_targets:
                append("column_created", column_id=column["id"], column_data=clone(column), index=index)
        for column_id, column in current_columns_by_id.items():
            old = previous_columns_by_id.get(column_id)
            if old is not None and old != column:
                append(
                    "column_updated",
                    column_id=column_id,
                    old_column_id=column_id,
                    column_data=clone(column),
                    old_column_data=clone(old),
                    changed_fields={
                        key: clone(value) for key, value in column.items() if old.get(key) != value
                    },
                )

        for card_id, old in previous_cards_by_id.items():
            if card_id not in current_cards_by_id:
                append(
                    "card_deleted",
                    card_id=card_id,
                    card_data=clone(old),
                    old_card_data=clone(old),
                )
        for card_id, card in current_cards_by_id.items():
            old = previous_cards_by_id.get(card_id)
            if old is None:
                append(
                    "card_created",
                    card_id=card_id,
                    card_data=clone(card),
                    temporary_id=False,
                )
            elif old != card:
                renamed_old = clone(old)
                old_column = renamed_old.get("column")
                if old_column in renamed_columns:
                    renamed_old["column"] = renamed_columns[old_column]
                if renamed_old == card:
                    continue
                append(
                    "card_updated",
                    card_id=card_id,
                    old_card_id=card_id,
                    card_data=clone(card),
                    old_card_data=clone(old),
                    changed_fields={
                        key: clone(value) for key, value in card.items() if old.get(key) != value
                    },
                )

        for column_id, old in previous_columns_by_id.items():
            if column_id not in current_columns_by_id and column_id not in renamed_columns:
                append("column_deleted", column_id=column_id, column_data=clone(old))
        previous_order = [renamed_columns.get(column["id"], column["id"]) for column in previous_columns]
        if previous_order != [column["id"] for column in current_columns]:
            append("column_reordered", columns=clone(current_columns))
        return events

    def _invoke_callback(self, name: str, event: dict[str, Any], *, cancellable: bool = False) -> str | None:
        callback = self._callbacks.get(name)
        if callback is None:
            return None
        try:
            result = callback(clone(event))
            self._last_callback_result = coerce_mutation_result(result)
        except Exception as exc:  # Application callbacks are an integration boundary.
            self._emit_error(exc, event)
            if cancellable:
                return str(exc).strip() or exc.__class__.__name__
            return None
        return cancellation_reason(result) if cancellable else None

    def _emit_error(self, error: Exception, action_event: dict[str, Any] | None = None) -> None:
        callback = self._callbacks.get("on_error")
        if callback is None:
            return
        event = create_event(
            "error",
            source="callback" if action_event else "board",
            error=error,
            message=str(error),
            action_event=clone(action_event) if action_event else None,
        )
        try:
            callback(event)
        except Exception:
            pass

    def _action_cancelled(self, action_event: dict[str, Any], reason: str) -> None:
        self._last_cancellation_reason = reason
        event = create_event(
            "action_cancelled",
            source=action_event.get("source", "api"),
            action_type=action_event["type"],
            reason=reason,
            action_event=clone(action_event),
        )
        self._invoke_callback("on_action_cancelled", event)

    def _invoke_data_changed(
        self,
        action_event: dict[str, Any],
        *,
        rollback_state: dict[str, Any] | None = None,
        record_history: bool = True,
    ) -> str | None:
        """Persist one focused operation or emit the legacy snapshot callback."""

        if self._batch_events is not None:
            self._batch_events.append(
                MutationEvent.from_mapping(
                    {
                        **action_event,
                        "payload": self._operation_payload(action_event),
                        "board_id": self.board_id,
                        "actor_id": self.actor_id,
                        "expected_revision": self._board_revision,
                    }
                )
            )
            return None

        if self._persistence is not None:
            event = MutationEvent.from_mapping(
                {
                    **action_event,
                    "payload": self._operation_payload(action_event),
                    "board_id": self.board_id,
                    "actor_id": self.actor_id,
                    "expected_revision": self._board_revision,
                }
            )
            self.logger.info(
                "Submitting Kanban mutation",
                extra={
                    "kanban_event_id": event.metadata.event_id,
                    "kanban_transaction_id": event.metadata.transaction_id,
                    "kanban_board_id": self.board_id,
                    "kanban_operation": event.type,
                    "kanban_expected_revision": self._board_revision,
                },
            )
            self._set_persistence_status("saving", "Saving...")

            def succeeded(result: MutationResult) -> None:
                self._board_revision = result.board_revision or self._board_revision
                self.logger.info(
                    "Kanban mutation saved",
                    extra={
                        "kanban_event_id": event.metadata.event_id,
                        "kanban_board_id": self.board_id,
                        "kanban_operation": event.type,
                        "kanban_revision": self._board_revision,
                    },
                )
                self._apply_canonical_result(action_event, result)
                if record_history:
                    self._record_history(rollback_state)

            def failed(error: Exception | MutationResult) -> None:
                self.logger.error(
                    "Kanban mutation rejected",
                    extra={
                        "kanban_event_id": event.metadata.event_id,
                        "kanban_board_id": self.board_id,
                        "kanban_operation": event.type,
                    },
                )
                if isinstance(error, MutationResult) and error.conflict is not None:
                    self._handle_conflict(event, error, rollback_state)
                    return
                if (
                    isinstance(error, (ConnectionError, TimeoutError, OSError))
                    and not self._persistence.online
                ):
                    self.logger.warning(
                        "Kanban mutation queued offline",
                        extra={"kanban_event_id": event.metadata.event_id, "kanban_board_id": self.board_id},
                    )
                    return
                if rollback_state is not None:
                    self._history_suspended = True
                    try:
                        self._restore_internal_state(rollback_state)
                    finally:
                        self._history_suspended = False
                reason = error.reason if isinstance(error, MutationResult) else str(error)
                self._action_cancelled(action_event, reason or "Save failed")

            self._persistence.submit(event, on_success=succeeded, on_failure=failed)
            return None

        if self._callbacks.get("on_data_changed") is None:
            if record_history:
                self._record_history(rollback_state)
            return None
        event = create_event(
            "data_changed",
            source=action_event.get("source", "api"),
            action_type=action_event["type"],
            action_event=clone(action_event),
            columns=self.get_columns(),
            cards=self.get_all_cards(),
        )
        reason = self._invoke_callback("on_data_changed", event, cancellable=True)
        if reason is None:
            self._apply_canonical_result(action_event, self._last_callback_result)
        if reason is None and record_history:
            self._record_history(rollback_state)
        return reason

    def _apply_canonical_result(self, action_event: Mapping[str, Any], result: MutationResult) -> None:
        """Merge IDs, timestamps, versions, and defaults returned by storage."""

        changed = False
        for old_id, new_id in result.id_map.items():
            if old_id in self._cards:
                self.remap_card_id(old_id, new_id, persist=False)
                changed = True
        if result.card is not None:
            old_id = action_event.get("old_card_id", action_event.get("card_id", result.card["id"]))
            if old_id in self._cards and old_id != result.card["id"]:
                self.remap_card_id(old_id, result.card["id"], persist=False)
            if result.card["id"] in self._cards:
                self._cards[result.card["id"]] = clone(result.card)
                changed = True
        for card in result.changed_cards:
            if card.get("id") in self._cards:
                self._cards[card["id"]] = clone(card)
                changed = True
        if result.column is not None:
            for index, column in enumerate(self._columns_data):
                if column["id"] in {action_event.get("old_column_id"), result.column["id"]}:
                    self._columns_data[index] = clone(result.column)
                    changed = True
                    break
        if changed:
            if self.incremental_card_rendering:
                self._replace_cards_incrementally(list(self._cards.values()))
            else:
                self.refresh()

    def remap_card_id(self, old_id: Any, new_id: Any, *, persist: bool = False) -> dict[str, Any]:
        """Replace a temporary card ID with its canonical database ID."""

        if new_id in self._cards and new_id != old_id:
            raise KanbanDuplicateIDError(f"Duplicate card ID: {new_id!r}")
        card = self._require_card(old_id)
        del self._cards[old_id]
        card["id"] = new_id
        self._cards[new_id] = card
        if self._selected_card_id == old_id:
            self._selected_card_id = new_id
        widget = self._card_widgets.pop(old_id, None)
        if widget is not None:
            widget.card_id = new_id
            widget.card_data["id"] = new_id
            self._card_widgets[new_id] = widget
        hidden = self._hidden_card_widgets.pop(old_id, None)
        if hidden is not None:
            hidden.card_id = new_id
            hidden.card_data["id"] = new_id
            self._hidden_card_widgets[new_id] = hidden
        if persist:
            self.update_card(new_id, {"id": new_id}, source="id_remap")
        return clone(card)

    def _handle_conflict(
        self,
        event: MutationEvent,
        result: MutationResult,
        rollback_state: dict[str, Any] | None,
    ) -> None:
        conflict = result.conflict
        assert conflict is not None
        decision = self.conflict_strategy
        callback = self._callbacks.get("on_conflict")
        if callback is not None:
            callback_event = create_event(
                "conflict",
                source="persistence",
                mutation=event.to_dict(),
                conflict=conflict,
            )
            try:
                callback_result = callback(callback_event)
                if isinstance(callback_result, str) and callback_result in {"server_wins", "local_wins"}:
                    decision = callback_result
            except Exception as exc:
                self._emit_error(exc, callback_event)
        if decision == "local_wins" and self._persistence is not None:
            event.metadata.expected_revision = conflict.actual_revision

            def local_saved(accepted: MutationResult) -> None:
                self._board_revision = accepted.board_revision or conflict.actual_revision
                self._apply_canonical_result(event.payload, accepted)
                self._record_history(rollback_state)

            def local_failed(error: Exception | MutationResult) -> None:
                if (
                    isinstance(error, (ConnectionError, TimeoutError, OSError))
                    and self._persistence is not None
                    and not self._persistence.online
                ):
                    return
                if rollback_state is not None:
                    self._history_suspended = True
                    try:
                        self._restore_internal_state(rollback_state)
                    finally:
                        self._history_suspended = False
                reason = error.reason if isinstance(error, MutationResult) else str(error)
                self._action_cancelled(event.to_dict(), reason or "Save failed")

            self._persistence.submit(
                event,
                on_success=local_saved,
                on_failure=local_failed,
            )
            return
        server_data = conflict.server_data
        if server_data is not None:
            self.set_data(server_data)
            self._board_revision = conflict.actual_revision
            self._clear_history()
            self.refresh_from_source()
        elif rollback_state is not None:
            self._restore_internal_state(rollback_state)
        self._action_cancelled(event.to_dict(), conflict.message)

    # ------------------------------------------------------------------
    # Card data API
    # ------------------------------------------------------------------
    def add_card(self, card_data: Mapping[str, Any], *, source: str = "api") -> dict[str, Any] | None:
        """Validate, add, and emit ``on_card_created`` for a new card."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        candidate = dict(card_data)
        temporary_id = False
        if candidate.get("id") in (None, ""):
            if self.id_factory is not None:
                candidate["id"] = self.id_factory()
            elif self.data_source is not None and self.use_temporary_ids:
                candidate["id"] = f"__tmp__:{uuid4()}"
                temporary_id = True
            else:
                candidate["id"] = generate_card_id(self._cards)
        now = datetime.now(self.timezone).isoformat()
        candidate.setdefault("created_at", now)
        candidate.setdefault("updated_at", now)
        candidate.setdefault("version", 0)
        card = validate_card(self._normalize_card_values(candidate), self._column_ids())
        validate_card_values(card, self.fields)
        if card["id"] in self._cards:
            raise KanbanDuplicateIDError(f"Duplicate card ID: {card['id']!r}")
        self._check_column_accepts(card["column"])
        column_was_partial = self._column_has_partial_card_data(card["column"])
        global_was_partial = self._has_more
        if card.get("sort_order") is None:
            card["sort_order"] = self._next_sort_order(card["column"])

        self._cards[card["id"]] = card
        self._adjust_column_total(card["column"], 1)
        matches_query = self._matches_active_server_query(card)
        column_enters_prefix = matches_query and (
            not column_was_partial or self._offset_contains_card(card["id"], card["column"])
        )
        global_enters_prefix = matches_query and (
            not global_was_partial or self._offset_contains_card(card["id"], None)
        )
        self._adjust_loaded_offsets(
            card["column"],
            int(column_enters_prefix),
            int(global_enters_prefix),
        )
        event = create_event(
            "card_created",
            source=source,
            card_id=card["id"],
            card_data=clone(card),
            column_data=self.get_column(card["column"]),
            temporary_id=temporary_id,
        )
        reason = self._invoke_callback("on_card_created", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            del self._cards[card["id"]]
            self._restore_paging_metadata(rollback_state)
            self._action_cancelled(event, reason)
            return None
        if self.incremental_card_rendering:
            self._render_card_add(card["id"])
        else:
            self.refresh()
        return clone(card)

    def update_card(
        self,
        card_id: Any,
        new_data: Mapping[str, Any],
        *,
        source: str = "api",
    ) -> dict[str, Any] | None:
        """Merge updates into a card and restore it if the callback cancels."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        if not isinstance(new_data, Mapping):
            raise KanbanValidationError("Card update data must be a mapping")
        old = clone(self._require_card(card_id))
        candidate = {**old, **new_data}
        if self.immutable_card_ids and candidate.get("id") != card_id:
            raise KanbanValidationError("Card IDs are immutable; use remap_card_id() for a database ID")
        candidate["updated_at"] = datetime.now(self.timezone).isoformat()
        updated = validate_card(self._normalize_card_values(candidate), self._column_ids())
        validate_card_values(updated, self.fields)
        new_id = updated["id"]
        if new_id != card_id and new_id in self._cards:
            raise KanbanDuplicateIDError(f"Duplicate card ID: {new_id!r}")
        if updated["column"] != old["column"]:
            self._check_column_accepts(updated["column"])
            if "sort_order" not in new_data:
                updated["sort_order"] = self._next_sort_order(updated["column"])
        old_column_was_partial = self._column_has_partial_card_data(old["column"])
        new_column_was_partial = self._column_has_partial_card_data(updated["column"])
        global_was_partial = self._has_more
        old_column_in_prefix = not old_column_was_partial or self._offset_contains_card(
            card_id, old["column"]
        )
        old_global_in_prefix = not global_was_partial or self._offset_contains_card(card_id, None)
        affected_columns = {old["column"], updated["column"]}
        if updated["column"] == old["column"]:
            snapshot = {card_id: old}
        else:
            snapshot = {
                current_id: clone(current)
                for current_id, current in self._cards.items()
                if current["column"] in affected_columns
            }
        del self._cards[card_id]
        self._cards[new_id] = updated
        if updated["column"] != old["column"]:
            self._adjust_column_total(old["column"], -1)
            self._adjust_column_total(updated["column"], 1)
        same_column = updated["column"] == old["column"]
        column_sort = self._column_sorts.get(updated["column"], self._global_sort)
        if same_column and not self._sort_position_changed(old, updated, column_sort):
            new_column_in_prefix = old_column_in_prefix
        else:
            prospective_column_offset = self._loaded_offsets.get(updated["column"], 0)
            if same_column and old_column_in_prefix:
                prospective_column_offset -= 1
            new_column_in_prefix = not new_column_was_partial or self._offset_contains_card(
                new_id,
                updated["column"],
                offset=max(0, prospective_column_offset),
            )
        if same_column and not self._sort_position_changed(old, updated, self._global_sort):
            new_global_in_prefix = old_global_in_prefix
        else:
            prospective_global_offset = self._loaded_offsets.get(None, 0) - int(old_global_in_prefix)
            new_global_in_prefix = not global_was_partial or self._offset_contains_card(
                new_id,
                None,
                offset=max(0, prospective_global_offset),
            )
        if same_column:
            self._adjust_loaded_offsets(
                updated["column"],
                int(new_column_in_prefix) - int(old_column_in_prefix),
                int(new_global_in_prefix) - int(old_global_in_prefix),
            )
        else:
            self._adjust_loaded_offsets(old["column"], -int(old_column_in_prefix), 0)
            self._adjust_loaded_offsets(
                updated["column"],
                int(new_column_in_prefix),
                int(new_global_in_prefix) - int(old_global_in_prefix),
            )

        event = create_event(
            "card_updated",
            source=source,
            card_id=new_id,
            old_card_id=card_id,
            card_data=clone(updated),
            old_card_data=clone(old),
            changed_fields={key: clone(value) for key, value in updated.items() if old.get(key) != value},
            changed_cards=self._changed_order_cards(snapshot, affected_columns),
            column_data=self.get_column(updated["column"]),
        )
        reason = self._invoke_callback("on_card_updated", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            if updated["column"] == old["column"]:
                self._cards.pop(new_id, None)
                self._cards.pop(card_id, None)
            else:
                for current_id, current in list(self._cards.items()):
                    if current_id in {card_id, new_id} or current["column"] in affected_columns:
                        del self._cards[current_id]
            self._cards.update(snapshot)
            self._restore_paging_metadata(rollback_state)
            self._action_cancelled(event, reason)
            return None
        if self._selected_card_id == card_id:
            self._selected_card_id = new_id
        if updated == old and new_id == card_id:
            return clone(updated)
        if self.incremental_card_rendering or source == "inline_edit":
            self._render_card_update(card_id, old["column"], new_id, updated["column"])
        else:
            self.refresh()
        return clone(updated)

    def delete_card(self, card_id: Any, *, source: str = "api") -> bool:
        """Delete a card, unless ``on_card_deleted`` rejects the operation."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        old = clone(self._require_card(card_id))
        column_id = old["column"]
        column_was_partial = self._column_has_partial_card_data(column_id)
        global_was_partial = self._has_more
        matches_query = self._matches_active_server_query(old)
        column_in_prefix = matches_query and (
            not column_was_partial or self._offset_contains_card(card_id, column_id)
        )
        global_in_prefix = matches_query and (
            not global_was_partial or self._offset_contains_card(card_id, None)
        )
        snapshot = {
            current_id: clone(current)
            for current_id, current in self._cards.items()
            if current["column"] == column_id
        }
        del self._cards[card_id]
        self._adjust_column_total(column_id, -1)
        self._adjust_loaded_offsets(
            column_id,
            -int(column_in_prefix),
            -int(global_in_prefix),
        )
        event = create_event(
            "card_deleted",
            source=source,
            card_id=card_id,
            card_data=clone(old),
            old_card_data=clone(old),
            column_data=self.get_column(column_id),
            changed_cards=self._changed_order_cards(snapshot, {column_id}),
        )
        reason = self._invoke_callback("on_card_deleted", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            for current_id, current in list(self._cards.items()):
                if current["column"] == column_id:
                    del self._cards[current_id]
            self._cards.update(snapshot)
            self._restore_paging_metadata(rollback_state)
            self._action_cancelled(event, reason)
            return False
        if self._selected_card_id == card_id:
            self._selected_card_id = None
        if self.incremental_card_rendering:
            self._render_card_delete(card_id, column_id)
        else:
            self.refresh()
        return True

    def duplicate_card(self, card_id: Any, *, source: str = "api") -> dict[str, Any] | None:
        """Copy a card with a generated ID and a title suffix."""

        duplicate = clone(self._require_card(card_id))
        duplicate["id"] = generate_card_id(self._cards)
        duplicate["title"] = f"{duplicate['title']} (copy)"
        duplicate.pop("sort_order", None)
        return self.add_card(duplicate, source=source)

    def move_card(
        self,
        card_id: Any,
        target_column: Any,
        target_index: int | None = None,
        *,
        source: str = "api",
    ) -> bool:
        """Move or reorder a card and persist sequential ``sort_order`` values."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        try:
            target_exists = target_column in self._column_ids()
        except TypeError as exc:
            raise KanbanValidationError("Target column ID must be hashable") from exc
        if not target_exists:
            raise KanbanUnknownColumnError(f"Unknown target column: {target_column!r}")
        card = self._require_card(card_id)
        old_card = clone(card)
        old_column = card["column"]
        old_column_was_partial = self._column_has_partial_card_data(old_column)
        target_column_was_partial = self._column_has_partial_card_data(target_column)
        global_was_partial = self._has_more
        old_column_in_prefix = not old_column_was_partial or self._offset_contains_card(
            card_id, old_column
        )
        old_global_in_prefix = not global_was_partial or self._offset_contains_card(card_id, None)
        source_cards = self._manual_cards_for_column(old_column)
        old_index = next(index for index, item in enumerate(source_cards) if item["id"] == card_id)
        old_sort_order = card.get("sort_order")
        if target_column != old_column:
            self._check_column_accepts(target_column)
        target_data = self.get_column(target_column)
        if target_data and target_data.get("locked"):
            raise KanbanValidationError(f"Column {target_column!r} is locked")

        source_cards.pop(old_index)
        if target_column == old_column:
            target_cards = source_cards
        else:
            target_cards = self._manual_cards_for_column(target_column)
        insertion_index = (
            len(target_cards)
            if target_index is None
            else max(
                0,
                min(_validated_index(target_index, "target_index"), len(target_cards)),
            )
        )
        if target_column == old_column and insertion_index == old_index:
            return True

        affected_cards = [card]
        snapshot = {item["id"]: clone(item) for item in affected_cards}
        card["column"] = target_column
        card["updated_at"] = datetime.now(self.timezone).isoformat()
        if target_column != old_column:
            self._adjust_column_total(old_column, -1)
            self._adjust_column_total(target_column, 1)
        target_cards.insert(insertion_index, card)
        card["sort_order"] = self._rank_for_insertion(target_cards, insertion_index)
        prospective_target_offset = self._loaded_offsets.get(target_column, 0)
        if target_column == old_column and old_column_in_prefix:
            prospective_target_offset -= 1
        target_column_in_prefix = (
            not target_column_was_partial
            or self._offset_contains_card(
                card_id,
                target_column,
                offset=max(0, prospective_target_offset),
            )
        )
        prospective_global_offset = self._loaded_offsets.get(None, 0) - int(old_global_in_prefix)
        target_global_in_prefix = not global_was_partial or self._offset_contains_card(
            card_id,
            None,
            offset=max(0, prospective_global_offset),
        )
        if target_column == old_column:
            self._adjust_loaded_offsets(
                target_column,
                int(target_column_in_prefix) - int(old_column_in_prefix),
                int(target_global_in_prefix) - int(old_global_in_prefix),
            )
        else:
            self._adjust_loaded_offsets(old_column, -int(old_column_in_prefix), 0)
            self._adjust_loaded_offsets(
                target_column,
                int(target_column_in_prefix),
                int(target_global_in_prefix) - int(old_global_in_prefix),
            )

        event_type = "card_reordered" if old_column == target_column else "card_moved"
        callback_name = "on_card_reordered" if old_column == target_column else "on_card_moved"
        event = create_event(
            event_type,
            source=source,
            card_id=card_id,
            old_column=old_column,
            new_column=target_column,
            old_index=old_index,
            new_index=insertion_index,
            old_sort_order=old_sort_order,
            new_sort_order=card.get("sort_order"),
            card_data=clone(card),
            old_card_data=old_card,
            column_data=target_data,
            changed_cards=self._changed_order_cards(snapshot, {old_column, target_column}),
        )
        reason = self._invoke_callback(callback_name, event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            for snapshot_id, snapshot_card in snapshot.items():
                self._cards[snapshot_id] = snapshot_card
            self._restore_paging_metadata(rollback_state)
            self._action_cancelled(event, reason)
            return False
        if self.incremental_card_rendering:
            self._render_card_move(card_id, old_column, target_column)
        else:
            self.refresh()
        return True

    def reorder_card(self, card_id: Any, target_index: int, *, source: str = "api") -> bool:
        """Reorder a card within its current column."""

        return self.move_card(card_id, self._require_card(card_id)["column"], target_index, source=source)

    def apply_batch(self, operations: Iterable[Mapping[str, Any]], *, source: str = "batch") -> bool:
        """Apply imports, bulk edits, and bulk moves as one durable transaction.

        Supported operation names are ``add_card``, ``update_card``,
        ``delete_card``, ``move_card``, and their column equivalents.
        """

        self._ensure_mutation_allowed()
        if self._batch_events is not None:
            raise KanbanValidationError("Nested batches are not supported")
        before = self._capture_internal_state()
        self._batch_events = []
        dispatch: dict[str, Callable[..., Any]] = {
            "add_card": self.add_card,
            "update_card": self.update_card,
            "delete_card": self.delete_card,
            "move_card": self.move_card,
            "add_column": self.add_column,
            "update_column": self.update_column,
            "delete_column": self.delete_column,
            "move_column": self.move_column,
        }
        rejected = False
        try:
            for raw_operation in operations:
                operation = dict(raw_operation)
                name = str(operation.pop("operation", operation.pop("type", "")))
                callback = dispatch.get(name)
                if callback is None:
                    raise KanbanValidationError(f"Unsupported batch operation: {name!r}")
                operation.setdefault("source", source)
                outcome = callback(**operation)
                if outcome is None or outcome is False:
                    rejected = True
                    break
            events = self._batch_events
        except Exception:
            self._history_suspended = True
            try:
                self._restore_internal_state(before)
            finally:
                self._history_suspended = False
            raise
        finally:
            self._batch_events = None
        if rejected:
            self._history_suspended = True
            try:
                self._restore_internal_state(before)
            finally:
                self._history_suspended = False
            return False
        if not events:
            return True

        if self._persistence is not None:
            self._set_persistence_status("saving", "Saving batch...")

            def succeeded(result: MutationResult) -> None:
                self._board_revision = result.board_revision or self._board_revision
                self._apply_canonical_result({}, result)
                self._record_history(before)

            def failed(error: Exception | MutationResult) -> None:
                self._history_suspended = True
                try:
                    if isinstance(error, MutationResult) and error.conflict and error.conflict.server_data:
                        self.set_data(error.conflict.server_data)
                        self._board_revision = error.conflict.actual_revision
                        self._clear_history()
                        self.refresh_from_source()
                    else:
                        self._restore_internal_state(before)
                finally:
                    self._history_suspended = False
                reason = error.reason if isinstance(error, MutationResult) else str(error)
                self._action_cancelled(
                    create_event("batch_failed", source=source, operation_count=len(events)),
                    reason or "Batch save failed",
                )

            self._persistence.submit_batch(events, on_success=succeeded, on_failure=failed)
            return True

        event = create_event(
            "batch_changed",
            source=source,
            operations=[item.to_dict() for item in events],
            columns=self.get_columns(),
            cards=self.get_all_cards(),
        )
        reason = self._invoke_callback("on_data_changed", event, cancellable=True)
        if reason:
            self._restore_internal_state(before)
            self._action_cancelled(event, reason)
            return False
        self._record_history(before)
        return True

    def get_card(self, card_id: Any) -> dict[str, Any] | None:
        """Return a defensive card copy, or ``None`` when not found."""

        try:
            card = self._cards.get(card_id)
        except TypeError as exc:
            raise KanbanValidationError("Card ID must be hashable") from exc
        return clone(card) if card is not None else None

    def get_all_cards(self) -> list[dict[str, Any]]:
        """Return all cards in owned insertion order."""

        return clone(list(self._cards.values()))

    def get_cards_by_column(self, column_id: Any) -> list[dict[str, Any]]:
        """Return cards in the column's current configured display order."""

        if column_id not in self._column_ids():
            raise KanbanUnknownColumnError(f"Unknown column: {column_id!r}")
        return clone(self._ordered_cards_for_column(column_id))

    # ------------------------------------------------------------------
    # Column data API
    # ------------------------------------------------------------------
    def add_column(self, column_data: Mapping[str, Any], *, source: str = "api") -> dict[str, Any] | None:
        """Append a column and emit a cancellable creation event."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        column = validate_column(column_data)
        if column["id"] in self._column_ids():
            raise KanbanDuplicateIDError(f"Duplicate column ID: {column['id']!r}")
        self._columns_data.append(column)
        self._column_totals[column["id"]] = 0
        self._loaded_offsets[column["id"]] = 0
        event = create_event(
            "column_created",
            source=source,
            column_id=column["id"],
            column_data=clone(column),
            index=len(self._columns_data) - 1,
        )
        reason = self._invoke_callback("on_column_created", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            self._columns_data.pop()
            self._column_totals.pop(column["id"], None)
            self._loaded_offsets.pop(column["id"], None)
            self._action_cancelled(event, reason)
            return None
        if self.incremental_column_rendering:
            self._render_column_add(column["id"])
        else:
            self.refresh()
        return clone(column)

    def update_column(
        self,
        column_id: Any,
        new_data: Mapping[str, Any],
        *,
        source: str = "api",
    ) -> dict[str, Any] | None:
        """Update a column, including atomically renaming its ID."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        if not isinstance(new_data, Mapping):
            raise KanbanValidationError("Column update data must be a mapping")
        index = self._column_index(column_id)
        old = clone(self._columns_data[index])
        updated = validate_column({**old, **new_data})
        if self.immutable_column_ids and updated["id"] != column_id:
            raise KanbanValidationError("Column IDs are immutable by default")
        new_id = updated["id"]
        if new_id != column_id and new_id in self._column_ids():
            raise KanbanDuplicateIDError(f"Duplicate column ID: {new_id!r}")
        affected_card_ids = [card_id for card_id, card in self._cards.items() if card["column"] == column_id]
        self._columns_data[index] = updated
        if new_id != column_id:
            for card in self._cards.values():
                if card["column"] == column_id:
                    card["column"] = new_id
            if column_id in self._column_sorts:
                self._column_sorts[new_id] = self._column_sorts.pop(column_id)
            self._column_totals[new_id] = self._column_totals.pop(column_id, 0)
            self._loaded_offsets[new_id] = self._loaded_offsets.pop(column_id, 0)

        event = create_event(
            "column_updated",
            source=source,
            column_id=new_id,
            old_column_id=column_id,
            column_data=clone(updated),
            old_column_data=old,
            changed_fields={key: clone(value) for key, value in updated.items() if old.get(key) != value},
            affected_cards=self.get_cards_by_column(new_id),
        )
        reason = self._invoke_callback("on_column_updated", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            self._columns_data[index] = old
            for affected_card_id in affected_card_ids:
                self._cards[affected_card_id]["column"] = column_id
            if new_id != column_id and new_id in self._column_sorts:
                self._column_sorts[column_id] = self._column_sorts.pop(new_id)
            if new_id != column_id:
                self._column_totals[column_id] = self._column_totals.pop(new_id, 0)
                self._loaded_offsets[column_id] = self._loaded_offsets.pop(new_id, 0)
            self._action_cancelled(event, reason)
            return None
        if updated == old and new_id == column_id:
            return clone(updated)
        if self.incremental_column_rendering:
            self._render_column_update(column_id, new_id)
        else:
            self.refresh()
        return clone(updated)

    def delete_column(self, column_id: Any, *, source: str = "api") -> bool:
        """Delete an empty column. Cards must be moved or deleted first."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        index = self._column_index(column_id)
        if self._effective_column_total(column_id) > 0:
            raise KanbanValidationError("Cannot delete a column while it still contains cards")
        column = self._columns_data.pop(index)
        column_total = self._column_totals.pop(column_id, 0)
        loaded_offset = self._loaded_offsets.pop(column_id, 0)
        event = create_event(
            "column_deleted",
            source=source,
            column_id=column_id,
            column_data=clone(column),
            old_index=index,
        )
        reason = self._invoke_callback("on_column_deleted", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            self._columns_data.insert(index, column)
            self._column_totals[column_id] = column_total
            self._loaded_offsets[column_id] = loaded_offset
            self._action_cancelled(event, reason)
            return False
        self._column_sorts.pop(column_id, None)
        if self.incremental_column_rendering:
            self._render_column_delete(column_id)
        else:
            self.refresh()
        return True

    def move_column(self, column_id: Any, target_index: int, *, source: str = "api") -> bool:
        """Move a column in the board's ordered column list."""

        self._ensure_mutation_allowed()
        rollback_state = self._capture_internal_state()
        old_index = self._column_index(column_id)
        new_index = max(
            0,
            min(
                _validated_index(target_index, "target_index"),
                len(self._columns_data) - 1,
            ),
        )
        if old_index == new_index:
            return True
        column = self._columns_data.pop(old_index)
        self._columns_data.insert(new_index, column)
        event = create_event(
            "column_reordered",
            source=source,
            column_id=column_id,
            old_index=old_index,
            new_index=new_index,
            column_data=clone(column),
            columns=self.get_columns(),
        )
        reason = self._invoke_callback("on_column_reordered", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event, rollback_state=rollback_state)
        if reason:
            self._columns_data.pop(new_index)
            self._columns_data.insert(old_index, column)
            self._action_cancelled(event, reason)
            return False
        if self.incremental_column_rendering:
            self._layout_column_widgets()
        else:
            self.refresh()
        return True

    def get_column(self, column_id: Any) -> dict[str, Any] | None:
        """Return a defensive copy of one column, or ``None``."""

        for column in self._columns_data:
            if column["id"] == column_id:
                return clone(column)
        return None

    def get_columns(self) -> list[dict[str, Any]]:
        """Return columns in current board order."""

        return clone(self._columns_data)

    def get_style(self) -> dict[str, Any]:
        """Return the board's complete style snapshot, including nested maps."""

        snapshot = merge_theme(self.theme)
        snapshot["priority_colors"] = clone(self.priority_colors)
        snapshot["tag_colors"] = clone(self.tag_colors)
        snapshot["font_config"] = dict(self.font_config)
        return snapshot

    def get_data(self) -> BoardData:
        """Return mutable board data without view-specific UI state."""

        return {
            "columns": self.get_columns(),
            "cards": self.get_all_cards(),
        }

    # ------------------------------------------------------------------
    # Bulk data and state API
    # ------------------------------------------------------------------
    def refresh_from_source(self) -> bool:
        """Load the board asynchronously from the configured data source."""

        if self._persistence is None:
            return False
        query = CardQuery(
            search=self._search_query if self.server_side_query else "",
            filters=clone(self._filters) if self.server_side_query else {},
            sort_key=self._global_sort[0] if self.server_side_query else "manual",
            reverse=self._global_sort[1] if self.server_side_query else False,
            limit=self.page_size,
            completion_field=self.completion_field,
            completed_columns=tuple(self.completed_columns),
            timezone_name=self.timezone_name,
        )

        def loaded(result: Any) -> None:
            self._board_revision = result.board_revision
            totals = clone(result.column_totals)
            offsets = {
                column["id"]: sum(1 for card in result.cards if card["column"] == column["id"])
                for column in result.columns
            }
            offsets[None] = len(result.cards)
            self.set_data({"columns": result.columns, "cards": result.cards})
            self._column_totals = totals
            self._loaded_offsets = offsets
            self._has_more = bool(result.has_more)
            self._sync_paging_metadata_view()
            self._clear_history()

        def failed(exc: Exception) -> None:
            self._emit_error(exc, create_event("board_load_failed", source="data_source"))

        self._persistence.load(self.board_id, query, on_success=loaded, on_failure=failed)
        return True

    def query_source(self, query: CardQuery, *, append: bool = False) -> bool:
        """Run a server-side card query and update the visible page."""

        if self._persistence is None:
            return False

        def loaded(page: Any) -> None:
            self._board_revision = page.board_revision or self._board_revision
            totals = clone(self._column_totals)
            if query.column_id is None:
                totals = clone(page.column_totals)
            else:
                totals.update(clone(page.column_totals))
            offsets = clone(self._loaded_offsets)
            if append:
                merged = {card["id"]: card for card in self.get_all_cards()}
                merged.update({card["id"]: card for card in page.cards})
                self.set_cards(merged.values())
            elif query.column_id is not None:
                retained = [card for card in self.get_all_cards() if card["column"] != query.column_id]
                self.set_cards([*retained, *page.cards])
            else:
                self.set_cards(page.cards)
            if query.column_id is None:
                offsets = {
                    column["id"]: sum(1 for card in self._cards.values() if card["column"] == column["id"])
                    for column in self._columns_data
                }
            offsets[query.column_id] = query.offset + len(page.cards)
            self._column_totals = totals
            self._loaded_offsets = offsets
            self._has_more = bool(page.has_more)
            self._sync_paging_metadata_view()
            self._clear_history()

        def failed(exc: Exception) -> None:
            self._emit_error(exc, create_event("card_query_failed", source="data_source"))

        self._persistence.query(self.board_id, query, on_success=loaded, on_failure=failed)
        return True

    def load_next_page(self, column_id: Any | None = None) -> bool:
        """Append the next lazy page, optionally for one column."""

        fallback = (
            len(self._cards)
            if column_id is None
            else sum(1 for card in self._cards.values() if card["column"] == column_id)
        )
        offset = self._loaded_offsets.get(column_id, fallback)
        query = CardQuery(
            column_id=column_id,
            search=self._search_query,
            filters=clone(self._filters),
            sort_key=_canonical_sort_key((self._column_sorts.get(column_id, self._global_sort))[0]),
            reverse=(self._column_sorts.get(column_id, self._global_sort))[1],
            offset=offset,
            limit=self.page_size,
            completion_field=self.completion_field,
            completed_columns=tuple(self.completed_columns),
            timezone_name=self.timezone_name,
        )
        return self.query_source(query, append=True)

    def _schedule_poll(self) -> None:
        if self.poll_interval_ms <= 0 or self._persistence is None:
            return
        self._poll_after_id = self.after(self.poll_interval_ms, self._poll_changes)

    def _poll_changes(self) -> None:
        self._poll_after_id = None
        if self._persistence is None:
            return

        def received(page: Any) -> None:
            if page.events:
                self.refresh_from_source()
            self._board_revision = page.board_revision or self._board_revision
            self._schedule_poll()

        def failed(exc: Exception) -> None:
            self.logger.warning("Kanban change poll failed: %s", exc)
            self._schedule_poll()

        self._persistence.changes(
            self.board_id,
            self._board_revision,
            on_success=received,
            on_failure=failed,
        )

    def load_data(self, data: Mapping[str, Any]) -> None:
        """Alias for :meth:`set_data`, useful for database-backed loading."""

        self.set_data(data)

    def set_data(self, data: Mapping[str, Any]) -> None:
        """Replace columns and cards without touching persistence callbacks."""

        if not isinstance(data, Mapping):
            raise KanbanValidationError("Data must be a mapping")
        state = self.get_state()
        state["columns"] = data.get("columns", state["columns"])
        state["cards"] = data.get("cards", state["cards"])
        self.set_state(state)

    def load_cards(self, cards: Iterable[Mapping[str, Any]]) -> None:
        """Alias for :meth:`set_cards`, useful for adapter-style code."""

        self.set_cards(cards)

    def set_cards(self, cards: Iterable[Mapping[str, Any]]) -> None:
        """Replace all cards without firing persistence callbacks."""

        normalized = validate_cards(cards, self._column_ids())
        for card in normalized:
            validate_card_values(card, self.fields)
        if self.incremental_card_rendering:
            self._replace_cards_incrementally(normalized, sync_view=False)
            self._recompute_local_paging_metadata()
            self._sync_card_view()
        else:
            self._cards = {card["id"]: card for card in normalized}
            if self._selected_card_id not in self._cards:
                self._selected_card_id = None
            self._recompute_local_paging_metadata()
            self.refresh()

    def set_columns(self, columns: Iterable[Mapping[str, Any]]) -> None:
        """Replace columns after ensuring existing cards remain valid."""

        normalized = validate_columns(columns)
        ids = {column["id"] for column in normalized}
        unknown = {card["column"] for card in self._cards.values()} - ids
        if unknown:
            raise KanbanUnknownColumnError(
                f"Existing cards reference removed columns: {sorted(map(str, unknown))}"
            )
        old_by_id = {column["id"]: column for column in self._columns_data}
        old_ids = set(old_by_id)
        self._columns_data = normalized
        self._column_sorts = {key: value for key, value in self._column_sorts.items() if key in ids}
        self._recompute_local_paging_metadata()
        if self.incremental_column_rendering and ids == old_ids:
            changed_ids = [column["id"] for column in normalized if column != old_by_id[column["id"]]]
            for changed_id in changed_ids:
                self._render_column_update(changed_id, changed_id)
            self._layout_column_widgets()
        else:
            self.refresh()

    def clear_board(self) -> None:
        """Remove all cards while preserving the configured columns."""

        self._cards.clear()
        self._selected_card_id = None
        self._recompute_local_paging_metadata()
        self._clear_card_widgets()

    def get_state(self) -> dict[str, Any]:
        """Return a defensive snapshot of board data and current view state."""

        return {
            "columns": self.get_columns(),
            "cards": self.get_all_cards(),
            "search": self._search_query,
            "filters": clone(self._filters),
            "sort": {"key": self._global_sort[0], "reverse": self._global_sort[1]},
            "column_sorts": {
                column_id: {"key": value[0], "reverse": value[1]}
                for column_id, value in self._column_sorts.items()
            },
            "selected_card_id": clone(self._selected_card_id),
        }

    def set_state(self, state: Mapping[str, Any]) -> None:
        """Restore data and view state previously produced by ``get_state``."""

        if not isinstance(state, Mapping):
            raise KanbanValidationError("State must be a mapping")
        columns = validate_columns(state.get("columns", self._columns_data))
        cards = validate_cards(state.get("cards", self._cards.values()), {column["id"] for column in columns})
        for card in cards:
            validate_card_values(card, self.fields)
        raw_filters = state.get("filters", {})
        if not isinstance(raw_filters, Mapping):
            raise KanbanValidationError("State 'filters' must be a mapping")
        filters = clone(dict(raw_filters))
        global_sort = self._normalize_sort_state(state.get("sort", {}), "State 'sort'")
        raw_column_sorts = state.get("column_sorts", {})
        if not isinstance(raw_column_sorts, Mapping):
            raise KanbanValidationError("State 'column_sorts' must be a mapping")
        column_ids = {column["id"] for column in columns}
        column_sorts: dict[Any, tuple[str, bool]] = {}
        for column_id, sort_value in raw_column_sorts.items():
            if column_id in column_ids:
                column_sorts[column_id] = self._normalize_sort_state(
                    sort_value,
                    f"State sort for column {column_id!r}",
                )
        selected = state.get("selected_card_id")
        try:
            selected_card_id = selected if selected in {card["id"] for card in cards} else None
        except TypeError:
            selected_card_id = None
        search_query = "" if state.get("search") is None else str(state.get("search", ""))

        columns_unchanged = columns == self._columns_data
        self._columns_data = columns
        self._search_query = search_query
        self._filters = filters
        self._global_sort = global_sort
        self._column_sorts = column_sorts
        self._selected_card_id = selected_card_id
        if hasattr(self, "toolbar"):
            self.toolbar.set_search_query(self._search_query)
            self.toolbar.set_filter_active(bool(self._filters))
        if columns_unchanged and self.incremental_card_rendering:
            self._replace_cards_incrementally(cards, sync_view=False)
            self._recompute_local_paging_metadata()
            self._sync_card_view()
        else:
            self._cards = {card["id"]: card for card in cards}
            self._recompute_local_paging_metadata()
            self.refresh()

    # ------------------------------------------------------------------
    # Search, filters, sorting, and selection
    # ------------------------------------------------------------------
    def search(self, query: str) -> bool:
        """Set the case-insensitive search query and refresh card visibility."""

        if not self.enable_search:
            return False
        old_query = self._search_query
        self._search_query = str(query).strip()
        event = create_event(
            "search_changed", source="toolbar", query=self._search_query, old_query=old_query
        )
        reason = self._invoke_callback("on_search_changed", event, cancellable=True)
        if reason:
            self._search_query = old_query
            self._action_cancelled(event, reason)
            if hasattr(self, "toolbar"):
                self.toolbar.set_search_query(old_query)
            return False
        if self.server_side_query and self._persistence is not None:
            self.query_source(
                CardQuery(
                    search=self._search_query,
                    filters=clone(self._filters),
                    sort_key=self._global_sort[0],
                    reverse=self._global_sort[1],
                    limit=self.page_size,
                    completion_field=self.completion_field,
                    completed_columns=tuple(self.completed_columns),
                    timezone_name=self.timezone_name,
                )
            )
            return True
        if self.incremental_card_rendering:
            self._sync_card_view()
        else:
            self.refresh()
        return True

    def clear_search(self) -> None:
        """Clear the search query and update the toolbar."""

        if self.search("") and hasattr(self, "toolbar"):
            self.toolbar.set_search_query("")

    def apply_filters(self, filters: Mapping[str, Any]) -> bool:
        """Replace active exact-value filters."""

        if not self.enable_filters:
            return False
        if not isinstance(filters, Mapping):
            raise KanbanValidationError("Filters must be a mapping")
        old_filters = clone(self._filters)
        self._filters = clone(dict(filters))
        event = create_event(
            "filter_changed",
            source="toolbar",
            filters=clone(self._filters),
            old_filters=old_filters,
        )
        reason = self._invoke_callback("on_filter_changed", event, cancellable=True)
        if reason:
            self._filters = old_filters
            self._action_cancelled(event, reason)
            return False
        if hasattr(self, "toolbar"):
            self.toolbar.set_filter_active(bool(self._filters), len(self._filters))
            self.toolbar.set_filter_chips(self._filters)
        if self.server_side_query and self._persistence is not None:
            self.query_source(
                CardQuery(
                    search=self._search_query,
                    filters=clone(self._filters),
                    sort_key=self._global_sort[0],
                    reverse=self._global_sort[1],
                    limit=self.page_size,
                    completion_field=self.completion_field,
                    completed_columns=tuple(self.completed_columns),
                    timezone_name=self.timezone_name,
                )
            )
            return True
        if self.incremental_card_rendering:
            self._sync_card_view()
        else:
            self.refresh()
        return True

    def clear_filters(self) -> None:
        """Remove all active filters."""

        self.apply_filters({})

    def sort_cards(
        self,
        sort_key: str,
        reverse: bool = False,
        column_id: Any | None = None,
    ) -> bool:
        """Set global or per-column display sorting without mutating card data."""

        if not self.enable_sorting:
            return False
        if not isinstance(sort_key, str) or sort_key not in self._allowed_sort_keys():
            raise KanbanValidationError(f"Unsupported sort key: {sort_key!r}")
        sort_key = _canonical_sort_key(sort_key)
        if not isinstance(reverse, bool):
            raise KanbanValidationError("reverse must be a boolean")
        if column_id is not None:
            self._column_index(column_id)
            if not self.allow_column_sorting:
                raise KanbanValidationError("Per-column sorting is disabled")
        old_sort = self._column_sorts.get(column_id) if column_id is not None else self._global_sort
        new_sort = (sort_key, bool(reverse))
        if column_id is None:
            self._global_sort = new_sort
        else:
            self._column_sorts[column_id] = new_sort
        if hasattr(self, "toolbar") and column_id is None:
            self.toolbar.set_sort(sort_key, reverse)
        event = create_event(
            "sort_changed",
            source="toolbar",
            sort_key=sort_key,
            reverse=bool(reverse),
            column_id=column_id,
            old_sort=old_sort,
        )
        reason = self._invoke_callback("on_sort_changed", event, cancellable=True)
        if reason:
            if column_id is None:
                self._global_sort = old_sort or ("manual", False)
            elif old_sort is None:
                self._column_sorts.pop(column_id, None)
            else:
                self._column_sorts[column_id] = old_sort
            self._action_cancelled(event, reason)
            return False
        if self.server_side_query and self._persistence is not None:
            self.query_source(
                CardQuery(
                    column_id=column_id,
                    search=self._search_query,
                    filters=clone(self._filters),
                    sort_key=sort_key,
                    reverse=reverse,
                    limit=self.page_size,
                    completion_field=self.completion_field,
                    completed_columns=tuple(self.completed_columns),
                    timezone_name=self.timezone_name,
                )
            )
            return True
        if self.incremental_card_rendering:
            self._sync_card_view([column_id] if column_id is not None else None)
        else:
            self.refresh()
        return True

    def select_card(self, card_id: Any) -> dict[str, Any]:
        """Select one card and update selection visuals."""

        card = self._require_card(card_id)
        if self._selected_card_id == card_id:
            return clone(card)
        previous_id = self._selected_card_id
        self._selected_card_id = card_id
        if previous_id in self._card_widgets:
            self._card_widgets[previous_id].set_selected(False)
        if card_id in self._card_widgets:
            self._card_widgets[card_id].set_selected(True)
        return clone(card)

    def clear_selection(self) -> None:
        """Clear the current single-card selection."""

        selected_id = self._selected_card_id
        self._selected_card_id = None
        if selected_id in self._card_widgets:
            self._card_widgets[selected_id].set_selected(False)
        elif selected_id in self._hidden_card_widgets:
            self._hidden_card_widgets[selected_id].set_selected(False)

    def get_selected_card(self) -> dict[str, Any] | None:
        """Return the selected card copy, if any."""

        return self.get_card(self._selected_card_id) if self._selected_card_id is not None else None

    # ------------------------------------------------------------------
    # Built-in forms and menus
    # ------------------------------------------------------------------
    def start_inline_card_edit(self, card_id: Any, field_key: str = "title") -> bool:
        """Start editing a visible card field without opening another window."""

        if not self.enable_inline_card_editing or not self.enable_builtin_card_form:
            return False
        card_widget = self._card_widgets.get(card_id)
        if card_widget is None:
            return False
        return card_widget.start_inline_edit(field_key)

    def _begin_inline_card_edit(
        self,
        card_widget: CTkKanbanCard,
        field_key: str,
    ) -> bool:
        """Coordinate a single active inline editor across the board."""

        if not self.enable_inline_card_editing or not self.enable_builtin_card_form:
            return False
        current_widget = self._card_widgets.get(card_widget.card_id)
        if current_widget is None:
            return False
        if current_widget is not card_widget:
            return current_widget.start_inline_edit(field_key)
        if not self._request_close_card_form():
            return False
        active = self._inline_edit_card
        if active is not None and active is not card_widget:
            try:
                if active.winfo_exists() and active.editing_field_key is not None:
                    if not active.commit_inline_edit():
                        return False
            except tk.TclError:
                pass
        self._inline_edit_card = card_widget
        self._bind_inline_outside_click()
        if self.enable_card_selection:
            self.select_card(card_widget.card_id)
        return True

    def _bind_inline_outside_click(self) -> None:
        """Watch the owning window so ordinary click-away actions save the edit."""

        pending_after_id = self._inline_outside_unbind_after_id
        if pending_after_id is not None:
            self._inline_outside_unbind_after_id = None
            try:
                self.after_cancel(pending_after_id)
            except (tk.TclError, ValueError):
                pass
        if self._inline_outside_click_binding is not None:
            return
        toplevel = self.winfo_toplevel()
        bind_owner = toplevel._root()
        bind_tag = f"CTkKanbanInlineCapture{id(self)}"
        click_bind_id = tk.Misc.bind_class(
            bind_owner,
            bind_tag,
            "<ButtonPress-1>",
            self._commit_inline_on_outside_press,
            add="+",
        )
        if click_bind_id is None:
            return
        release_bind_id = tk.Misc.bind_class(
            bind_owner,
            bind_tag,
            "<ButtonRelease-1>",
            self._block_inline_release_after_failed_commit,
            add="+",
        )
        if release_bind_id is None:
            self._remove_tcl_binding_callback(
                bind_owner,
                ("bind", bind_tag, "<ButtonPress-1>"),
                click_bind_id,
            )
            return
        tagged_widgets: list[Any] = []
        map_bind_id = tk.Misc.bind_all(
            bind_owner,
            "<Map>",
            self._tag_inline_capture_widget,
            add="+",
        )
        if map_bind_id is None:
            for bind_path, bind_id in (
                (("bind", bind_tag, "<ButtonPress-1>"), click_bind_id),
                (("bind", bind_tag, "<ButtonRelease-1>"), release_bind_id),
            ):
                self._remove_tcl_binding_callback(
                    bind_owner,
                    bind_path,
                    bind_id,
                )
            return
        self._inline_outside_click_binding = (
            toplevel,
            bind_owner,
            bind_tag,
            click_bind_id,
            map_bind_id,
            tagged_widgets,
            release_bind_id,
        )
        for widget in iter_widget_tree(toplevel):
            self._tag_inline_capture_widget(widget=widget)

    def _tag_inline_capture_widget(
        self,
        event: Any = None,
        *,
        widget: Any = None,
    ) -> None:
        """Prepend the capture tag to existing and newly mapped host widgets."""

        binding = self._inline_outside_click_binding
        if binding is None:
            return
        (
            toplevel,
            _bind_owner,
            bind_tag,
            _click_bind_id,
            _map_bind_id,
            tagged_widgets,
            _release_bind_id,
        ) = binding
        target = widget if widget is not None else getattr(event, "widget", None)
        if target is None:
            return
        try:
            if target.winfo_toplevel() is not toplevel:
                return
            tags = tuple(target.bindtags())
            if bind_tag not in tags:
                target.bindtags((bind_tag, *tags))
                tagged_widgets.append(target)
        except (tk.TclError, AttributeError):
            pass

    def _unbind_inline_outside_click(self) -> None:
        if self._inline_outside_click_dispatching:
            if self._inline_outside_unbind_after_id is None:
                self._inline_outside_unbind_after_id = self.after_idle(
                    self._unbind_inline_outside_click
                )
            return
        pending_after_id = self._inline_outside_unbind_after_id
        self._inline_outside_unbind_after_id = None
        if pending_after_id is not None:
            try:
                self.after_cancel(pending_after_id)
            except (tk.TclError, ValueError):
                pass
        binding = getattr(self, "_inline_outside_click_binding", None)
        self._inline_outside_click_binding = None
        self._inline_outside_release_blocked = False
        if binding is None:
            return
        (
            _toplevel,
            bind_owner,
            bind_tag,
            click_bind_id,
            map_bind_id,
            tagged_widgets,
            release_bind_id,
        ) = binding
        for widget in tagged_widgets:
            try:
                tags = tuple(widget.bindtags())
                if bind_tag in tags:
                    widget.bindtags(tuple(tag for tag in tags if tag != bind_tag))
            except tk.TclError:
                pass
        for bind_path, bind_id in (
            (("bind", bind_tag, "<ButtonPress-1>"), click_bind_id),
            (("bind", bind_tag, "<ButtonRelease-1>"), release_bind_id),
            (
                ("bind", "all", "<Map>"),
                map_bind_id,
            ),
        ):
            try:
                self._remove_tcl_binding_callback(
                    bind_owner,
                    bind_path,
                    bind_id,
                )
            except tk.TclError:
                pass

    @staticmethod
    def _remove_tcl_binding_callback(
        bind_owner: Any,
        bind_path: tuple[str, str, str],
        bind_id: str,
    ) -> None:
        """Remove one Tk callback without disturbing sibling binding scripts."""

        script = str(bind_owner.tk.call(*bind_path))
        prefix = f'if {{"[{bind_id} '
        remaining_lines = [
            line
            for line in script.split("\n")
            if not line.startswith(prefix)
        ]
        while remaining_lines and not remaining_lines[-1].strip():
            remaining_lines.pop()
        remaining = "\n".join(remaining_lines)
        bind_owner.tk.call(*bind_path, remaining)
        bind_owner.deletecommand(bind_id)

    @staticmethod
    def _widget_is_within(widget: Any, ancestor: Any) -> bool:
        while widget is not None:
            if widget is ancestor:
                return True
            widget = getattr(widget, "master", None)
        return False

    @staticmethod
    def _inline_target_details(target: Any) -> tuple[Any | None, str | None]:
        """Return the card and field represented by a pointer target."""

        path: list[Any] = []
        widget = target
        while widget is not None:
            path.append(widget)
            if isinstance(widget, CTkKanbanCard):
                field_key = next(
                    (
                        widget._inline_widget_fields[item]
                        for item in path
                        if item in widget._inline_widget_fields
                    ),
                    None,
                )
                return widget.card_id, field_key
            widget = getattr(widget, "master", None)
        return None, None

    def _replay_card_click_after_refresh(
        self,
        card_id: Any,
        field_key: str | None,
        x_root: int,
        y_root: int,
    ) -> None:
        """Complete a click whose original card widget was rebuilt mid-press."""

        card_widget = self._card_widgets.get(card_id)
        if card_widget is None:
            return
        self._handle_card_click(
            card_id,
            SimpleNamespace(x_root=x_root, y_root=y_root),
        )
        if field_key is not None:
            card_widget.start_inline_edit(field_key)

    def _commit_inline_on_outside_press(self, event: Any) -> str | None:
        self._inline_outside_release_blocked = False
        active = self._inline_edit_card
        if active is None or active.editing_field_key is None:
            self._inline_outside_click_dispatching = True
            try:
                self._unbind_inline_outside_click()
            finally:
                self._inline_outside_click_dispatching = False
            return None
        target = getattr(event, "widget", None)
        editor = active.inline_editor
        if editor is not None and self._widget_is_within(target, editor):
            return None
        if target in active._inline_widget_fields:
            return None
        target_was_active_card = self._widget_is_within(target, active)
        target_card_id, target_field_key = self._inline_target_details(target)
        self._inline_outside_click_dispatching = True
        try:
            committed = active.commit_inline_edit()
        finally:
            self._inline_outside_click_dispatching = False
        if committed:
            try:
                target_exists = target is not None and bool(target.winfo_exists())
            except (tk.TclError, AttributeError):
                target_exists = False
            if not target_exists:
                if target_card_id is not None and not target_was_active_card:
                    self.after_idle(
                        self._replay_card_click_after_refresh,
                        target_card_id,
                        target_field_key,
                        int(getattr(event, "x_root", 0) or 0),
                        int(getattr(event, "y_root", 0) or 0),
                    )
                return "break"
            return "break" if target_was_active_card else None
        self._drag_state = None
        self._inline_outside_release_blocked = True
        return "break"

    def _block_inline_release_after_failed_commit(
        self,
        _event: Any,
    ) -> str | None:
        """Stop release-driven controls after their press failed validation."""

        if not self._inline_outside_release_blocked:
            return None
        self._inline_outside_release_blocked = False
        return "break"

    def _request_commit_inline_edit(self) -> bool:
        """Commit the current inline editor before opening another edit surface."""

        active = self._inline_edit_card
        if active is None:
            return True
        try:
            if not active.winfo_exists() or active.editing_field_key is None:
                self._inline_edit_card = None
                self._unbind_inline_outside_click()
                return True
        except tk.TclError:
            self._inline_edit_card = None
            self._unbind_inline_outside_click()
            return True
        return active.commit_inline_edit()

    def _commit_inline_card_edit(
        self,
        card_widget: CTkKanbanCard,
        field_key: str,
        value: Any,
    ) -> bool | str:
        """Save one inline field through the normal update and persistence path."""

        event = create_event(
            "inline_card_edit_failed",
            source="inline_edit",
            card_id=card_widget.card_id,
            field_key=field_key,
        )
        self._last_cancellation_reason = None
        try:
            updated = self.update_card(
                card_widget.card_id,
                {field_key: value},
                source="inline_edit",
            )
        except KanbanValidationError as exc:
            return str(exc).strip() or exc.__class__.__name__
        except Exception as exc:
            self._emit_error(exc, event)
            return str(exc).strip() or exc.__class__.__name__
        if updated is None:
            return self._last_cancellation_reason or "The change was cancelled"
        if self._inline_edit_card is card_widget:
            self._inline_edit_card = None
        return True

    def _end_inline_card_edit(self, card_widget: CTkKanbanCard) -> None:
        if self._inline_edit_card is card_widget:
            self._inline_edit_card = None
            self._unbind_inline_outside_click()

    def _begin_default_card_edit(self, card_id: Any) -> None:
        """Use inline title editing when available, otherwise retain form behavior."""

        if self.start_inline_card_edit(card_id, "title"):
            return
        self.open_edit_card_form(card_id)

    def _open_card_form(
        self,
        *,
        title: str,
        initial_data: dict[str, Any],
        on_submit: Callable[[dict[str, Any]], bool | str | None],
    ) -> None:
        """Open a generated card form using the configured presentation mode."""

        if not self._request_close_card_form():
            return
        if self.card_form_mode == "popup":
            dialog: CardFormDialog
            dialog = CardFormDialog(
                self,
                self.fields,
                self.theme,
                title=title,
                initial_data=initial_data,
                on_submit=on_submit,
                on_close=lambda: self._card_form_dialog_closed(dialog),
                confirm_discard=self.confirm_discard_changes,
            )
            self._card_form_dialog = dialog
            return

        panel = CardFormFrame(
            self,
            self.fields,
            self.theme,
            title=title,
            initial_data=initial_data,
            on_submit=on_submit,
            on_close=self._close_card_form,
            confirm_discard=self.confirm_discard_changes,
            width=400,
            fg_color=self.theme["panel_fg_color"],
            border_color=self.theme["panel_border_color"],
            border_width=self.theme["panel_border_width"],
            corner_radius=self.theme["panel_corner_radius"],
        )
        self._card_form_panel = panel
        panel.grid(
            row=0,
            column=1,
            rowspan=2 if self.show_toolbar else 1,
            sticky="nsew",
            padx=(0, self.board_padding),
            pady=self.board_padding,
        )
        panel.after_idle(panel.focus_first_control)

    def _request_close_card_form(self) -> bool:
        """Ask the active form to close and report whether it accepted."""

        panel = self._card_form_panel
        if panel is not None:
            panel._close()
            return self._card_form_panel is not panel
        dialog = self._card_form_dialog
        if dialog is not None:
            dialog._close()
            return self._card_form_dialog is not dialog
        return True

    def _close_card_form(self) -> None:
        """Close the active embedded or popup card form, if one exists."""

        panel = self._card_form_panel
        self._card_form_panel = None
        if panel is not None:
            try:
                if panel.winfo_exists():
                    panel.destroy()
            except tk.TclError:
                pass
        dialog = self._card_form_dialog
        self._card_form_dialog = None
        if dialog is not None:
            dialog._close()

    def _card_form_dialog_closed(self, dialog: CardFormDialog) -> None:
        if self._card_form_dialog is dialog:
            self._card_form_dialog = None

    def open_add_card_form(self, column_id: Any | None = None) -> None:
        """Open the generated add form, or notify an external form callback."""

        if not self._request_commit_inline_edit():
            return
        if column_id is None:
            column_id = next(
                (column["id"] for column in self._columns_data if not column.get("locked")), None
            )
        if column_id is None:
            return
        self._column_index(column_id)
        if not self.enable_builtin_card_form:
            event = create_event(
                "add_card_requested",
                source="ui",
                column_id=column_id,
                column_data=self.get_column(column_id),
            )
            self._invoke_callback("on_add_card_requested", event)
            return
        defaults = {
            field["key"]: clone(field.get("default"))
            for field in self.fields
            if field.get("default") is not None
        }

        def submit(data: dict[str, Any]) -> bool:
            data["column"] = column_id
            if self.data_source is None or not self.use_temporary_ids:
                data.setdefault("id", self.id_factory() if self.id_factory else generate_card_id(self._cards))
            result = self.add_card(data, source="form")
            if result is not None:
                return True
            if self._last_cancellation_reason == "Action cancelled by callback":
                return False
            return self._last_cancellation_reason or "The action was cancelled"

        self._open_card_form(
            title=f"Add card to {self.get_column(column_id)['title']}",
            initial_data=defaults,
            on_submit=submit,
        )

    def open_edit_card_form(self, card_id: Any) -> None:
        """Open the generated edit form, or notify an external form callback."""

        if not self._request_commit_inline_edit():
            return
        card = self._require_card(card_id)
        if not self.enable_builtin_card_form:
            event = create_event("edit_card_requested", source="ui", card_id=card_id, card_data=clone(card))
            self._invoke_callback("on_edit_card_requested", event)
            return

        def submit(data: dict[str, Any]) -> bool:
            result = self.update_card(card_id, data, source="form")
            if result is not None:
                return True
            if self._last_cancellation_reason == "Action cancelled by callback":
                return False
            return self._last_cancellation_reason or "The action was cancelled"

        self._open_card_form(
            title="Edit card",
            initial_data=clone(card),
            on_submit=submit,
        )

    def request_delete_card(self, card_id: Any) -> bool:
        """Ask for confirmation, when configured, then delete a card."""

        card = self._require_card(card_id)
        if self.confirm_delete:
            confirmed = messagebox.askyesno(
                "Delete card",
                f"Delete '{card['title']}'?",
                parent=self.winfo_toplevel(),
            )
            if not confirmed:
                return False
        return self.delete_card(card_id, source="context_menu")

    def _create_menu(self, parent: Any | None = None) -> tk.Menu:
        """Create a Tk menu styled from the current board theme."""

        menu = tk.Menu(parent or self, tearoff=False)
        try:
            menu.configure(
                background=self._appearance_color(self.theme["menu_fg_color"]),
                foreground=self._appearance_color(self.theme["menu_text_color"]),
                activebackground=self._appearance_color(self.theme["menu_hover_color"]),
                activeforeground=self._appearance_color(self.theme["menu_hover_text_color"]),
                disabledforeground=self._appearance_color(self.theme["menu_disabled_text_color"]),
                borderwidth=int(self.theme["menu_border_width"]),
                relief="flat",
            )
            menu_font = self.theme.get("menu_font")
            if menu_font is not None:
                menu.configure(font=menu_font)
        except tk.TclError:
            pass
        return menu

    def _show_add_menu(self, button: Any) -> None:
        available = [column for column in self._columns_data if not column.get("locked")]
        if not available:
            return
        if len(available) == 1:
            self.open_add_card_form(available[0]["id"])
            return
        menu = self._create_menu()
        for column in available:
            menu.add_command(
                label=str(column["title"]),
                command=lambda column_id=column["id"]: self.open_add_card_form(column_id),
            )
        self._popup_widget_menu(menu, button)

    def _open_filter_dialog(self, _button: Any = None) -> None:
        FilterDialog(
            self,
            self.fields,
            self.get_all_cards(),
            self.theme,
            current_filters=self._filters,
            on_apply=self.apply_filters,
        )

    def _show_sort_menu(self, button: Any, column_id: Any | None = None) -> None:
        menu = self._create_menu()
        options = [
            ("Manual order", "manual"),
            ("Priority", "priority"),
            ("Due date", "due_date"),
            ("Created date", "created_at"),
            ("Updated date", "updated_at"),
            ("Title", "title"),
        ]
        known = {key for _, key in options}
        options.extend(
            (field["label"], field["key"])
            for field in self.fields
            if field.get("sortable") and field["key"] not in known
        )
        for label, key in options:
            submenu = self._create_menu(menu)
            submenu.add_command(label="Ascending", command=lambda k=key: self.sort_cards(k, False, column_id))
            submenu.add_command(label="Descending", command=lambda k=key: self.sort_cards(k, True, column_id))
            menu.add_cascade(label=label, menu=submenu)
        self._popup_widget_menu(menu, button)

    def _show_column_menu(self, column_id: Any, button: Any) -> None:
        menu = self._create_menu()
        menu.add_command(label="Add card", command=lambda: self.open_add_card_form(column_id))
        if self.enable_sorting and self.allow_column_sorting:
            menu.add_command(label="Sort column...", command=lambda: self._show_sort_menu(button, column_id))
        width_menu = self._create_menu(menu)
        width_menu.add_command(
            label="Narrow", command=lambda: self.set_column_width(self.min_column_width, column_id)
        )
        width_menu.add_command(
            label="Default", command=lambda: self.set_column_width(self.column_width, column_id)
        )
        width_menu.add_command(
            label="Wide", command=lambda: self.set_column_width(self.max_column_width, column_id)
        )
        menu.add_cascade(label="Column width", menu=width_menu)
        self._popup_widget_menu(menu, button)

    def _show_card_context_menu(self, card_id: Any, event: Any) -> None:
        if card_id not in self._cards:
            return
        menu = self._create_menu()
        menu.add_command(
            label="Open",
            command=lambda: self._invoke_ui_action(
                lambda: self._open_card(card_id),
                "card_open_failed",
                card_id=card_id,
            ),
        )
        menu.add_command(
            label="Edit",
            command=lambda: self._invoke_ui_action(
                lambda: self._begin_default_card_edit(card_id),
                "card_edit_failed",
                card_id=card_id,
            ),
        )
        menu.add_command(
            label="Delete",
            command=lambda: self._invoke_ui_action(
                lambda: self.request_delete_card(card_id),
                "card_delete_failed",
                card_id=card_id,
            ),
        )
        menu.add_separator()
        menu.add_command(
            label="Duplicate",
            command=lambda: self._invoke_ui_action(
                lambda: self.duplicate_card(card_id, source="context_menu"),
                "card_duplicate_failed",
                card_id=card_id,
            ),
        )
        move_menu = self._create_menu(menu)
        for column in self._columns_data:
            state = (
                "disabled"
                if column.get("locked") or column["id"] == self._cards[card_id]["column"]
                else "normal"
            )
            move_menu.add_command(
                label=str(column["title"]),
                state=state,
                command=lambda column_id=column["id"]: self._invoke_ui_action(
                    lambda: self.move_card(card_id, column_id, source="context_menu"),
                    "card_move_failed",
                    card_id=card_id,
                    column_id=column_id,
                ),
            )
        menu.add_cascade(label="Move to", menu=move_menu)
        if self.card_context_menu_items:
            menu.add_separator()
        event_data = create_event(
            "card_context_action",
            source="context_menu",
            card_id=card_id,
            card_data=self.get_card(card_id),
        )
        for item in self.card_context_menu_items:
            if item.get("separator_before"):
                menu.add_separator()
            enabled = item.get("enabled", True)
            if callable(enabled):
                try:
                    enabled = bool(enabled(clone(event_data)))
                except Exception as exc:
                    self._emit_error(exc, event_data)
                    enabled = False
            menu.add_command(
                label=str(item["label"]),
                state="normal" if enabled else "disabled",
                command=lambda action=item["callback"]: self._invoke_context_action(
                    action,
                    event_data,
                ),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _invoke_context_action(
        self,
        action: Callable[[dict[str, Any]], Any],
        event: dict[str, Any],
    ) -> None:
        try:
            action(clone(event))
        except Exception as exc:
            self._emit_error(exc, event)

    def _invoke_ui_action(
        self,
        action: Callable[[], Any],
        event_type: str,
        **payload: Any,
    ) -> None:
        try:
            action()
        except Exception as exc:
            self._emit_error(exc, create_event(event_type, source="ui", **payload))

    @staticmethod
    def _popup_widget_menu(menu: tk.Menu, widget: Any) -> None:
        widget.update_idletasks()
        try:
            menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _clear_toolbar_state(self) -> None:
        if self._search_query:
            self.clear_search()
        if self._filters:
            self.clear_filters()

    # ------------------------------------------------------------------
    # Internal data helpers
    # ------------------------------------------------------------------
    def _allowed_sort_keys(self) -> set[str]:
        allowed = {
            "manual",
            "priority",
            "due_date",
            "created_date",
            "created_at",
            "updated_date",
            "updated_at",
            "title",
        }
        allowed.update(field["key"] for field in self.fields if field.get("sortable"))
        return allowed

    def _normalize_sort_state(self, value: Any, label: str) -> tuple[str, bool]:
        if not isinstance(value, Mapping):
            raise KanbanValidationError(f"{label} must be a mapping")
        sort_key = value.get("key", "manual")
        reverse = value.get("reverse", False)
        if not isinstance(sort_key, str) or sort_key not in self._allowed_sort_keys():
            raise KanbanValidationError(f"{label} has unsupported sort key {sort_key!r}")
        sort_key = _canonical_sort_key(sort_key)
        if not isinstance(reverse, bool):
            raise KanbanValidationError(f"{label} 'reverse' must be a boolean")
        return sort_key, reverse

    def _column_ids(self) -> set[Any]:
        return {column["id"] for column in self._columns_data}

    def _recompute_local_paging_metadata(self) -> None:
        """Treat the currently owned cards as a complete, locally supplied board."""

        counts = {
            column["id"]: sum(1 for card in self._cards.values() if card["column"] == column["id"])
            for column in self._columns_data
        }
        self._column_totals = counts
        self._loaded_offsets = {**counts, None: len(self._cards)}
        self._has_more = False

    def _sync_paging_metadata_view(self) -> None:
        """Refresh count-only widgets after server paging metadata is restored."""

        for column_id in getattr(self, "_column_widgets", {}):
            self._update_column_summary(column_id)
        self._update_toolbar_summary()

    def _column_has_partial_card_data(self, column_id: Any) -> bool:
        loaded = sum(1 for card in self._cards.values() if card["column"] == column_id)
        return self._effective_column_total(column_id) > loaded

    def _offset_contains_card(
        self,
        card_id: Any,
        column_id: Any | None,
        *,
        offset: int | None = None,
    ) -> bool:
        """Return whether a loaded card is inside a server page's consumed prefix."""

        if offset is None:
            if column_id not in self._loaded_offsets:
                return False
            offset = self._loaded_offsets[column_id]
        if offset <= 0:
            return False
        if column_id is None:
            ordered = self._ordered_cards_for_query()
        else:
            card = self._cards.get(card_id)
            if card is None or card["column"] != column_id:
                return False
            ordered = self._ordered_cards_for_column(column_id)
        if self.server_side_query:
            ordered = [card for card in ordered if self._card_matches_view(card)]
        return any(card["id"] == card_id for card in ordered[:offset])

    def _matches_active_server_query(self, card: Mapping[str, Any]) -> bool:
        if not self.server_side_query:
            return True
        return self._card_matches_view(dict(card))

    def _adjust_loaded_offsets(
        self,
        column_id: Any,
        column_delta: int,
        global_delta: int,
    ) -> None:
        """Advance or rewind consumed server prefixes after an optimistic write."""

        if column_id in self._loaded_offsets:
            self._loaded_offsets[column_id] = max(
                0,
                self._loaded_offsets[column_id] + column_delta,
            )
        if None in self._loaded_offsets:
            self._loaded_offsets[None] = max(0, self._loaded_offsets[None] + global_delta)

    @staticmethod
    def _sort_position_changed(
        old: Mapping[str, Any],
        new: Mapping[str, Any],
        sort_state: tuple[str, bool],
    ) -> bool:
        """Return whether an update can move a card across a page boundary."""

        sort_key = _canonical_sort_key(sort_state[0])
        if sort_key == "manual":
            return old.get("sort_order") != new.get("sort_order")
        if sort_key == "priority":
            return old.get("priority") != new.get("priority")
        return _card_sort_value(old, sort_key) != _card_sort_value(new, sort_key)

    def _effective_column_total(self, column_id: Any) -> int:
        """Return the best known full count, never less than loaded cards."""

        loaded = sum(1 for card in self._cards.values() if card["column"] == column_id)
        return max(loaded, int(self._column_totals.get(column_id, loaded)))

    def _adjust_column_total(self, column_id: Any, delta: int) -> None:
        """Keep server totals aligned with accepted optimistic mutations."""

        loaded_now = sum(1 for card in self._cards.values() if card["column"] == column_id)
        loaded_before = max(0, loaded_now - delta)
        current = max(loaded_before, int(self._column_totals.get(column_id, loaded_before)))
        self._column_totals[column_id] = max(0, current + delta)

    def _has_partial_card_data(self) -> bool:
        """Return whether the owned card mapping represents only a page."""

        if self._has_more:
            return True
        return any(
            self._effective_column_total(column["id"])
            > sum(1 for card in self._cards.values() if card["column"] == column["id"])
            for column in self._columns_data
        )

    def _normalize_card_values(self, card: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(card)
        if not self.normalize_empty_values:
            return normalized
        for field in self.fields:
            key = field["key"]
            if key in normalized and normalized[key] == "" and not field.get("required"):
                normalized[key] = clone(field.get("empty_value"))
        return normalized

    def _column_index(self, column_id: Any) -> int:
        for index, column in enumerate(self._columns_data):
            if column["id"] == column_id:
                return index
        raise KanbanUnknownColumnError(f"Unknown column: {column_id!r}")

    def _require_card(self, card_id: Any) -> dict[str, Any]:
        try:
            return self._cards[card_id]
        except (KeyError, TypeError) as exc:
            raise KanbanValidationError(f"Unknown card ID: {card_id!r}") from exc

    def _manual_cards_for_column(self, column_id: Any) -> list[dict[str, Any]]:
        indexed = [
            (index, card) for index, card in enumerate(self._cards.values()) if card["column"] == column_id
        ]
        indexed.sort(
            key=lambda pair: (
                pair[1].get("sort_order") is None,
                pair[1].get("sort_order", pair[0]),
                pair[0],
            )
        )
        return [card for _, card in indexed]

    def _next_sort_order(self, column_id: Any) -> int | float:
        """Return an append order without sorting the column's existing cards."""

        highest: int | float = 0
        for card in self._cards.values():
            if card["column"] != column_id:
                continue
            sort_order = card.get("sort_order")
            if isinstance(sort_order, (int, float)) and not isinstance(sort_order, bool):
                highest = max(highest, sort_order)
        if self._column_has_partial_card_data(column_id):
            sparse_gap = max(1024, (self._effective_column_total(column_id) + 1) * 1024)
            return highest + sparse_gap
        return highest + 1

    @staticmethod
    def _rank_for_insertion(ordered: list[dict[str, Any]], index: int) -> float:
        """Return a sparse rank between adjacent cards without renumbering siblings."""

        previous = ordered[index - 1].get("sort_order") if index > 0 else None
        following = ordered[index + 1].get("sort_order") if index + 1 < len(ordered) else None
        previous_rank = float(previous) if isinstance(previous, (int, float)) else None
        following_rank = float(following) if isinstance(following, (int, float)) else None
        if previous_rank is None and following_rank is None:
            return 1024.0
        if previous_rank is None:
            return following_rank - 1024.0
        if following_rank is None:
            return previous_rank + 1024.0
        return previous_rank + (following_rank - previous_rank) / 2.0

    def _ordered_cards_for_column(self, column_id: Any) -> list[dict[str, Any]]:
        cards = self._manual_cards_for_column(column_id)
        sort_key, reverse = self._column_sorts.get(column_id, self._global_sort)
        sort_key = _canonical_sort_key(sort_key)
        if sort_key == "manual":
            return list(reversed(cards)) if reverse else cards
        if sort_key == "priority":
            ranking = {"critical": 0, "high": 1, "medium": 2, "low": 3}

            def key(card: dict[str, Any]) -> Any:
                return (
                    ranking.get(str(card.get("priority", "")).casefold(), 99),
                    searchable_text(card.get("priority")),
                )
        else:

            def key(card: dict[str, Any]) -> Any:
                return comparable_value(_card_sort_value(card, sort_key))

        return sorted(cards, key=key, reverse=reverse)

    def _ordered_cards_for_query(self) -> list[dict[str, Any]]:
        """Order all loaded cards as the active global server query does."""

        cards = list(self._cards.values())
        sort_key, reverse = self._global_sort
        sort_key = _canonical_sort_key(sort_key)
        if sort_key == "manual":
            indexed = list(enumerate(cards))
            indexed.sort(
                key=lambda pair: (
                    pair[1].get("sort_order") is None,
                    comparable_value(pair[1].get("sort_order")),
                    pair[0],
                ),
                reverse=reverse,
            )
            return [card for _, card in indexed]
        if sort_key == "priority":
            ranking = {"critical": 0, "high": 1, "medium": 2, "low": 3}

            def key(card: dict[str, Any]) -> Any:
                return (
                    ranking.get(str(card.get("priority", "")).casefold(), 99),
                    searchable_text(card.get("priority")),
                )
        else:

            def key(card: dict[str, Any]) -> Any:
                return comparable_value(_card_sort_value(card, sort_key))

        return sorted(cards, key=key, reverse=reverse)

    def _card_index(self, card_id: Any) -> int:
        card = self._require_card(card_id)
        return next(
            index
            for index, item in enumerate(self._manual_cards_for_column(card["column"]))
            if item["id"] == card_id
        )

    def _apply_manual_order(self, column_id: Any, ordered: list[dict[str, Any]]) -> None:
        for index, card in enumerate(ordered, start=1):
            card["column"] = column_id
            card["sort_order"] = index

    def _reindex_column(self, column_id: Any) -> None:
        self._apply_manual_order(column_id, self._manual_cards_for_column(column_id))

    def _changed_order_cards(
        self, snapshot: dict[Any, dict[str, Any]], columns: set[Any]
    ) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for card_id, old in snapshot.items():
            card = self._cards.get(card_id)
            if (
                card is not None
                and (card["column"] in columns or old.get("column") in columns)
                and (
                    old.get("column") != card.get("column") or old.get("sort_order") != card.get("sort_order")
                )
            ):
                changed.append(clone(card))
        return changed

    def _check_column_accepts(self, column_id: Any) -> None:
        column = self.get_column(column_id)
        if column is None:
            raise KanbanUnknownColumnError(f"Unknown column: {column_id!r}")
        if column.get("locked"):
            raise KanbanValidationError(f"Column {column_id!r} is locked")
        max_cards = column.get("max_cards")
        if self.enforce_column_limits and max_cards is not None:
            count = self._effective_column_total(column_id)
            if count >= max_cards:
                event = create_event(
                    "move_blocked",
                    source="validation",
                    column_id=column_id,
                    column_data=column,
                    reason="column_limit",
                )
                self._action_cancelled(event, f"Column {column['title']!r} has reached its card limit")
                raise KanbanValidationError(f"Column {column['title']!r} has reached its card limit")

    def _column_accepts_drop(self, column_id: Any, card_id: Any | None = None) -> bool:
        column = self.get_column(column_id)
        if column is None or column.get("locked"):
            return False
        maximum = column.get("max_cards")
        if not self.enforce_column_limits or maximum is None:
            return True
        current_column = self._cards.get(card_id, {}).get("column") if card_id is not None else None
        if current_column == column_id:
            return True
        total = self._effective_column_total(column_id)
        return total < maximum

    def _card_matches_view(self, card: dict[str, Any]) -> bool:
        if self._search_query:
            query = self._search_query.casefold()
            if not any(query in searchable_text(card.get(key)) for key in self._searchable_field_keys):
                return False
        ordinary_filters: dict[str, Any] = {}
        for key, expected in self._filters.items():
            if key == "overdue_only":
                if expected and not self._is_overdue(card):
                    return False
                continue
            if callable(expected):
                actual = card.get("column") if key in {"column", "status"} else card.get(key)
                try:
                    matches = bool(expected(actual, clone(card)))
                except Exception as exc:
                    self._emit_error(
                        exc,
                        create_event(
                            "filter_predicate_failed",
                            source="filter",
                            field=key,
                            card_id=card.get("id"),
                        ),
                    )
                    return False
                if not matches:
                    return False
            else:
                ordinary_filters[key] = expected
        try:
            return card_matches_filters(card, ordinary_filters)
        except Exception as exc:
            self._emit_error(exc, create_event("filter_failed", source="filter", card_id=card.get("id")))
            return False

    def _is_overdue(self, card: dict[str, Any]) -> bool:
        completed = bool(card.get(self.completion_field)) or card.get("column") in self.completed_columns
        if completed:
            return False
        raw_due = card.get("due_date")
        if isinstance(raw_due, date) and not isinstance(raw_due, datetime):
            return raw_due < datetime.now(self.timezone).date()
        if isinstance(raw_due, str) and len(raw_due.strip()) == 10:
            try:
                due_date = date.fromisoformat(raw_due.strip())
            except ValueError:
                pass
            else:
                return due_date < datetime.now(self.timezone).date()
        due = parse_temporal(raw_due)
        if due is None:
            return False
        now = datetime.now(self.timezone)
        return due.astimezone(self.timezone) < now
