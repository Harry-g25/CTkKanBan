"""Widget construction and incremental rendering for the Kanban board."""

from __future__ import annotations

import queue
import tkinter as tk
from time import monotonic
from typing import Any, Iterable, Mapping

import customtkinter as ctk

from .card import CTkKanbanCard
from .column import CTkKanbanColumn
from .exceptions import KanbanValidationError
from .toolbar import CTkKanbanToolbar
from .utils import clone


def _validated_width(value: Any, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise KanbanValidationError(f"width must be an integer of at least {minimum}")
    return value


class RenderingMixin:
    """Build, refresh, and incrementally synchronize board widgets."""

    # Construction and rendering
    # ------------------------------------------------------------------
    def destroy(self) -> None:
        """Cancel deferred cleanup before destroying the board widget."""

        self._cancel_retired_cleanup()
        if self._ui_after_id is not None:
            try:
                self.after_cancel(self._ui_after_id)
            except (ValueError, tk.TclError):
                pass
            self._ui_after_id = None
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except (ValueError, tk.TclError):
                pass
            self._poll_after_id = None
        if self._persistence is not None:
            self._persistence.close()
        self._close_card_form()
        super().destroy()

    def _drain_ui_queue(self) -> None:
        """Run worker completions exclusively on Tk's owning thread."""

        self._ui_after_id = None
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                self.logger.exception("Queued Kanban UI callback failed", exc_info=exc)
        try:
            if self.winfo_exists():
                self._ui_after_id = self.after(10, self._drain_ui_queue)
        except tk.TclError:
            self._ui_after_id = None

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
                on_clear_search=self.clear_search,
                on_retry=self.retry_last_save,
            )
            self.toolbar.grid(row=0, column=0, sticky="ew", padx=self.board_padding, pady=(self.board_padding, 0))
            self.toolbar.set_sort(self._global_sort[0], self._global_sort[1])

        row = 1 if self.show_toolbar else 0
        if self.enable_horizontal_scroll:
            self.board_area: Any = ctk.CTkScrollableFrame(
                self,
                orientation="horizontal",
                fg_color="transparent",
                scrollbar_button_color=self.theme["scrollbar_button_color"],
                scrollbar_button_hover_color=self.theme["scrollbar_button_hover_color"],
            )
            if hasattr(self.board_area, "_scrollbar"):
                self.board_area._scrollbar.configure(height=7)
        else:
            self.board_area = ctk.CTkFrame(self, fg_color="transparent")
        self.board_area.grid(
            row=row,
            column=0,
            sticky="nsew",
            padx=self.board_padding,
            pady=self.board_padding,
        )
        if self.responsive_columns:
            self.board_area.bind("<Configure>", self._apply_responsive_columns, add="+")
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
            self._show_empty_board()
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
                total = card_counts[column_data["id"]]
                column.show_no_results(
                    "No cards yet" if total == 0 else "No cards match this view",
                    allow_add=total == 0,
                )
        self._layout_column_widgets()
        self._update_toolbar_summary()

    def _show_empty_board(self) -> None:
        """Render a polished empty board state and retain one destroy handle."""

        empty_panel = ctk.CTkFrame(
            self.board_area,
            fg_color=self.theme["toolbar_fg_color"],
            border_color=self.theme["toolbar_border_color"],
            border_width=self.theme.get("toolbar_border_width", 1),
            corner_radius=self.theme.get("toolbar_corner_radius", 14),
        )
        empty_panel.grid(row=0, column=0, padx=30, pady=30)
        ctk.CTkLabel(
            empty_panel,
            text="▥",
            width=42,
            height=42,
            corner_radius=12,
            fg_color=self.theme["secondary_button_fg_color"],
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(size=19),
        ).pack(padx=56, pady=(28, 8))
        ctk.CTkLabel(
            empty_panel,
            text="No columns yet",
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(padx=56, pady=(0, 4))
        ctk.CTkLabel(
            empty_panel,
            text="Create your first workflow column to get started.",
            text_color=self.theme["overlay_text_color"],
        ).pack(padx=32, pady=(0, 30))
        self._empty_label = empty_panel

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
            control_size=self.column_control_size,
            show_drag_handle=self.show_drag_handles,
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
            self._show_empty_board()

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
            card_width=max(160, self.column_width - 26),
            show_drag_handle=self.show_drag_handles,
            density=self.card_density,
            max_visible_tags=self.max_visible_tags,
            tags_per_row=self.tags_per_row,
            timezone_info=self.timezone,
            locale_name=self.locale_name,
        )
        column.add_card_widget(card)
        self._card_widgets[card_data["id"]] = card
        if card_data["id"] == self._selected_card_id:
            card.set_selected(True)
        if self.highlight_search_matches and self._search_query:
            card.set_search_match(True)
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
        total = self._column_totals.get(
            column_id,
            sum(1 for card in self._cards.values() if card["column"] == column_id),
        )
        column.update_card_count(total)
        if column.card_widgets:
            column.clear_no_results()
        elif self.show_no_results:
            column.show_no_results(
                "No cards yet" if total == 0 else "No cards match this view",
                allow_add=total == 0,
            )

    def _apply_responsive_columns(self, event: Any = None) -> None:
        """Fit columns to available width within configurable bounds."""

        if not self.responsive_columns or not self._column_widgets:
            return
        available = int(getattr(event, "width", self.board_area.winfo_width()))
        gaps = self.column_gap * max(0, len(self._column_widgets) - 1)
        target = (available - gaps) // max(1, len(self._column_widgets))
        preferred_minimum = max(
            self.min_column_width,
            int(self.theme.get("responsive_preferred_min_column_width", self.min_column_width)),
        )
        target = max(preferred_minimum, min(self.max_column_width, target))
        for column in self._column_widgets.values():
            column.set_width(target)
            for card in column.card_widgets:
                card.reflow(max(160, target - 26))

    def set_column_width(self, width: int, column_id: Any | None = None) -> None:
        """Allow applications or user preference controls to resize columns."""

        validated = _validated_width(width, self.min_column_width)
        validated = min(validated, self.max_column_width)
        if column_id is None:
            self.column_width = validated
            for column in self._column_widgets.values():
                column.set_width(validated)
                for card in column.card_widgets:
                    card.reflow(max(160, validated - 26))
            return
        self._column_index(column_id)
        self._column_widgets[column_id].set_width(validated)
        for card in self._column_widgets[column_id].card_widgets:
            card.reflow(max(160, validated - 26))

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
                widget.set_search_match(bool(self.highlight_search_matches and self._search_query and match_by_id[card_id]))
                ordered_widgets.append(widget)
            column.set_card_widget_order(ordered_widgets)
            self._update_column_summary(column_id)
        self._update_toolbar_summary()

    def _update_toolbar_summary(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        visible = len(self._card_widgets)
        total = sum(self._column_totals.values()) if self._column_totals else len(self._cards)
        self.toolbar.set_result_count(visible, total)
        self.toolbar.set_filter_active(bool(self._filters), len(self._filters))
        self.toolbar.set_filter_chips(self._filters)
        self.toolbar.set_sort(self._global_sort[0], self._global_sort[1])

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
