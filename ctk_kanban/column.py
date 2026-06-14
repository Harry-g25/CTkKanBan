"""Column widget used by :class:`ctk_kanban.CTkKanbanBoard`."""

from __future__ import annotations

from bisect import bisect_left
from typing import Any, Callable

import customtkinter as ctk

from .card import CTkKanbanCard
from .widgets import Tooltip


class CTkKanbanColumn(ctk.CTkFrame):
    """Own one column header, scrollable card layout, and drop indicator."""

    def __init__(
        self,
        master: Any,
        column_data: dict[str, Any],
        theme: dict[str, Any],
        *,
        width: int = 280,
        height: int = 600,
        enable_scroll: bool = True,
        show_card_count: bool = True,
        show_add_button: bool = True,
        show_menu: bool = True,
        control_size: int = 34,
        show_drag_handle: bool = True,
        on_add: Callable[[Any], None] | None = None,
        on_menu: Callable[[Any, Any], None] | None = None,
        on_drag_press: Callable[["CTkKanbanColumn", Any], None] | None = None,
        on_drag_motion: Callable[["CTkKanbanColumn", Any], None] | None = None,
        on_drag_release: Callable[["CTkKanbanColumn", Any], None] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("fg_color", theme["column_fg_color"])
        kwargs.setdefault("border_color", theme["column_border_color"])
        kwargs.setdefault("border_width", theme.get("column_border_width", theme["border_width"]))
        kwargs.setdefault("corner_radius", theme.get("column_corner_radius", theme["corner_radius"]))
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        self.grid_propagate(False)

        self.column_data = column_data
        self.column_id = column_data["id"]
        self.theme = theme
        self.card_widgets: list[CTkKanbanCard] = []
        self.enable_scroll = enable_scroll
        self._on_drag_press = on_drag_press
        self._on_drag_motion = on_drag_motion
        self._on_drag_release = on_drag_release
        self._on_add = on_add
        self._on_menu = on_menu
        self._default_show_card_count = show_card_count
        self._default_show_add_button = show_add_button
        self._default_show_menu = show_menu
        self.control_size = control_size

        color = column_data.get("color") or theme["button_fg_color"]
        self.accent_bar = ctk.CTkFrame(
            self,
            height=4,
            corner_radius=3,
            fg_color=color,
        )
        self.accent_bar.pack(fill="x", padx=12, pady=(10, 0))

        self.header = ctk.CTkFrame(
            self,
            height=52,
            corner_radius=theme.get("column_header_corner_radius", theme["corner_radius"]),
            fg_color=theme["column_header_fg_color"],
        )
        self.header.pack(fill="x", padx=8, pady=(4, 2))
        self.header.grid_columnconfigure(2, weight=1)

        self.color_bar = ctk.CTkFrame(self.header, width=6, height=6, corner_radius=3, fg_color=color)
        self.drag_handle = ctk.CTkLabel(
            self.header,
            text="::",
            width=14,
            text_color=theme.get("muted_text_color", theme["text_color"]),
            cursor="fleur",
            font=ctk.CTkFont(size=9, weight="bold"),
        )
        if show_drag_handle:
            self.drag_handle.grid(row=0, column=1, padx=(1, 4))
            Tooltip(self.drag_handle, "Drag to reorder column")
        self.title_label = ctk.CTkLabel(
            self.header,
            text=str(column_data["title"]),
            anchor="w",
            justify="left",
            wraplength=max(80, width - 148),
            font=theme.get("column_title_font") or ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.get("column_title_text_color", theme["text_color"]),
        )
        self.title_label.grid(row=0, column=2, sticky="ew")

        self.lock_label = ctk.CTkLabel(
            self.header,
            text="LOCKED",
            width=52,
            height=22,
            corner_radius=7,
            fg_color=theme.get("column_lock_fg_color", theme["secondary_button_fg_color"]),
            text_color=theme.get("column_lock_text_color", theme["muted_text_color"]),
            font=ctk.CTkFont(size=9, weight="bold"),
        )
        if column_data.get("locked"):
            self.lock_label.grid(row=0, column=3, padx=3)

        effective_count = bool(column_data.get("show_count", show_card_count))
        self.count_label = ctk.CTkLabel(
            self.header,
            text="0",
            width=28,
            height=24,
            corner_radius=8,
            fg_color=theme.get("column_count_fg_color", theme["secondary_button_fg_color"]),
            text_color=theme.get("column_count_text_color", theme["secondary_button_text_color"]),
            font=theme.get("column_count_font") or ctk.CTkFont(size=11, weight="bold"),
        )
        if effective_count:
            self.count_label.grid(row=0, column=4, padx=4)

        self.add_button = ctk.CTkButton(
            self.header,
            text="+",
            width=max(30, control_size),
            height=max(30, control_size),
            fg_color=theme.get("column_control_fg_color", "transparent"),
            hover_color=theme.get("column_control_hover_color", theme["secondary_button_hover_color"]),
            text_color=theme.get("toolbar_button_text_color", theme["text_color"]),
            corner_radius=9,
            font=theme.get("column_button_font") or ctk.CTkFont(size=18),
            command=lambda: self._on_add(self.column_id) if self._on_add else None,
        )
        if column_data.get("show_add_button", show_add_button):
            self.add_button.grid(row=0, column=5, padx=2)
        Tooltip(self.add_button, "Add a card")

        self.menu_button = ctk.CTkButton(
            self.header,
            text="...",
            width=max(30, control_size),
            height=max(30, control_size),
            fg_color="transparent",
            hover_color=theme.get("column_control_hover_color", theme["secondary_button_hover_color"]),
            text_color=theme.get("toolbar_button_text_color", theme["text_color"]),
            corner_radius=9,
            font=theme.get("column_button_font") or ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self._on_menu(self.column_id, self.menu_button) if self._on_menu else None,
        )
        if column_data.get("show_menu", show_menu):
            self.menu_button.grid(row=0, column=6, padx=(0, 3))
        Tooltip(self.menu_button, "Column actions")

        body_height = max(100, height - 76)
        if enable_scroll:
            self.body: Any = ctk.CTkScrollableFrame(
                self,
                width=width - 16,
                height=body_height,
                fg_color="transparent",
                scrollbar_button_color=theme["scrollbar_button_color"],
                scrollbar_button_hover_color=theme["scrollbar_button_hover_color"],
            )
        else:
            self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=6, pady=(2, 8))

        self.drop_indicator = ctk.CTkFrame(
            self.body,
            height=4,
            corner_radius=2,
            fg_color=theme["drop_indicator_color"],
        )
        self.no_results_label: ctk.CTkLabel | None = None
        self.empty_action: ctk.CTkButton | None = None
        self._drop_indicator_index: int | None = None
        self._drag_card_midpoints: list[int] = []
        self._drag_body_bounds: tuple[int, int] | None = None
        self._bind_header_drag()

    def _bind_header_drag(self) -> None:
        draggable = (self.drag_handle,)
        for widget in draggable:
            widget.bind(
                "<ButtonPress-1>",
                lambda event, col=self: self._dispatch(self._on_drag_press, col, event),
                add="+",
            )
            widget.bind(
                "<B1-Motion>",
                lambda event, col=self: self._dispatch(self._on_drag_motion, col, event),
                add="+",
            )
            widget.bind(
                "<ButtonRelease-1>",
                lambda event, col=self: self._dispatch(self._on_drag_release, col, event),
                add="+",
            )

    def update_column_data(self, column_data: dict[str, Any]) -> None:
        """Apply column metadata and header visibility without rebuilding cards."""

        self.column_data = column_data
        self.column_id = column_data["id"]
        self.title_label.configure(text=str(column_data["title"]))
        color = column_data.get("color") or self.theme["button_fg_color"]
        self.color_bar.configure(fg_color=color)
        self.accent_bar.configure(fg_color=color)
        if column_data.get("locked"):
            self.lock_label.grid(row=0, column=3, padx=3)
        else:
            self.lock_label.grid_remove()

        if column_data.get("show_count", self._default_show_card_count):
            self.count_label.grid(row=0, column=4, padx=4)
        else:
            self.count_label.grid_remove()
        if column_data.get("show_add_button", self._default_show_add_button):
            self.add_button.grid(row=0, column=5, padx=2)
        else:
            self.add_button.grid_remove()
        if column_data.get("show_menu", self._default_show_menu):
            self.menu_button.grid(row=0, column=6, padx=(0, 3))
        else:
            self.menu_button.grid_remove()

    @staticmethod
    def _dispatch(callback: Callable[..., None] | None, *args: Any) -> None:
        if callback is not None:
            callback(*args)

    def add_card_widget(self, card_widget: CTkKanbanCard) -> None:
        """Append a card widget to this column's visual order."""

        self.clear_no_results()
        self.card_widgets.append(card_widget)
        card_widget.pack(fill="x", padx=3, pady=(0, self.theme["card_gap"]))

    def place_card_widget(self, card_widget: CTkKanbanCard, index: int) -> bool:
        """Place one card at *index* without repacking unaffected cards.

        Returns ``True`` when the visible order changed. Tk widgets cannot be
        reparented, so callers must only pass widgets already owned by this
        column's body.
        """

        bounded_index = max(0, min(int(index), len(self.card_widgets)))
        if card_widget in self.card_widgets:
            old_index = self.card_widgets.index(card_widget)
            self.card_widgets.pop(old_index)
            bounded_index = max(0, min(bounded_index, len(self.card_widgets)))
            if old_index == bounded_index:
                self.card_widgets.insert(old_index, card_widget)
                return False
        self.card_widgets.insert(bounded_index, card_widget)
        card_widget.pack_forget()
        options = {"fill": "x", "padx": 3, "pady": (0, self.theme["card_gap"])}
        if bounded_index + 1 < len(self.card_widgets):
            card_widget.pack(before=self.card_widgets[bounded_index + 1], **options)
        else:
            card_widget.pack(**options)
        self.clear_no_results()
        return True

    def set_card_widget_order(self, ordered_widgets: list[CTkKanbanCard]) -> bool:
        """Apply a complete visible order while preserving widget instances."""

        if self.card_widgets == ordered_widgets:
            return False
        self.drop_indicator.pack_forget()
        self._drop_indicator_index = None
        for widget in self.card_widgets:
            widget.pack_forget()
        self.card_widgets = list(ordered_widgets)
        for widget in self.card_widgets:
            widget.pack(fill="x", padx=3, pady=(0, self.theme["card_gap"]))
        if self.card_widgets:
            self.clear_no_results()
        return True

    def remove_card_widget(self, card_widget: CTkKanbanCard) -> None:
        """Detach a known card widget from the column."""

        if card_widget in self.card_widgets:
            self.card_widgets.remove(card_widget)
        card_widget.pack_forget()

    def update_card_count(self, count: int | None = None) -> None:
        """Update the header count using total cards unless explicitly given."""

        total = len(self.card_widgets) if count is None else count
        maximum = self.column_data.get("max_cards")
        self.count_label.configure(text=f"{total} / {maximum}" if maximum is not None else str(total))
        blocked = bool(self.column_data.get("locked")) or (maximum is not None and total >= maximum)
        full = maximum is not None and total >= maximum
        self.count_label.configure(
            fg_color=(
                self.theme.get("column_count_full_fg_color", self.theme["column_count_fg_color"])
                if full
                else self.theme["column_count_fg_color"]
            ),
            text_color=(
                self.theme.get("column_count_full_text_color", self.theme["column_count_text_color"])
                if full
                else self.theme["column_count_text_color"]
            ),
        )
        self.add_button.configure(state="disabled" if blocked else "normal")

    def show_drop_indicator(self, index: int) -> None:
        """Place the drop marker before the requested card index."""

        bounded_index = max(0, min(int(index), len(self.card_widgets)))
        if self._drop_indicator_index == bounded_index:
            return
        self.drop_indicator.pack_forget()
        options = {"fill": "x", "padx": 5, "pady": (0, 5)}
        if bounded_index < len(self.card_widgets):
            self.drop_indicator.pack(before=self.card_widgets[bounded_index], **options)
        else:
            self.drop_indicator.pack(**options)
        self._drop_indicator_index = bounded_index

    def clear_drop_indicator(self) -> None:
        """Hide the active drop marker."""

        if self._drop_indicator_index is None:
            return
        self.drop_indicator.pack_forget()
        self._drop_indicator_index = None

    def prepare_drag_geometry(self, excluding_id: Any | None = None) -> None:
        """Cache card midpoints and body bounds for the active drag.

        Crossing the Python/Tcl boundary for every card on every mouse event is
        expensive. One cache fill lets insertion lookup use binary search.
        """

        self._drag_card_midpoints = [
            card.winfo_rooty() + card.winfo_height() // 2
            for card in self.card_widgets
            if card.card_id != excluding_id
        ]
        top = self.body.winfo_rooty()
        self._drag_body_bounds = (top, top + self.body.winfo_height())

    def clear_drag_geometry(self) -> None:
        """Release geometry cached for a completed drag."""

        self._drag_card_midpoints = []
        self._drag_body_bounds = None

    def card_index_at(self, root_y: int, excluding_id: Any | None = None) -> int:
        """Return the insertion index nearest the pointer's vertical position."""

        if self._drag_body_bounds is not None:
            return bisect_left(self._drag_card_midpoints, root_y)
        candidates = [card for card in self.card_widgets if card.card_id != excluding_id]
        for index, card in enumerate(candidates):
            midpoint = card.winfo_rooty() + card.winfo_height() // 2
            if root_y < midpoint:
                return index
        return len(candidates)

    def contains_point(self, root_x: int, root_y: int) -> bool:
        """Return whether a root-coordinate point lies over the column."""

        return (
            self.winfo_rootx() <= root_x <= self.winfo_rootx() + self.winfo_width()
            and self.winfo_rooty() <= root_y <= self.winfo_rooty() + self.winfo_height()
        )

    def autoscroll(self, root_y: int, margin: int = 42) -> bool:
        """Scroll near a body edge and return whether scrolling occurred."""

        if not self.enable_scroll or not hasattr(self.body, "_parent_canvas"):
            return False
        if self._drag_body_bounds is None:
            top = self.body.winfo_rooty()
            bottom = top + self.body.winfo_height()
        else:
            top, bottom = self._drag_body_bounds
        canvas = self.body._parent_canvas
        if root_y < top + margin:
            canvas.yview_scroll(-1, "units")
            return True
        elif root_y > bottom - margin:
            canvas.yview_scroll(1, "units")
            return True
        return False

    def show_no_results(self, text: str = "No cards match the current view", *, allow_add: bool = False) -> None:
        """Display an empty-result message inside the column."""

        if self.no_results_label is None:
            self.no_results_label = ctk.CTkLabel(
                self.body,
                text=text,
                justify="center",
                wraplength=210,
                text_color=self.theme.get("column_no_results_text_color", self.theme["overlay_text_color"]),
                font=self.theme.get("card_metadata_font") or ctk.CTkFont(size=12),
            )
        self.no_results_label.pack(padx=18, pady=(36, 14))
        if allow_add and not self.column_data.get("locked"):
            if self.empty_action is None:
                self.empty_action = ctk.CTkButton(
                    self.body,
                    text="Add first card",
                    width=130,
                    height=34,
                    corner_radius=self.theme.get("button_corner_radius", 10),
                    fg_color=self.theme["button_fg_color"],
                    hover_color=self.theme["button_hover_color"],
                    text_color=self.theme["button_text_color"],
                    command=lambda: self._on_add(self.column_id) if self._on_add else None,
                )
            self.empty_action.pack(pady=(0, 18))

    def clear_no_results(self) -> None:
        if self.no_results_label is not None:
            self.no_results_label.pack_forget()
        if self.empty_action is not None:
            self.empty_action.pack_forget()

    def set_drop_valid(self, valid: bool | None) -> None:
        """Highlight valid and invalid drag targets before the pointer is released."""

        if valid is None:
            self.configure(
                border_color=self.theme["column_border_color"],
                border_width=self.theme.get("column_border_width", self.theme["border_width"]),
            )
        elif valid:
            self.configure(border_color=self.theme["drop_indicator_color"], border_width=2)
        else:
            self.configure(border_color=self.theme["danger_color"], border_width=2)

    def set_width(self, width: int) -> None:
        self.configure(width=width)
        self.title_label.configure(wraplength=max(80, width - 148))
        if hasattr(self.body, "configure"):
            try:
                self.body.configure(width=max(120, width - 16))
            except (TypeError, ValueError):
                pass
