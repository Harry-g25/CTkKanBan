"""Main CTkKanbanBoard widget and public data API."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timezone
from math import isfinite
from time import monotonic
from tkinter import messagebox
from typing import Any, Callable, Iterable, Mapping

import customtkinter as ctk

from .card import CTkKanbanCard
from .column import CTkKanbanColumn
from .dialogs import CardFormDialog, CardFormFrame, FilterDialog
from .events import cancellation_reason, create_event
from .exceptions import (
    KanbanDuplicateIDError,
    KanbanUnknownColumnError,
    KanbanValidationError,
)
from .models import BoardData, CardRenderer, ContextMenuItem, KanbanCallback
from .themes import DEFAULT_PRIORITY_COLORS, merge_theme
from .toolbar import CTkKanbanToolbar
from .utils import clone, comparable_value, generate_card_id, parse_temporal, searchable_text
from .validators import (
    validate_card,
    validate_card_values,
    validate_cards,
    validate_column,
    validate_columns,
    validate_context_menu_items,
    validate_fields,
)


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


class CTkKanbanBoard(ctk.CTkFrame):
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
        columns: Iterable[Mapping[str, Any]],
        cards: Iterable[Mapping[str, Any]] | None = None,
        fields: Iterable[Mapping[str, Any]] | None = None,
        *,
        # Layout
        enable_horizontal_scroll: bool = True,
        enable_column_scroll: bool = True,
        column_width: int = 280,
        column_height: int = 600,
        column_gap: int = 12,
        board_padding: int | None = None,
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
        enable_card_hover: bool = True,
        enable_card_selection: bool = True,
        enable_card_context_menu: bool = True,
        enable_card_double_click: bool = True,
        enable_builtin_card_form: bool = True,
        card_form_mode: str = "popup",
        confirm_delete: bool = True,
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
        # Styling and extension points
        theme: Mapping[str, Any] | None = None,
        style: Mapping[str, Any] | None = None,
        priority_colors: Mapping[str, str] | None = None,
        tag_colors: Mapping[str, str] | None = None,
        font_config: Mapping[str, Any] | None = None,
        card_renderer: CardRenderer | None = None,
        card_context_menu_items: Iterable[ContextMenuItem] | None = None,
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
        **kwargs: Any,
    ) -> None:
        column_width = _validated_int(column_width, "column_width", minimum=160)
        column_height = _validated_int(column_height, "column_height", minimum=180)
        column_gap = _validated_int(column_gap, "column_gap", minimum=0)
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
        if filter_mode not in {"hide", "dim"}:
            raise KanbanValidationError("filter_mode must be 'hide' or 'dim'")
        if card_form_mode not in {"popup", "sidepanel"}:
            raise KanbanValidationError("card_form_mode must be 'popup' or 'sidepanel'")
        boolean_options = {
            "enable_horizontal_scroll": enable_horizontal_scroll,
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
            "enable_card_selection": enable_card_selection,
            "enable_card_context_menu": enable_card_context_menu,
            "enable_card_double_click": enable_card_double_click,
            "enable_builtin_card_form": enable_builtin_card_form,
            "confirm_delete": confirm_delete,
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
        }
        for option_name, option_value in boolean_options.items():
            if not isinstance(option_value, bool):
                raise KanbanValidationError(f"{option_name} must be a boolean")

        normalized_columns = validate_columns(columns)
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
            "updated_date",
            "title",
        }
        allowed_sort_keys.update(
            field["key"] for field in normalized_fields if field.get("sortable")
        )
        if not isinstance(default_sort, str) or default_sort not in allowed_sort_keys:
            raise KanbanValidationError(f"Unsupported default sort key: {default_sort!r}")

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
        }
        for callback_name, callback in callbacks.items():
            if callback is not None and not callable(callback):
                raise KanbanValidationError(f"{callback_name} must be callable or None")
        if card_renderer is not None and not callable(card_renderer):
            raise KanbanValidationError("card_renderer must be callable or None")

        self.theme = merge_theme(style_overrides)
        self.style = self.theme
        for font_name, font_value in dict(font_config or {}).items():
            self.theme[f"{font_name}_font"] = font_value
        font_defaults = {
            "card_title_font": {"size": 14, "weight": "bold"},
            "card_body_font": {"size": 12},
            "card_metadata_font": {"size": 11},
            "badge_font": {"size": 10, "weight": "bold"},
            "column_title_font": {"size": 14, "weight": "bold"},
            "column_count_font": {"size": 11, "weight": "bold"},
            "form_title_font": {"size": 20, "weight": "bold"},
            "filter_title_font": {"size": 19, "weight": "bold"},
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
        self.enable_card_hover = enable_card_hover
        self.enable_card_selection = enable_card_selection
        self.enable_card_context_menu = enable_card_context_menu
        self.enable_card_double_click = enable_card_double_click
        self.enable_builtin_card_form = enable_builtin_card_form
        self.card_form_mode = card_form_mode
        self.confirm_delete = confirm_delete
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

        self._callbacks = callbacks

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
        self._empty_label: ctk.CTkLabel | None = None
        self._drag_state: dict[str, Any] | None = None
        self._drag_preview: tk.Toplevel | None = None
        self._drag_preview_position: tuple[int, int] | None = None
        self._indicator_column: CTkKanbanColumn | None = None
        self._highlighted_column: CTkKanbanColumn | None = None
        self._last_cancellation_reason: str | None = None
        self._card_form_panel: CardFormFrame | None = None
        self._card_form_dialog: CardFormDialog | None = None

        self._build_board()

    # ------------------------------------------------------------------
    # Construction and rendering
    # ------------------------------------------------------------------
    def destroy(self) -> None:
        """Cancel deferred cleanup before destroying the board widget."""

        self._cancel_retired_cleanup()
        self._close_card_form()
        super().destroy()

    def _cancel_retired_cleanup(self) -> None:
        """Cancel pending cleanup when parent destruction will handle widgets."""

        if self._retire_after_id is not None:
            try:
                self.after_cancel(self._retire_after_id)
            except (tk.TclError, ValueError):
                pass
            self._retire_after_id = None
        self._retired_card_widgets.clear()

    def _build_board(self) -> None:
        self.grid_rowconfigure(1 if self.show_toolbar else 0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        if self.show_toolbar:
            self.toolbar = CTkKanbanToolbar(
                self,
                self.theme,
                show_search=self.show_search,
                show_filter_button=self.show_filter_button,
                show_sort_button=self.show_sort_button,
                show_add_card_button=self.show_add_card_button,
                show_clear_filters_button=self.show_clear_filters_button,
                on_search=self.search,
                on_filter=self._open_filter_dialog,
                on_sort=self._show_sort_menu,
                on_add=self._show_add_menu,
                on_clear=self._clear_toolbar_state,
            )
            self.toolbar.grid(row=0, column=0, sticky="ew", padx=self.board_padding, pady=(self.board_padding, 0))

        row = 1 if self.show_toolbar else 0
        if self.enable_horizontal_scroll:
            self.board_area: Any = ctk.CTkScrollableFrame(
                self,
                orientation="horizontal",
                fg_color="transparent",
                scrollbar_button_color=self.theme["scrollbar_button_color"],
                scrollbar_button_hover_color=self.theme["scrollbar_button_hover_color"],
            )
        else:
            self.board_area = ctk.CTkFrame(self, fg_color="transparent")
        self.board_area.grid(
            row=row,
            column=0,
            sticky="nsew",
            padx=self.board_padding,
            pady=self.board_padding,
        )
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the current visual board from owned data and view state."""

        self._cancel_retired_cleanup()
        self._clear_drag_visuals()
        for widget in list(self._column_widgets.values()):
            if widget.winfo_exists():
                widget.destroy()
        self._column_widgets.clear()
        self._card_widgets.clear()
        self._hidden_card_widgets.clear()
        if self._empty_label is not None and self._empty_label.winfo_exists():
            self._empty_label.destroy()
            self._empty_label = None

        if not self._columns_data:
            self._empty_label = ctk.CTkLabel(
                self.board_area,
                text="No columns",
                text_color=self.theme["overlay_text_color"],
            )
            self._empty_label.grid(row=0, column=0, padx=30, pady=30)
            return

        card_counts: dict[Any, int] = {column["id"]: 0 for column in self._columns_data}
        for card_data in self._cards.values():
            card_counts[card_data["column"]] += 1

        for column_index, column_data in enumerate(self._columns_data):
            column = self._create_column_widget(column_data, column_index)

            ordered = self._ordered_cards_for_column(column_data["id"])
            visible_count = 0
            for card_data in ordered:
                matches = self._card_matches_view(card_data)
                if not matches and self.filter_mode == "hide":
                    continue
                card = self._create_card_widget(column, card_data)
                if not matches and self.filter_mode == "dim":
                    card.set_dimmed(True)
                visible_count += 1
            column.update_card_count(card_counts[column_data["id"]])
            if visible_count == 0 and self.show_no_results:
                column.show_no_results()
        self._layout_column_widgets()

    def _create_column_widget(self, column_data: Mapping[str, Any], index: int) -> CTkKanbanColumn:
        """Create and position one column widget."""

        if self._empty_label is not None and self._empty_label.winfo_exists():
            self._empty_label.destroy()
            self._empty_label = None
        column = CTkKanbanColumn(
            self.board_area,
            dict(column_data),
            self.theme,
            width=self.column_width,
            height=self.column_height,
            enable_scroll=self.enable_column_scroll,
            show_card_count=self.show_card_count,
            show_add_button=self.show_column_add_button,
            show_menu=self.show_column_menu,
            on_add=self.open_add_card_form,
            on_menu=self._show_column_menu,
            on_drag_press=self._on_column_press,
            on_drag_motion=self._on_column_motion,
            on_drag_release=self._on_column_release,
        )
        column.grid(row=0, column=index, sticky="ns")
        self._column_widgets[column_data["id"]] = column
        return column

    def _layout_column_widgets(self) -> None:
        """Re-grid existing columns in data order without rebuilding them."""

        last_index = len(self._columns_data) - 1
        for index, column_data in enumerate(self._columns_data):
            self._column_widgets[column_data["id"]].grid_configure(
                row=0,
                column=index,
                sticky="ns",
                padx=(0, self.column_gap if index < last_index else 0),
            )

    def _populate_column_widget(self, column_id: Any) -> None:
        """Populate one new or rebuilt column from current card/view state."""

        column = self._column_widgets[column_id]
        for card_data in self._ordered_cards_for_column(column_id):
            matches = self._card_matches_view(card_data)
            if not matches and self.filter_mode == "hide":
                continue
            card = self._create_card_widget(column, card_data)
            if not matches and self.filter_mode == "dim":
                card.set_dimmed(True)
        self._update_column_summary(column_id)

    def _render_column_add(self, column_id: Any) -> None:
        index = self._column_index(column_id)
        self._create_column_widget(self._columns_data[index], index)
        self._update_column_summary(column_id)
        self._layout_column_widgets()

    def _render_column_delete(self, column_id: Any) -> None:
        widget = self._column_widgets.pop(column_id, None)
        if widget is not None:
            widget.destroy()
        self._layout_column_widgets()
        if not self._columns_data:
            self._empty_label = ctk.CTkLabel(
                self.board_area,
                text="No columns",
                text_color=self.theme["overlay_text_color"],
            )
            self._empty_label.grid(row=0, column=0, padx=30, pady=30)

    def _render_column_update(self, old_column_id: Any, new_column_id: Any) -> None:
        """Update column metadata in place while retaining every card widget."""

        index = self._column_index(new_column_id)
        widget = self._column_widgets.pop(old_column_id)
        widget.update_column_data(dict(self._columns_data[index]))
        self._column_widgets[new_column_id] = widget
        if old_column_id != new_column_id:
            refresh_card_content = self.card_renderer is not None or any(
                field["key"] == "column" and field.get("show_on_card")
                for field in self.fields
            )
            affected_card_ids: list[Any] = []
            for card_id, card_data in self._cards.items():
                if card_data["column"] != new_column_id:
                    continue
                affected_card_ids.append(card_id)
                card_widget = self._card_widgets.get(card_id) or self._hidden_card_widgets.get(card_id)
                if card_widget is not None and not refresh_card_content:
                    card_widget.card_data["column"] = new_column_id
            if refresh_card_content:
                for card_id in affected_card_ids:
                    self._discard_card_widget(card_id)
                self._sync_card_view([new_column_id])
        self._layout_column_widgets()

    def _create_card_widget(
        self,
        column: CTkKanbanColumn,
        card_data: Mapping[str, Any],
    ) -> CTkKanbanCard:
        """Create one visible card widget and register it with its column."""

        card = CTkKanbanCard(
            column.body,
            clone(card_data),
            self.fields,
            self.theme,
            card_mode=self.card_mode,
            priority_colors=self.priority_colors,
            tag_colors=self.tag_colors,
            renderer=self.card_renderer,
            on_press=self._on_card_press,
            on_motion=self._on_card_motion,
            on_release=self._on_card_release,
            on_double_click=self._on_card_double_click,
            on_right_click=self._on_card_right_click,
            hover_enabled=self.enable_card_hover,
        )
        column.add_card_widget(card)
        self._card_widgets[card_data["id"]] = card
        if card_data["id"] == self._selected_card_id:
            card.set_selected(True)
        return card

    def _render_card_move(self, card_id: Any, old_column: Any, new_column: Any) -> None:
        """Update only the visual widgets affected by a successful card move."""

        card_data = self._cards[card_id]
        matches = self._card_matches_view(card_data)
        should_render = matches or self.filter_mode == "dim"
        old_column_widget = self._column_widgets[old_column]
        new_column_widget = self._column_widgets[new_column]
        card_widget = self._card_widgets.get(card_id)
        hidden_widget = self._hidden_card_widgets.get(card_id)

        if old_column != new_column and (card_widget is not None or hidden_widget is not None):
            self._discard_card_widget(card_id)
            card_widget = None
            hidden_widget = None

        if should_render:
            if card_widget is None:
                card_widget = self._hidden_card_widgets.pop(card_id, None)
                if card_widget is None:
                    card_widget = self._create_card_widget(new_column_widget, card_data)
                else:
                    self._card_widgets[card_id] = card_widget
            else:
                card_widget.card_data = clone(card_data)
            card_widget.card_data = clone(card_data)
            card_widget.set_dimmed(not matches and self.filter_mode == "dim")
            desired_ids = self._visible_card_ids_for_column(new_column)
            new_column_widget.place_card_widget(card_widget, desired_ids.index(card_id))
        elif card_widget is not None:
            old_column_widget.remove_card_widget(card_widget)
            self._card_widgets.pop(card_id, None)
            card_widget.card_data = clone(card_data)
            self._hidden_card_widgets[card_id] = card_widget
        elif hidden_widget is not None:
            hidden_widget.card_data = clone(card_data)

        for column_id in {old_column, new_column}:
            self._update_column_summary(column_id)

    def _render_card_add(self, card_id: Any) -> None:
        """Render one newly created card without rebuilding existing widgets."""

        card_data = self._cards[card_id]
        column_id = card_data["column"]
        column = self._column_widgets[column_id]
        matches = self._card_matches_view(card_data)
        if matches or self.filter_mode == "dim":
            card_widget = self._create_card_widget(column, card_data)
            card_widget.set_dimmed(not matches and self.filter_mode == "dim")
            sort_key, reverse = self._column_sorts.get(column_id, self._global_sort)
            if sort_key != "manual" or reverse:
                desired_ids = self._visible_card_ids_for_column(column_id)
                column.place_card_widget(card_widget, desired_ids.index(card_id))
        self._update_column_summary(column_id)

    def _render_card_update(
        self,
        old_card_id: Any,
        old_column: Any,
        new_card_id: Any,
        new_column: Any,
    ) -> None:
        """Replace only the changed card widget after an accepted update."""

        self._discard_card_widget(old_card_id)
        self._render_card_add(new_card_id)
        if old_column != new_column:
            self._update_column_summary(old_column)

    def _render_card_delete(self, card_id: Any, column_id: Any) -> None:
        """Remove one card widget and refresh only its column summary."""

        self._discard_card_widget(card_id)
        self._update_column_summary(column_id)

    def _visible_card_ids_for_column(self, column_id: Any) -> list[Any]:
        """Return the IDs represented by widgets in one column's view order."""

        return [
            card["id"]
            for card in self._ordered_cards_for_column(column_id)
            if self._card_matches_view(card) or self.filter_mode == "dim"
        ]

    def _update_column_summary(self, column_id: Any) -> None:
        """Update one column's count and no-results message."""

        column = self._column_widgets[column_id]
        total = sum(1 for card in self._cards.values() if card["column"] == column_id)
        column.update_card_count(total)
        if column.card_widgets:
            column.clear_no_results()
        elif self.show_no_results:
            column.show_no_results()

    def _discard_card_widget(self, card_id: Any) -> None:
        """Destroy a visible or cached card widget and unregister it."""

        widget = self._card_widgets.pop(card_id, None)
        if widget is None:
            widget = self._hidden_card_widgets.pop(card_id, None)
        if widget is None:
            return
        for column in self._column_widgets.values():
            if widget in column.card_widgets:
                column.remove_card_widget(widget)
                break
        widget.destroy()

    def _retire_card_widget(self, card_id: Any) -> None:
        """Detach a card immediately and destroy it later in small batches."""

        widget = self._card_widgets.pop(card_id, None)
        if widget is None:
            widget = self._hidden_card_widgets.pop(card_id, None)
        if widget is None:
            return
        for column in self._column_widgets.values():
            if widget in column.card_widgets:
                column.remove_card_widget(widget)
                break
        widget.pack_forget()
        self._retired_card_widgets.append(widget)
        if self._retire_after_id is None:
            self._retire_after_id = self.after(1, self._drain_retired_card_widgets)

    def _drain_retired_card_widgets(self) -> None:
        """Destroy retired cards incrementally to avoid blocking Tk's event loop."""

        self._retire_after_id = None
        deadline = monotonic() + self.cleanup_time_budget_ms / 1000
        while self._retired_card_widgets:
            widget = self._retired_card_widgets.pop()
            try:
                widget.destroy()
            except tk.TclError:
                pass
            if monotonic() >= deadline:
                break
        if self._retired_card_widgets and self.winfo_exists():
            self._retire_after_id = self.after(1, self._drain_retired_card_widgets)

    def _sync_card_view(self, column_ids: Iterable[Any] | None = None) -> None:
        """Synchronize visibility and order without reconstructing the board."""

        target_ids = list(column_ids) if column_ids is not None else [column["id"] for column in self._columns_data]
        for column_id in target_ids:
            column = self._column_widgets[column_id]
            ordered_cards = self._ordered_cards_for_column(column_id)
            match_by_id = {card["id"]: self._card_matches_view(card) for card in ordered_cards}
            desired_cards = [card for card in ordered_cards if match_by_id[card["id"]] or self.filter_mode == "dim"]
            desired_ids = {card["id"] for card in desired_cards}

            for widget in list(column.card_widgets):
                if widget.card_id not in desired_ids:
                    column.remove_card_widget(widget)
                    self._card_widgets.pop(widget.card_id, None)
                    self._hidden_card_widgets[widget.card_id] = widget

            ordered_widgets: list[CTkKanbanCard] = []
            for card_data in desired_cards:
                card_id = card_data["id"]
                widget = self._card_widgets.get(card_id)
                if widget is None:
                    widget = self._hidden_card_widgets.pop(card_id, None)
                    if widget is None:
                        widget = self._create_card_widget(column, card_data)
                    else:
                        self._card_widgets[card_id] = widget
                widget.set_dimmed(not match_by_id[card_id] and self.filter_mode == "dim")
                ordered_widgets.append(widget)
            column.set_card_widget_order(ordered_widgets)
            self._update_column_summary(column_id)

    def _clear_card_widgets(self) -> None:
        """Detach card widgets now and retire their resources incrementally."""

        card_ids = list({*self._card_widgets, *self._hidden_card_widgets})
        for card_id in card_ids:
            self._retire_card_widget(card_id)
        for column in self._column_widgets.values():
            column.card_widgets.clear()
            column.clear_drop_indicator()
        for column_id in self._column_widgets:
            self._update_column_summary(column_id)

    def _replace_cards_incrementally(self, cards: list[dict[str, Any]], *, sync_view: bool = True) -> None:
        """Replace card data while retaining widgets for byte-for-byte equal cards."""

        replacement = {card["id"]: card for card in cards}
        stale_ids = [
            card_id
            for card_id, old_card in self._cards.items()
            if card_id not in replacement or replacement[card_id] != old_card
        ]
        for card_id in stale_ids:
            self._retire_card_widget(card_id)
        self._cards = replacement
        if self._selected_card_id not in self._cards:
            self._selected_card_id = None
        if sync_view:
            self._sync_card_view()

    # ------------------------------------------------------------------
    # Callback and error handling
    # ------------------------------------------------------------------
    def _invoke_callback(self, name: str, event: dict[str, Any], *, cancellable: bool = False) -> str | None:
        callback = self._callbacks.get(name)
        if callback is None:
            return None
        try:
            result = callback(clone(event))
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

    def _invoke_data_changed(self, action_event: dict[str, Any]) -> str | None:
        """Emit a single full-snapshot persistence event for data mutations."""

        if self._callbacks.get("on_data_changed") is None:
            return None
        event = create_event(
            "data_changed",
            source=action_event.get("source", "api"),
            action_type=action_event["type"],
            action_event=clone(action_event),
            columns=self.get_columns(),
            cards=self.get_all_cards(),
        )
        return self._invoke_callback("on_data_changed", event, cancellable=True)

    # ------------------------------------------------------------------
    # Card data API
    # ------------------------------------------------------------------
    def add_card(self, card_data: Mapping[str, Any], *, source: str = "api") -> dict[str, Any] | None:
        """Validate, add, and emit ``on_card_created`` for a new card."""

        card = validate_card(card_data, self._column_ids())
        validate_card_values(card, self.fields)
        if card["id"] in self._cards:
            raise KanbanDuplicateIDError(f"Duplicate card ID: {card['id']!r}")
        self._check_column_accepts(card["column"])
        if card.get("sort_order") is None:
            card["sort_order"] = self._next_sort_order(card["column"])

        self._cards[card["id"]] = card
        event = create_event(
            "card_created",
            source=source,
            card_id=card["id"],
            card_data=clone(card),
            column_data=self.get_column(card["column"]),
        )
        reason = self._invoke_callback("on_card_created", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event)
        if reason:
            del self._cards[card["id"]]
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

        if not isinstance(new_data, Mapping):
            raise KanbanValidationError("Card update data must be a mapping")
        old = clone(self._require_card(card_id))
        candidate = {**old, **new_data}
        updated = validate_card(candidate, self._column_ids())
        validate_card_values(updated, self.fields)
        new_id = updated["id"]
        if new_id != card_id and new_id in self._cards:
            raise KanbanDuplicateIDError(f"Duplicate card ID: {new_id!r}")
        if updated["column"] != old["column"]:
            self._check_column_accepts(updated["column"])
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
            self._reindex_column(old["column"])
            self._reindex_column(updated["column"])

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
            reason = self._invoke_data_changed(event)
        if reason:
            if updated["column"] == old["column"]:
                self._cards.pop(new_id, None)
                self._cards.pop(card_id, None)
            else:
                for current_id, current in list(self._cards.items()):
                    if current_id in {card_id, new_id} or current["column"] in affected_columns:
                        del self._cards[current_id]
            self._cards.update(snapshot)
            self._action_cancelled(event, reason)
            return None
        if self._selected_card_id == card_id:
            self._selected_card_id = new_id
        if updated == old and new_id == card_id:
            return clone(updated)
        if self.incremental_card_rendering:
            self._render_card_update(card_id, old["column"], new_id, updated["column"])
        else:
            self.refresh()
        return clone(updated)

    def delete_card(self, card_id: Any, *, source: str = "api") -> bool:
        """Delete a card, unless ``on_card_deleted`` rejects the operation."""

        old = clone(self._require_card(card_id))
        column_id = old["column"]
        snapshot = {
            current_id: clone(current)
            for current_id, current in self._cards.items()
            if current["column"] == column_id
        }
        del self._cards[card_id]
        self._reindex_column(column_id)
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
            reason = self._invoke_data_changed(event)
        if reason:
            for current_id, current in list(self._cards.items()):
                if current["column"] == column_id:
                    del self._cards[current_id]
            self._cards.update(snapshot)
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

        try:
            target_exists = target_column in self._column_ids()
        except TypeError as exc:
            raise KanbanValidationError("Target column ID must be hashable") from exc
        if not target_exists:
            raise KanbanUnknownColumnError(f"Unknown target column: {target_column!r}")
        card = self._require_card(card_id)
        old_card = clone(card)
        old_column = card["column"]
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

        affected_cards = source_cards + ([card] if target_column == old_column else target_cards + [card])
        snapshot = {item["id"]: clone(item) for item in affected_cards}
        card["column"] = target_column
        target_cards.insert(insertion_index, card)
        self._apply_manual_order(old_column, source_cards if target_column != old_column else target_cards)
        if target_column != old_column:
            self._apply_manual_order(target_column, target_cards)

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
            reason = self._invoke_data_changed(event)
        if reason:
            for snapshot_id, snapshot_card in snapshot.items():
                self._cards[snapshot_id] = snapshot_card
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

        column = validate_column(column_data)
        if column["id"] in self._column_ids():
            raise KanbanDuplicateIDError(f"Duplicate column ID: {column['id']!r}")
        self._columns_data.append(column)
        event = create_event(
            "column_created",
            source=source,
            column_id=column["id"],
            column_data=clone(column),
            index=len(self._columns_data) - 1,
        )
        reason = self._invoke_callback("on_column_created", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event)
        if reason:
            self._columns_data.pop()
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

        if not isinstance(new_data, Mapping):
            raise KanbanValidationError("Column update data must be a mapping")
        index = self._column_index(column_id)
        old = clone(self._columns_data[index])
        updated = validate_column({**old, **new_data})
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
            reason = self._invoke_data_changed(event)
        if reason:
            self._columns_data[index] = old
            for affected_card_id in affected_card_ids:
                self._cards[affected_card_id]["column"] = column_id
            if new_id != column_id and new_id in self._column_sorts:
                self._column_sorts[column_id] = self._column_sorts.pop(new_id)
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

        index = self._column_index(column_id)
        if any(card["column"] == column_id for card in self._cards.values()):
            raise KanbanValidationError("Cannot delete a column while it still contains cards")
        column = self._columns_data.pop(index)
        event = create_event(
            "column_deleted",
            source=source,
            column_id=column_id,
            column_data=clone(column),
            old_index=index,
        )
        reason = self._invoke_callback("on_column_deleted", event, cancellable=True)
        if reason is None:
            reason = self._invoke_data_changed(event)
        if reason:
            self._columns_data.insert(index, column)
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
            reason = self._invoke_data_changed(event)
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

        return {
            **dict(self.theme),
            "priority_colors": clone(self.priority_colors),
            "tag_colors": clone(self.tag_colors),
            "font_config": dict(self.font_config),
        }

    def get_data(self) -> BoardData:
        """Return mutable board data without view-specific UI state."""

        return {
            "columns": self.get_columns(),
            "cards": self.get_all_cards(),
        }

    # ------------------------------------------------------------------
    # Bulk data and state API
    # ------------------------------------------------------------------
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
            self._replace_cards_incrementally(normalized)
        else:
            self._cards = {card["id"]: card for card in normalized}
            if self._selected_card_id not in self._cards:
                self._selected_card_id = None
            self.refresh()

    def set_columns(self, columns: Iterable[Mapping[str, Any]]) -> None:
        """Replace columns after ensuring existing cards remain valid."""

        normalized = validate_columns(columns)
        ids = {column["id"] for column in normalized}
        unknown = {card["column"] for card in self._cards.values()} - ids
        if unknown:
            raise KanbanUnknownColumnError(f"Existing cards reference removed columns: {sorted(map(str, unknown))}")
        old_by_id = {column["id"]: column for column in self._columns_data}
        old_ids = set(old_by_id)
        self._columns_data = normalized
        self._column_sorts = {key: value for key, value in self._column_sorts.items() if key in ids}
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
            self._replace_cards_incrementally(cards)
        else:
            self._cards = {card["id"]: card for card in cards}
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
        event = create_event("search_changed", source="toolbar", query=self._search_query, old_query=old_query)
        reason = self._invoke_callback("on_search_changed", event, cancellable=True)
        if reason:
            self._search_query = old_query
            self._action_cancelled(event, reason)
            if hasattr(self, "toolbar"):
                self.toolbar.set_search_query(old_query)
            return False
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
            self.toolbar.set_filter_active(bool(self._filters))
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
    def _open_card_form(
        self,
        *,
        title: str,
        initial_data: dict[str, Any],
        on_submit: Callable[[dict[str, Any]], bool | str | None],
    ) -> None:
        """Open a generated card form using the configured presentation mode."""

        self._close_card_form()
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

        if column_id is None:
            column_id = next((column["id"] for column in self._columns_data if not column.get("locked")), None)
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
            data.setdefault("id", generate_card_id(self._cards))
            return self.add_card(data, source="form") is not None

        self._open_card_form(
            title=f"Add card to {self.get_column(column_id)['title']}",
            initial_data=defaults,
            on_submit=submit,
        )

    def open_edit_card_form(self, card_id: Any) -> None:
        """Open the generated edit form, or notify an external form callback."""

        card = self._require_card(card_id)
        if not self.enable_builtin_card_form:
            event = create_event("edit_card_requested", source="ui", card_id=card_id, card_data=clone(card))
            self._invoke_callback("on_edit_card_requested", event)
            return

        def submit(data: dict[str, Any]) -> bool:
            return self.update_card(card_id, data, source="form") is not None

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
            ("Created date", "created_date"),
            ("Updated date", "updated_date"),
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
                lambda: self.open_edit_card_form(card_id),
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
            state = "disabled" if column.get("locked") or column["id"] == self._cards[card_id]["column"] else "normal"
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
    # Card pointer handling and drag/drop
    # ------------------------------------------------------------------
    def _on_card_press(self, card_widget: CTkKanbanCard, event: Any) -> None:
        self._cancel_pending_drag_motion(self._drag_state)
        self._drag_state = {
            "kind": "card",
            "id": card_widget.card_id,
            "start_x": event.x_root,
            "start_y": event.y_root,
            "active": False,
            "target_column": None,
            "target_index": None,
            "pending_position": None,
            "motion_after_id": None,
            "last_update_at": 0.0,
            "last_autoscroll_at": 0.0,
        }

    def _on_card_motion(self, card_widget: CTkKanbanCard, event: Any) -> None:
        state = self._drag_state
        if not state or state.get("kind") != "card" or state.get("id") != card_widget.card_id:
            return
        distance = abs(event.x_root - state["start_x"]) + abs(event.y_root - state["start_y"])
        if not state["active"] and distance < 8:
            return
        if not self.enable_card_drag:
            return
        if not state["active"]:
            state["active"] = True
            card_widget.set_dragging(True)
            self.update_idletasks()
            self._prepare_card_drag_geometry(state)
            self._create_drag_preview(str(self._cards[card_widget.card_id]["title"]), event.x_root, event.y_root)
        self._queue_card_drag_update(card_widget.card_id, event.x_root, event.y_root)

    def _queue_card_drag_update(self, card_id: Any, root_x: int, root_y: int) -> None:
        """Coalesce raw mouse motion into at most one visual update per frame."""

        state = self._drag_state
        if not state or state.get("kind") != "card" or state.get("id") != card_id or not state.get("active"):
            return
        state["pending_position"] = (root_x, root_y)
        interval = self.drag_update_interval_ms / 1000
        elapsed = monotonic() - state["last_update_at"]
        if interval == 0 or elapsed >= interval:
            self._cancel_pending_drag_motion(state)
            self._process_card_drag_update(card_id, root_x, root_y)
            return
        if state.get("motion_after_id") is None:
            delay_ms = max(1, int((interval - elapsed) * 1000))
            state["motion_after_id"] = self.after(delay_ms, self._flush_card_drag_update, card_id)

    def _flush_card_drag_update(self, card_id: Any) -> None:
        state = self._drag_state
        if not state or state.get("kind") != "card" or state.get("id") != card_id:
            return
        state["motion_after_id"] = None
        position = state.get("pending_position")
        if position is not None:
            self._process_card_drag_update(card_id, position[0], position[1])

    def _process_card_drag_update(self, card_id: Any, root_x: int, root_y: int) -> None:
        state = self._drag_state
        if not state or state.get("kind") != "card" or state.get("id") != card_id or not state.get("active"):
            return
        state["last_update_at"] = monotonic()
        state["pending_position"] = (root_x, root_y)
        self._move_drag_preview(root_x, root_y)
        target = self._column_at(root_x, root_y)
        if target is None:
            state["target_column"] = None
            state["target_index"] = None
            self._set_drop_indicator(None, None)
            return
        source_column = self._cards[card_id]["column"]
        if target.column_id == source_column and not self.enable_card_reorder:
            target_index = self._card_index(card_id)
        else:
            target_index = target.card_index_at(root_y, excluding_id=card_id)
        state["target_column"] = target.column_id
        state["target_index"] = target_index
        if self.show_drop_indicator:
            self._set_drop_indicator(target, target_index)

        interval = self.autoscroll_interval_ms / 1000
        now = monotonic()
        if interval == 0 or now - state["last_autoscroll_at"] >= interval:
            vertical_scrolled = self.enable_vertical_autoscroll and target.autoscroll(root_y)
            horizontal_scrolled = self._horizontal_autoscroll(root_x)
            if vertical_scrolled or horizontal_scrolled:
                state["last_autoscroll_at"] = now
                self.update_idletasks()
                if vertical_scrolled:
                    target.prepare_drag_geometry(excluding_id=card_id)
                if horizontal_scrolled:
                    self._prepare_column_drag_geometry(state)

    def _on_card_release(self, card_widget: CTkKanbanCard, event: Any) -> None:
        state = self._drag_state
        if not state or state.get("kind") != "card" or state.get("id") != card_widget.card_id:
            return
        self._cancel_pending_drag_motion(state)
        if state.get("active"):
            self._process_card_drag_update(card_widget.card_id, event.x_root, event.y_root)
        active = bool(state.get("active"))
        target_column = state.get("target_column")
        target_index = state.get("target_index")
        card_widget.set_dragging(False)
        self._clear_drag_visuals()
        self._drag_state = None
        if active:
            if target_column is not None:
                try:
                    self.move_card(card_widget.card_id, target_column, target_index, source="drag")
                except KanbanValidationError as exc:
                    self._emit_error(exc, create_event("card_move_failed", source="drag", card_id=card_widget.card_id))
            return
        self._handle_card_click(card_widget.card_id, event)

    def _on_card_double_click(self, card_widget: CTkKanbanCard, event: Any) -> None:
        if not self.enable_card_double_click:
            return
        event_data = create_event(
            "card_double_clicked",
            source="mouse",
            card_id=card_widget.card_id,
            card_data=self.get_card(card_widget.card_id),
            x_root=event.x_root,
            y_root=event.y_root,
        )
        if self._callbacks.get("on_card_double_clicked") is not None:
            self._invoke_callback("on_card_double_clicked", event_data)
        else:
            self.open_edit_card_form(card_widget.card_id)

    def _on_card_right_click(self, card_widget: CTkKanbanCard, event: Any) -> None:
        if self.enable_card_selection:
            self.select_card(card_widget.card_id)
        event_data = create_event(
            "card_right_clicked",
            source="mouse",
            card_id=card_widget.card_id,
            card_data=self.get_card(card_widget.card_id),
            x_root=event.x_root,
            y_root=event.y_root,
        )
        self._invoke_callback("on_card_right_clicked", event_data)
        if self.enable_card_context_menu:
            self._show_card_context_menu(card_widget.card_id, event)

    def _handle_card_click(self, card_id: Any, event: Any) -> None:
        if self.enable_card_selection:
            self.select_card(card_id)
        self._invoke_callback(
            "on_card_clicked",
            create_event(
                "card_clicked",
                source="mouse",
                card_id=card_id,
                card_data=self.get_card(card_id),
                x_root=event.x_root,
                y_root=event.y_root,
            ),
        )

    def _open_card(self, card_id: Any) -> None:
        callback = self._callbacks.get("on_card_double_clicked")
        if callback:
            self._invoke_callback(
                "on_card_double_clicked",
                create_event(
                    "card_double_clicked",
                    source="context_menu",
                    card_id=card_id,
                    card_data=self.get_card(card_id),
                ),
            )
        else:
            self.open_edit_card_form(card_id)

    # ------------------------------------------------------------------
    # Column drag handling
    # ------------------------------------------------------------------
    def _on_column_press(self, column_widget: CTkKanbanColumn, event: Any) -> None:
        if not self.enable_column_drag:
            return
        self._drag_state = {
            "kind": "column",
            "id": column_widget.column_id,
            "start_x": event.x_root,
            "start_y": event.y_root,
            "active": False,
            "target_index": self._column_index(column_widget.column_id),
        }

    def _on_column_motion(self, column_widget: CTkKanbanColumn, event: Any) -> None:
        state = self._drag_state
        if not state or state.get("kind") != "column" or state.get("id") != column_widget.column_id:
            return
        distance = abs(event.x_root - state["start_x"]) + abs(event.y_root - state["start_y"])
        if not state["active"] and distance < 8:
            return
        if not state["active"]:
            state["active"] = True
            self._create_drag_preview(str(column_widget.column_data["title"]), event.x_root, event.y_root)
        self._move_drag_preview(event.x_root, event.y_root)
        index = len(self._columns_data) - 1
        for candidate_index, column in enumerate(self._columns_data):
            widget = self._column_widgets[column["id"]]
            if event.x_root < widget.winfo_rootx() + widget.winfo_width() // 2:
                index = candidate_index
                break
        state["target_index"] = index
        self._highlight_column(self._column_widgets[self._columns_data[index]["id"]])
        self._horizontal_autoscroll(event.x_root)

    def _on_column_release(self, column_widget: CTkKanbanColumn, _event: Any) -> None:
        state = self._drag_state
        if not state or state.get("kind") != "column" or state.get("id") != column_widget.column_id:
            return
        active = bool(state.get("active"))
        target_index = int(state.get("target_index", self._column_index(column_widget.column_id)))
        self._clear_drag_visuals()
        self._drag_state = None
        if active:
            self.move_column(column_widget.column_id, target_index, source="drag")

    # ------------------------------------------------------------------
    # Drag helpers
    # ------------------------------------------------------------------
    def _prepare_card_drag_geometry(self, state: dict[str, Any]) -> None:
        """Cache geometry once when card dragging begins."""

        card_id = state["id"]
        for column in self._column_widgets.values():
            column.prepare_drag_geometry(excluding_id=card_id)
        self._prepare_column_drag_geometry(state)

    def _prepare_column_drag_geometry(self, state: dict[str, Any]) -> None:
        """Cache column and board bounds used by pointer hit testing."""

        state["column_rects"] = [
            (
                column.winfo_rootx(),
                column.winfo_rootx() + column.winfo_width(),
                column.winfo_rooty(),
                column.winfo_rooty() + column.winfo_height(),
                column,
            )
            for column in self._column_widgets.values()
        ]
        if self.enable_horizontal_scroll and hasattr(self.board_area, "_parent_canvas"):
            canvas = self.board_area._parent_canvas
            left = canvas.winfo_rootx()
            state["board_horizontal_bounds"] = (left, left + canvas.winfo_width())

    def _cancel_pending_drag_motion(self, state: dict[str, Any] | None) -> None:
        if not state:
            return
        after_id = state.get("motion_after_id")
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except (tk.TclError, ValueError):
                pass
            state["motion_after_id"] = None

    def _set_drop_indicator(
        self,
        column: CTkKanbanColumn | None,
        index: int | None,
    ) -> None:
        """Move the indicator only when its column or index changes."""

        if self._indicator_column is not None and self._indicator_column is not column:
            self._indicator_column.clear_drop_indicator()
        self._indicator_column = column
        if column is not None and index is not None:
            column.show_drop_indicator(index)

    def _create_drag_preview(self, text: str, root_x: int, root_y: int) -> None:
        if not self.enable_drag_preview:
            return
        preview = tk.Toplevel(self.winfo_toplevel())
        preview.overrideredirect(True)
        try:
            if self.drag_preview_opacity < 1.0:
                preview.attributes("-alpha", self.drag_preview_opacity)
            preview.attributes("-topmost", True)
        except tk.TclError:
            pass
        color = self._appearance_color(self.theme["drag_preview_fg_color"])
        label = tk.Label(
            preview,
            text=text,
            bg=color,
            fg=self._appearance_color(self.theme["drag_preview_text_color"]),
            padx=14,
            pady=9,
            relief="solid",
            borderwidth=1,
        )
        label.pack()
        self._drag_preview = preview
        self._drag_preview_position = None
        self._move_drag_preview(root_x, root_y)

    def _move_drag_preview(self, root_x: int, root_y: int) -> None:
        position = (root_x + 14, root_y + 14)
        if self._drag_preview is None or self._drag_preview_position == position:
            return
        try:
            self._drag_preview.geometry(f"+{position[0]}+{position[1]}")
            self._drag_preview_position = position
        except tk.TclError:
            self._drag_preview = None
            self._drag_preview_position = None

    def _clear_drag_visuals(self) -> None:
        self._cancel_pending_drag_motion(self._drag_state)
        if self._drag_preview is not None:
            try:
                self._drag_preview.destroy()
            except tk.TclError:
                pass
            self._drag_preview = None
            self._drag_preview_position = None
        self._clear_column_drop_indicators()
        self._highlight_column(None)
        for column in self._column_widgets.values():
            column.clear_drag_geometry()

    def _clear_column_drop_indicators(self) -> None:
        if self._indicator_column is not None:
            self._indicator_column.clear_drop_indicator()
            self._indicator_column = None

    def _highlight_column(self, column: CTkKanbanColumn | None) -> None:
        if self._highlighted_column is not None and self._highlighted_column.winfo_exists():
            self._highlighted_column.configure(border_color=self.theme["column_border_color"])
        self._highlighted_column = column
        if column is not None:
            column.configure(border_color=self.theme["drop_indicator_color"])

    def _horizontal_autoscroll(self, root_x: int, margin: int = 48) -> bool:
        if not self.enable_horizontal_autoscroll or not self.enable_horizontal_scroll:
            return False
        if not hasattr(self.board_area, "_parent_canvas"):
            return False
        canvas = self.board_area._parent_canvas
        state = self._drag_state or {}
        bounds = state.get("board_horizontal_bounds")
        if bounds is None:
            left = canvas.winfo_rootx()
            right = left + canvas.winfo_width()
        else:
            left, right = bounds
        if root_x < left + margin:
            canvas.xview_scroll(-1, "units")
            return True
        elif root_x > right - margin:
            canvas.xview_scroll(1, "units")
            return True
        return False

    def _column_at(self, root_x: int, root_y: int) -> CTkKanbanColumn | None:
        state = self._drag_state or {}
        cached_rects = state.get("column_rects")
        if cached_rects is not None:
            for left, right, top, bottom, column in cached_rects:
                if left <= root_x <= right and top <= root_y <= bottom:
                    return column
            return None
        for column in self._column_widgets.values():
            if column.contains_point(root_x, root_y):
                return column
        return None

    def _appearance_color(self, color: Any) -> str:
        if isinstance(color, (tuple, list)):
            mode = ctk.get_appearance_mode().lower()
            return str(color[1] if mode == "dark" else color[0])
        return str(color)

    # ------------------------------------------------------------------
    # Internal data helpers
    # ------------------------------------------------------------------
    def _allowed_sort_keys(self) -> set[str]:
        allowed = {
            "manual",
            "priority",
            "due_date",
            "created_date",
            "updated_date",
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
        if not isinstance(reverse, bool):
            raise KanbanValidationError(f"{label} 'reverse' must be a boolean")
        return sort_key, reverse

    def _column_ids(self) -> set[Any]:
        return {column["id"] for column in self._columns_data}

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
        indexed = [(index, card) for index, card in enumerate(self._cards.values()) if card["column"] == column_id]
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
        return highest + 1

    def _ordered_cards_for_column(self, column_id: Any) -> list[dict[str, Any]]:
        cards = self._manual_cards_for_column(column_id)
        sort_key, reverse = self._column_sorts.get(column_id, self._global_sort)
        if sort_key == "manual":
            return list(reversed(cards)) if reverse else cards
        if sort_key == "priority":
            ranking = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            key: Callable[[dict[str, Any]], Any] = lambda card: (
                ranking.get(str(card.get("priority", "")).casefold(), 99),
                searchable_text(card.get("priority")),
            )
        else:
            key = lambda card: comparable_value(card.get(sort_key))
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

    def _changed_order_cards(self, snapshot: dict[Any, dict[str, Any]], columns: set[Any]) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for card_id, old in snapshot.items():
            card = self._cards.get(card_id)
            if card is not None and (card["column"] in columns or old.get("column") in columns) and (
                old.get("column") != card.get("column") or old.get("sort_order") != card.get("sort_order")
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
            count = sum(1 for card in self._cards.values() if card["column"] == column_id)
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

    def _card_matches_view(self, card: dict[str, Any]) -> bool:
        if self._search_query:
            query = self._search_query.casefold()
            if not any(query in searchable_text(card.get(key)) for key in self._searchable_field_keys):
                return False
        for key, expected in self._filters.items():
            if key == "overdue_only":
                if expected and not self._is_overdue(card):
                    return False
                continue
            if key in {"column", "status"}:
                actual = card.get("column")
            else:
                actual = card.get(key)
            if callable(expected):
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
            elif isinstance(actual, (list, tuple, set)):
                if isinstance(expected, (list, tuple, set)):
                    if not any(item in actual for item in expected):
                        return False
                elif expected not in actual:
                    return False
            elif isinstance(expected, (list, tuple, set)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _is_overdue(card: dict[str, Any]) -> bool:
        raw_due = card.get("due_date")
        if isinstance(raw_due, date) and not isinstance(raw_due, datetime):
            return raw_due < date.today() and not bool(card.get("completed"))
        if isinstance(raw_due, str) and len(raw_due.strip()) == 10:
            try:
                due_date = date.fromisoformat(raw_due.strip())
            except ValueError:
                pass
            else:
                return due_date < date.today() and not bool(card.get("completed"))
        due = parse_temporal(raw_due)
        if due is None:
            return False
        now = datetime.now(timezone.utc)
        return due < now and not bool(card.get("completed"))
