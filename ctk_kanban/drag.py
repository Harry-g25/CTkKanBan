"""Drag-and-drop behavior for the Kanban board."""

from __future__ import annotations

import tkinter as tk
from time import monotonic
from typing import Any

import customtkinter as ctk

from .card import CTkKanbanCard
from .column import CTkKanbanColumn
from .events import create_event
from .exceptions import KanbanValidationError


class DragDropMixin:
    """Pointer, preview, drop-target, and autoscroll behavior."""

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
            "target_valid": False,
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
            state["target_valid"] = False
            for column_widget in self._column_widgets.values():
                column_widget.set_drop_valid(None)
            self._set_drop_indicator(None, None)
            return
        source_column = self._cards[card_id]["column"]
        valid_target = self._column_accepts_drop(target.column_id, card_id)
        state["target_valid"] = valid_target
        for column_widget in self._column_widgets.values():
            column_widget.set_drop_valid(valid_target if column_widget is target else None)
        if not valid_target:
            state["target_column"] = None
            state["target_index"] = None
            self._set_drop_indicator(None, None)
            return
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
        target_valid = bool(state.get("target_valid"))
        card_widget.set_dragging(False)
        self._clear_drag_visuals()
        self._drag_state = None
        if active:
            if target_valid and target_column is not None:
                try:
                    self.move_card(card_widget.card_id, target_column, target_index, source="drag")
                except KanbanValidationError as exc:
                    self._emit_error(exc, create_event("card_move_failed", source="drag", card_id=card_widget.card_id))
            return
        self._handle_card_click(card_widget.card_id, event)

    def _on_card_double_click(self, card_widget: CTkKanbanCard, event: Any) -> None:
        if not self.enable_card_double_click:
            return
        inline_field_key = getattr(event, "inline_field_key", None)
        event_data = create_event(
            "card_double_clicked",
            source="mouse",
            card_id=card_widget.card_id,
            card_data=self.get_card(card_widget.card_id),
            x_root=event.x_root,
            y_root=event.y_root,
            field_key=inline_field_key,
        )
        if self._callbacks.get("on_card_double_clicked") is not None:
            if (
                inline_field_key is not None
                and card_widget.editing_field_key == inline_field_key
            ):
                card_widget.cancel_inline_edit()
            self._invoke_callback("on_card_double_clicked", event_data)
        elif inline_field_key is not None:
            self.start_inline_card_edit(card_widget.card_id, inline_field_key)
        else:
            self._begin_default_card_edit(card_widget.card_id)

    def _on_card_right_click(self, card_widget: CTkKanbanCard, event: Any) -> None:
        if not self._request_commit_inline_edit():
            return
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
            self._begin_default_card_edit(card_id)

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
        for column in self._column_widgets.values():
            column.set_drop_valid(None)

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
