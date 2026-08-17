"""A small, predictable CustomTkinter Kanban board."""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from functools import partial
from math import hypot
from tkinter import messagebox
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

import customtkinter as ctk

from ._scrolling import ManagedScrollableFrame
from .card import CTkKanbanCard
from .column import CTkKanbanColumn
from .editor import CardEditor
from .model import BoardModel, BoardModelError
from .themes import merge_theme

ChangeCallback = Callable[[dict[str, Any]], Any]
CardOpenCallback = Callable[[dict[str, Any]], Any]


@dataclass(slots=True)
class _DragState:
    card_id: Any
    start_x: int
    start_y: int
    grab_widget: tk.Misc | None = None
    active: bool = False
    target_column: Any | None = None
    target_index: int | None = None


class CTkKanbanBoard(ctk.CTkFrame):
    """A focused Kanban widget with explicit editing and handle-only dragging.

    The widget owns an in-memory :class:`BoardModel`.  Persistence belongs to
    the host application and is notified through one ``on_change`` callback.
    """

    def __init__(
        self,
        master: Any,
        columns: Iterable[Mapping[str, Any]] = (),
        cards: Iterable[Mapping[str, Any]] = (),
        *,
        on_change: ChangeCallback | None = None,
        on_card_open: CardOpenCallback | None = None,
        theme: Mapping[str, Any] | None = None,
        show_toolbar: bool = True,
        enable_drag: bool = True,
        column_width: int = 288,
        column_height: int = 500,
        confirm_delete: bool = True,
        **kwargs: Any,
    ) -> None:
        if not isinstance(column_width, int) or isinstance(column_width, bool) or column_width < 220:
            raise ValueError("column_width must be an integer of at least 220")
        if not isinstance(column_height, int) or isinstance(column_height, bool) or column_height < 240:
            raise ValueError("column_height must be an integer of at least 240")

        self.model = BoardModel(columns=columns, cards=cards)
        self.theme = merge_theme(theme)
        kwargs.setdefault("fg_color", self.theme["board_fg_color"])
        super().__init__(master, **kwargs)

        self.on_change = on_change
        self.on_card_open = on_card_open
        self.show_toolbar = bool(show_toolbar)
        self.enable_drag = bool(enable_drag)
        self.column_width = column_width
        self.column_height = column_height
        self.confirm_delete = bool(confirm_delete)

        self._logger = logging.getLogger("ctk_kanban")
        self._search_query = ""
        self._selected_card_id: Any | None = None
        self._drag_state: _DragState | None = None
        self._column_widgets: dict[Any, CTkKanbanColumn] = {}
        self._card_widgets: dict[Any, CTkKanbanCard] = {}
        self._empty_widget: ctk.CTkFrame | None = None
        self._active_menu: tk.Menu | None = None
        self._editor: CardEditor | None = None

        self.grid_rowconfigure(1 if self.show_toolbar else 0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        if self.show_toolbar:
            self._build_toolbar()
        self._build_board_area()
        self.refresh(preserve_scroll=False)

    # ------------------------------------------------------------------
    # Construction and rendering
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        self.toolbar = ctk.CTkFrame(
            self,
            height=48,
            fg_color=self.theme["toolbar_fg_color"],
        )
        self.toolbar.grid(row=0, column=0, padx=12, pady=(12, 0), sticky="ew")
        self.toolbar.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            self.toolbar,
            placeholder_text="Search cards",
            width=260,
        )
        self.search_entry.grid(row=0, column=0, padx=10, pady=9, sticky="w")
        self.search_entry.bind("<KeyRelease>", self._on_search_changed, add="+")

        self.summary_label = ctk.CTkLabel(
            self.toolbar,
            text="",
            text_color=self.theme["muted_text_color"],
        )
        self.summary_label.grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            self.toolbar,
            text="Add column",
            width=94,
            command=self.open_add_column_dialog,
        ).grid(row=0, column=2, padx=4, pady=8)
        ctk.CTkButton(
            self.toolbar,
            text="Add card",
            width=84,
            command=self.open_add_card_editor,
        ).grid(row=0, column=3, padx=(4, 10), pady=8)

    def _build_board_area(self) -> None:
        row = 1 if self.show_toolbar else 0
        self.board_area: Any = ManagedScrollableFrame(
            self,
            orientation="horizontal",
            fg_color="transparent",
            scrollbar_button_color=self.theme["scrollbar_color"],
            scrollbar_button_hover_color=self.theme["scrollbar_hover_color"],
        )
        self.board_area.grid(row=row, column=0, padx=12, pady=12, sticky="nsew")
        if hasattr(self.board_area, "_scrollbar"):
            self.board_area._scrollbar.configure(height=8)

    def refresh(self, *, preserve_scroll: bool = True) -> None:
        """Rebuild structural board state while preserving its viewport.

        Card-only mutations use the smaller ``_sync_card_columns`` path.
        """

        scroll_positions = self._capture_scroll_positions() if preserve_scroll else (0.0, {})
        self._destroy_active_menu()
        self._clear_drag_feedback()
        for widget in list(self._column_widgets.values()):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self._column_widgets.clear()
        self._card_widgets.clear()
        if self._empty_widget is not None:
            self._empty_widget.destroy()
            self._empty_widget = None

        columns = self.model.get_columns()
        if not columns:
            self._render_empty_board()
            self._update_summary()
            self._restore_scroll_positions(scroll_positions)
            return

        for index, column_data in enumerate(columns):
            column = CTkKanbanColumn(
                self.board_area,
                column_data,
                self.theme,
                width=self.column_width,
                height=self.column_height,
                on_add=self.open_add_card_editor,
                on_menu=self._show_column_menu,
            )
            column.grid(row=0, column=index, padx=6, pady=2, sticky="n")
            self._column_widgets[column_data["id"]] = column

            cards = [
                card
                for card in self.model.get_cards(column_data["id"])
                if self._card_matches_search(card)
            ]
            card_widgets = [self._create_card_widget(column, card_data) for card_data in cards]
            column.set_cards(
                card_widgets,
                empty_text="No matching cards" if self._search_query else "No cards",
            )
            column.count_label.configure(text=str(len(self.model.get_cards(column_data["id"]))))
        self._update_summary()
        self._restore_scroll_positions(scroll_positions)

    def _create_card_widget(
        self,
        column: CTkKanbanColumn,
        card_data: Mapping[str, Any],
    ) -> CTkKanbanCard:
        card = CTkKanbanCard(
            column.body,
            card_data,
            self.theme,
            width=self.column_width - 22,
            drag_enabled=self.enable_drag and not self._search_query,
            on_select=self._select_card_widget,
            on_edit=lambda widget: self.open_edit_card_editor(widget.card_id),
            on_menu=self._show_card_menu,
            on_drag_press=self._on_drag_press,
            on_drag_motion=self._on_drag_motion,
            on_drag_release=self._on_drag_release,
        )
        self._card_widgets[card.card_id] = card
        card.set_selected(card.card_id == self._selected_card_id)
        return card

    def _capture_scroll_positions(self) -> tuple[float, dict[Any, float]]:
        horizontal = 0.0
        vertical: dict[Any, float] = {}
        try:
            horizontal = float(self.board_area._parent_canvas.xview()[0])
        except (AttributeError, IndexError, tk.TclError):
            pass
        for column_id, column in self._column_widgets.items():
            try:
                vertical[column_id] = float(column.body._parent_canvas.yview()[0])
            except (AttributeError, IndexError, tk.TclError):
                pass
        return horizontal, vertical

    def _restore_scroll_positions(
        self,
        positions: tuple[float, dict[Any, float]],
    ) -> None:
        horizontal, vertical = positions
        self.update_idletasks()
        try:
            self.board_area._parent_canvas.xview_moveto(horizontal)
        except (AttributeError, tk.TclError):
            pass
        for column_id, position in vertical.items():
            column = self._column_widgets.get(column_id)
            if column is None:
                continue
            try:
                column.body._parent_canvas.yview_moveto(position)
            except (AttributeError, tk.TclError):
                pass

    def _sync_card_columns(
        self,
        column_ids: Iterable[Any],
        *,
        replace_card_ids: Iterable[Any] = (),
    ) -> None:
        """Update only affected card lists, keeping column scroll frames alive."""

        scroll_positions = self._capture_scroll_positions()
        self._destroy_active_menu()
        self._clear_drag_feedback()

        for card_id in replace_card_ids:
            widget = self._card_widgets.pop(card_id, None)
            if widget is None:
                continue
            for existing_column in self._column_widgets.values():
                existing_column.card_widgets = [
                    card for card in existing_column.card_widgets if card is not widget
                ]
            widget.destroy()

        for column_id in dict.fromkeys(column_ids):
            column_widget = self._column_widgets.get(column_id)
            if column_widget is None:
                continue
            all_cards = self.model.get_cards(column_id)
            visible_cards = [card for card in all_cards if self._card_matches_search(card)]
            desired_ids = {card["id"] for card in visible_cards}

            for widget in list(column_widget.card_widgets):
                if widget.card_id in desired_ids:
                    continue
                if self._card_widgets.get(widget.card_id) is widget:
                    self._card_widgets.pop(widget.card_id, None)
                widget.destroy()

            ordered_widgets: list[CTkKanbanCard] = []
            for card_data in visible_cards:
                widget = self._card_widgets.get(card_data["id"])
                if widget is not None and widget.master is not column_widget.body:
                    self._card_widgets.pop(card_data["id"], None)
                    widget.destroy()
                    widget = None
                if widget is None:
                    widget = self._create_card_widget(column_widget, card_data)
                ordered_widgets.append(widget)

            column_widget.set_cards(
                ordered_widgets,
                empty_text="No matching cards" if self._search_query else "No cards",
            )
            column_widget.count_label.configure(text=str(len(all_cards)))

        self._update_summary()
        self._restore_scroll_positions(scroll_positions)

    def _render_empty_board(self) -> None:
        self._empty_widget = ctk.CTkFrame(self.board_area, fg_color="transparent")
        self._empty_widget.grid(row=0, column=0, padx=40, pady=80)
        ctk.CTkLabel(
            self._empty_widget,
            text="No columns yet",
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(0, 10))
        ctk.CTkButton(
            self._empty_widget,
            text="Create first column",
            command=self.open_add_column_dialog,
        ).pack()

    # ------------------------------------------------------------------
    # Public data API
    # ------------------------------------------------------------------
    def get_data(self) -> dict[str, list[dict[str, Any]]]:
        return self.model.snapshot()

    def set_data(self, data: Mapping[str, Any]) -> None:
        self.model.load(data)
        if self._selected_card_id is not None:
            try:
                self.model.get_card(self._selected_card_id)
            except BoardModelError:
                self._selected_card_id = None
        self.refresh(preserve_scroll=False)

    def get_card(self, card_id: Any) -> dict[str, Any] | None:
        try:
            return self.model.get_card(card_id)
        except BoardModelError:
            return None

    def get_cards(self, column_id: Any | None = None) -> list[dict[str, Any]]:
        return self.model.get_cards(column_id)

    def get_columns(self) -> list[dict[str, Any]]:
        return self.model.get_columns()

    def add_card(self, card: Mapping[str, Any], *, index: int | None = None) -> dict[str, Any]:
        before = self.model.snapshot()
        created = self.model.add_card(card, index=index)
        self._sync_card_columns([created["column"]])
        self._emit_change("card_added", before=before, card=created)
        return created

    def update_card(self, card_id: Any, updates: Mapping[str, Any]) -> dict[str, Any]:
        before = self.model.snapshot()
        previous = self.model.get_card(card_id)
        updated = self.model.update_card(card_id, updates)
        if self.model.snapshot() == before:
            return updated
        self._sync_card_columns(
            [previous["column"], updated["column"]],
            replace_card_ids=[card_id],
        )
        self._emit_change("card_updated", before=before, card=updated, previous=previous)
        return updated

    def delete_card(self, card_id: Any) -> dict[str, Any]:
        before = self.model.snapshot()
        deleted = self.model.delete_card(card_id)
        if self._selected_card_id == card_id:
            self._selected_card_id = None
        self._sync_card_columns([deleted["column"]], replace_card_ids=[card_id])
        self._emit_change("card_deleted", before=before, card=deleted)
        return deleted

    def move_card(
        self,
        card_id: Any,
        column_id: Any,
        index: int | None = None,
    ) -> dict[str, Any]:
        before = self.model.snapshot()
        previous = self.model.get_card(card_id)
        moved = self.model.move_card(card_id, column_id, index=index)
        if self.model.snapshot() == before:
            return moved
        replace_ids = [card_id] if previous["column"] != moved["column"] else []
        self._sync_card_columns(
            [previous["column"], moved["column"]],
            replace_card_ids=replace_ids,
        )
        self._emit_change("card_moved", before=before, card=moved, previous=previous)
        return moved

    def add_column(self, column: Mapping[str, Any], *, index: int | None = None) -> dict[str, Any]:
        before = self.model.snapshot()
        created = self.model.add_column(column, index=index)
        self.refresh()
        self._emit_change("column_added", before=before, column=created)
        return created

    def update_column(self, column_id: Any, updates: Mapping[str, Any]) -> dict[str, Any]:
        before = self.model.snapshot()
        previous = next((item for item in self.model.get_columns() if item["id"] == column_id), None)
        updated = self.model.update_column(column_id, updates)
        if self.model.snapshot() == before:
            return updated
        self.refresh()
        self._emit_change("column_updated", before=before, column=updated, previous=previous)
        return updated

    def delete_column(self, column_id: Any, *, delete_cards: bool = False) -> dict[str, Any]:
        before = self.model.snapshot()
        removed_card_ids = {
            card["id"] for card in before["cards"] if card["column"] == column_id
        }
        deleted = self.model.delete_column(column_id, delete_cards=delete_cards)
        if self._selected_card_id in removed_card_ids:
            self._selected_card_id = None
        self.refresh()
        self._emit_change("column_deleted", before=before, column=deleted)
        return deleted

    def move_column(self, column_id: Any, index: int) -> dict[str, Any]:
        before = self.model.snapshot()
        moved = self.model.move_column(column_id, index)
        if self.model.snapshot() == before:
            return moved
        self.refresh()
        self._emit_change("column_moved", before=before, column=moved)
        return moved

    # ------------------------------------------------------------------
    # Explicit editors and menus
    # ------------------------------------------------------------------
    def open_add_card_editor(self, column_id: Any | None = None) -> None:
        columns = self.model.get_columns()
        if not columns:
            self.open_add_column_dialog()
            columns = self.model.get_columns()
            if not columns:
                return
        if column_id is not None and not any(column["id"] == column_id for column in columns):
            raise BoardModelError(f"unknown column ID: {column_id!r}")
        chosen_column = columns[0]["id"] if column_id is None else column_id

        def save(values: dict[str, Any]) -> bool | str:
            try:
                self.add_card({"id": str(uuid4()), **values})
            except (BoardModelError, ValueError) as exc:
                return str(exc)
            return True

        self._open_card_editor(
            title="Add card",
            initial={"column": chosen_column},
            columns=columns,
            on_save=save,
        )

    def open_edit_card_editor(self, card_id: Any) -> None:
        card = self.get_card(card_id)
        if card is None:
            return
        if self.on_card_open is not None:
            try:
                self.on_card_open(dict(card))
            except Exception:
                self._logger.exception("on_card_open callback failed")
            return

        def save(values: dict[str, Any]) -> bool | str:
            try:
                self.update_card(card_id, values)
            except (BoardModelError, ValueError) as exc:
                return str(exc)
            return True

        self._open_card_editor(
            title="Edit card",
            initial=card,
            columns=self.model.get_columns(),
            on_save=save,
        )

    def _open_card_editor(
        self,
        *,
        title: str,
        initial: Mapping[str, Any],
        columns: Iterable[Mapping[str, Any]],
        on_save: Callable[[dict[str, Any]], bool | str],
    ) -> None:
        """Replace any open drawer with the requested card editor."""

        self._destroy_active_menu()
        self._clear_drag_feedback()
        if self._editor is not None:
            editor = self._editor
            self._editor = None
            editor.destroy()
        self._editor = CardEditor(
            self,
            title=title,
            initial=initial,
            columns=list(columns),
            on_save=on_save,
            on_close=self._editor_closed,
        )

    def _editor_closed(self, editor: CardEditor) -> None:
        if self._editor is editor:
            self._editor = None

    def open_add_column_dialog(self) -> None:
        dialog = ctk.CTkInputDialog(text="Column name", title="Add column")
        title = dialog.get_input()
        if title is None or not title.strip():
            return
        self.add_column({"id": str(uuid4()), "title": title.strip()})

    def _rename_column(self, column_id: Any) -> None:
        current = next((item for item in self.model.get_columns() if item["id"] == column_id), None)
        if current is None:
            return
        dialog = ctk.CTkInputDialog(text="Column name", title="Rename column")
        title = dialog.get_input()
        if title is not None and title.strip() and title.strip() != current["title"]:
            self.update_column(column_id, {"title": title.strip()})

    def _show_card_menu(self, card_widget: CTkKanbanCard) -> None:
        card_id = card_widget.card_id
        current = self.get_card(card_id)
        if current is None:
            return
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Edit", command=lambda: self.open_edit_card_editor(card_id))
        column_id = current["column"]
        cards = self.model.get_cards(column_id)
        current_index = next(index for index, item in enumerate(cards) if item["id"] == card_id)
        menu.add_command(
            label="Move up",
            state="normal" if not self._search_query and current_index > 0 else "disabled",
            command=lambda: self.move_card(card_id, column_id, current_index - 1),
        )
        menu.add_command(
            label="Move down",
            state=(
                "normal"
                if not self._search_query and current_index < len(cards) - 1
                else "disabled"
            ),
            command=lambda: self.move_card(card_id, column_id, current_index + 1),
        )
        move_menu = tk.Menu(menu, tearoff=False)
        for column in self.model.get_columns():
            target_id = column["id"]
            move_menu.add_command(
                label=str(column["title"]),
                state="disabled" if target_id == column_id else "normal",
                command=partial(self.move_card, card_id, target_id),
            )
        menu.add_cascade(label="Move to column", menu=move_menu)
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self._request_delete_card(card_id))
        self._popup_menu(menu, card_widget.menu_button)

    def _show_column_menu(self, column_id: Any, button: Any) -> None:
        columns = self.model.get_columns()
        index = next((i for i, item in enumerate(columns) if item["id"] == column_id), -1)
        if index < 0:
            return
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Rename", command=lambda: self._rename_column(column_id))
        menu.add_command(
            label="Move left",
            state="normal" if index > 0 else "disabled",
            command=lambda: self.move_column(column_id, index - 1),
        )
        menu.add_command(
            label="Move right",
            state="normal" if index < len(columns) - 1 else "disabled",
            command=lambda: self.move_column(column_id, index + 1),
        )
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self._request_delete_column(column_id))
        self._popup_menu(menu, button)

    def _popup_menu(self, menu: tk.Menu, button: Any) -> None:
        self._destroy_active_menu()
        self._active_menu = menu
        menu.bind(
            "<Unmap>",
            lambda _event: self._menu_unmapped(menu),
            add="+",
        )
        try:
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _menu_unmapped(self, menu: tk.Menu) -> None:
        if self._active_menu is menu:
            self.after_idle(self._destroy_menu, menu)

    def _destroy_menu(self, menu: tk.Menu) -> None:
        if self._active_menu is menu:
            self._active_menu = None
        try:
            menu.destroy()
        except tk.TclError:
            pass

    def _destroy_active_menu(self) -> None:
        if self._active_menu is not None:
            self._destroy_menu(self._active_menu)

    def _request_delete_card(self, card_id: Any) -> None:
        card = self.get_card(card_id)
        if card is None:
            return
        if self.confirm_delete and not messagebox.askyesno(
            "Delete card",
            f"Delete '{card['title']}'?",
            parent=self.winfo_toplevel(),
        ):
            return
        self.delete_card(card_id)

    def _request_delete_column(self, column_id: Any) -> None:
        column = next((item for item in self.model.get_columns() if item["id"] == column_id), None)
        if column is None:
            return
        card_count = len(self.model.get_cards(column_id))
        message = f"Delete '{column['title']}'?"
        if card_count:
            message += f" This also deletes {card_count} card(s)."
        if self.confirm_delete and not messagebox.askyesno(
            "Delete column",
            message,
            parent=self.winfo_toplevel(),
        ):
            return
        self.delete_column(column_id, delete_cards=True)

    # ------------------------------------------------------------------
    # Selection, search, and drag
    # ------------------------------------------------------------------
    def _select_card_widget(self, card_widget: CTkKanbanCard) -> None:
        previous = self._card_widgets.get(self._selected_card_id)
        if previous is not None and previous is not card_widget:
            previous.set_selected(False)
        self._selected_card_id = card_widget.card_id
        card_widget.set_selected(True)

    def get_selected_card(self) -> dict[str, Any] | None:
        if self._selected_card_id is None:
            return None
        return self.get_card(self._selected_card_id)

    def search(self, query: str) -> None:
        self._apply_search(query, sync_entry=True)

    def _apply_search(self, query: str, *, sync_entry: bool) -> None:
        text = str(query)
        if sync_entry and self.show_toolbar and self.search_entry.get() != text:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, text)
        normalized = text.strip().casefold()
        if normalized != self._search_query:
            self._search_query = normalized
            self.refresh(preserve_scroll=False)

    def _on_search_changed(self, _event: Any = None) -> None:
        self._apply_search(self.search_entry.get(), sync_entry=False)

    def _card_matches_search(self, card: Mapping[str, Any]) -> bool:
        if not self._search_query:
            return True
        values = [
            card.get("title", ""),
            card.get("description", ""),
            card.get("priority", ""),
            *(card.get("tags") or []),
        ]
        return self._search_query in " ".join(str(value) for value in values).casefold()

    def _on_drag_press(self, card_widget: CTkKanbanCard, event: Any) -> None:
        if not self.enable_drag or self._search_query:
            return
        self._select_card_widget(card_widget)
        grab_widget = getattr(event, "widget", None)
        if not isinstance(grab_widget, tk.Misc):
            grab_widget = card_widget.drag_handle
        state = _DragState(
            card_widget.card_id,
            event.x_root,
            event.y_root,
            grab_widget=grab_widget,
        )
        self._drag_state = state
        try:
            grab_widget.grab_set()
        except tk.TclError:
            state.grab_widget = None

    def _on_drag_motion(self, card_widget: CTkKanbanCard, event: Any) -> None:
        state = self._drag_state
        if state is None or state.card_id != card_widget.card_id:
            return
        if not state.active and hypot(event.x_root - state.start_x, event.y_root - state.start_y) < 6:
            return
        if not state.active:
            state.active = True
            card_widget.set_dragging(True)
        target = None
        if self._board_view_contains(event.x_root, event.y_root):
            target = next(
                (
                    column
                    for column in self._column_widgets.values()
                    if column.contains_point(event.x_root, event.y_root)
                ),
                None,
            )
        target_column = target.column_id if target is not None else None
        target_index = (
            target.card_index_at(event.y_root, excluding_id=card_widget.card_id)
            if target is not None
            else None
        )
        if state.target_column == target_column and state.target_index == target_index:
            return

        previous_target = self._column_widgets.get(state.target_column)
        if previous_target is not None and previous_target is not target:
            previous_target.clear_drop_indicator()
            previous_target.set_drop_target(False)

        state.target_column = target_column
        state.target_index = target_index
        if target is None:
            return
        assert target_index is not None
        if previous_target is not target:
            target.set_drop_target(True)
        target.show_drop_indicator(target_index, excluding_id=card_widget.card_id)

    def _board_view_contains(self, root_x: int, root_y: int) -> bool:
        canvas = self.board_area._parent_canvas
        return (
            canvas.winfo_rootx() <= root_x <= canvas.winfo_rootx() + canvas.winfo_width()
            and canvas.winfo_rooty() <= root_y <= canvas.winfo_rooty() + canvas.winfo_height()
        )

    def _on_drag_release(self, card_widget: CTkKanbanCard, event: Any) -> None:
        state = self._drag_state
        if state is None or state.card_id != card_widget.card_id:
            return
        self._on_drag_motion(card_widget, event)
        state = self._drag_state
        if state is None:
            return
        self._release_drag_grab(state)
        self._drag_state = None
        self._clear_drop_targets()
        card_widget.set_dragging(False)
        if not state.active or state.target_column is None or state.target_index is None:
            return
        try:
            self.move_card(card_widget.card_id, state.target_column, state.target_index)
        except BoardModelError:
            self._logger.exception("Card drop failed")

    def _clear_drop_targets(self) -> None:
        for column in self._column_widgets.values():
            column.clear_drop_indicator()
            column.set_drop_target(False)

    def _clear_drag_feedback(self) -> None:
        self._clear_drop_targets()
        if self._drag_state is not None:
            self._release_drag_grab(self._drag_state)
        self._drag_state = None

    @staticmethod
    def _release_drag_grab(state: _DragState) -> None:
        grab_widget = state.grab_widget
        if grab_widget is None:
            return
        try:
            if grab_widget.grab_current() == grab_widget:
                grab_widget.grab_release()
        except tk.TclError:
            pass
        state.grab_widget = None

    # ------------------------------------------------------------------
    # Event boundary
    # ------------------------------------------------------------------
    def _emit_change(self, event_type: str, **payload: Any) -> None:
        if self.on_change is None:
            return
        event = {"type": event_type, **payload, "data": self.model.snapshot()}
        try:
            self.on_change(event)
        except Exception:
            self._logger.exception("on_change callback failed for %s", event_type)

    def _update_summary(self) -> None:
        if not self.show_toolbar:
            return
        visible = len(self._card_widgets)
        total = len(self.model.get_cards())
        self.summary_label.configure(text=f"{visible} of {total}" if self._search_query else f"{total} cards")

    def destroy(self) -> None:
        """Release menus, grabs, and scroll bindings before widget teardown."""

        if self._editor is not None:
            editor = self._editor
            self._editor = None
            editor.destroy()
        self._destroy_active_menu()
        self._clear_drag_feedback()
        for column in list(self._column_widgets.values()):
            column.destroy()
        self._column_widgets.clear()
        self._card_widgets.clear()
        if hasattr(self, "board_area"):
            self.board_area.destroy()
        super().destroy()
