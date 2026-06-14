"""Optional search and action toolbar for the board."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk


class CTkKanbanToolbar(ctk.CTkFrame):
    """Configurable toolbar whose controls delegate all behavior to the board."""

    def __init__(
        self,
        master: Any,
        theme: dict[str, Any],
        *,
        show_search: bool = True,
        show_filter_button: bool = True,
        show_sort_button: bool = True,
        show_add_card_button: bool = True,
        show_clear_filters_button: bool = True,
        on_search: Callable[[str], None] | None = None,
        on_filter: Callable[[Any], None] | None = None,
        on_sort: Callable[[Any], None] | None = None,
        on_add: Callable[[Any], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", theme["toolbar_fg_color"])
        kwargs.setdefault("border_color", theme["toolbar_border_color"])
        kwargs.setdefault("border_width", theme.get("toolbar_border_width", theme["border_width"]))
        kwargs.setdefault("corner_radius", theme.get("toolbar_corner_radius", theme["corner_radius"]))
        super().__init__(master, **kwargs)
        self.theme = theme
        self._on_search = on_search
        self._search_after_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        action_column = 1
        if show_search:
            self.search_entry = ctk.CTkEntry(
                self,
                placeholder_text="Search cards...",
                height=34,
                fg_color=theme["search_fg_color"],
                border_color=theme["search_border_color"],
                text_color=theme.get("search_text_color", theme["text_color"]),
                placeholder_text_color=theme.get(
                    "search_placeholder_text_color",
                    theme.get("input_placeholder_text_color"),
                ),
                corner_radius=theme.get("input_corner_radius", theme["corner_radius"]),
                border_width=theme.get("input_border_width", theme["border_width"]),
                font=theme.get("toolbar_font") or theme.get("input_font"),
            )
            self.search_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=9)
            self.search_entry.bind("<KeyRelease>", self._queue_search)
        else:
            self.spacer = ctk.CTkFrame(self, fg_color="transparent")
            self.spacer.grid(row=0, column=0, sticky="ew")

        button_options = {
            "height": 32,
            "fg_color": theme["secondary_button_fg_color"],
            "hover_color": theme["secondary_button_hover_color"],
            "text_color": theme.get("toolbar_button_text_color", theme["secondary_button_text_color"]),
            "text_color_disabled": theme.get(
                "secondary_button_text_color_disabled",
                theme.get("button_text_color_disabled"),
            ),
            "font": theme.get("toolbar_font") or theme.get("secondary_button_font"),
            "corner_radius": theme.get("secondary_button_corner_radius", theme["button_corner_radius"]),
            "border_width": theme.get("secondary_button_border_width", theme["button_border_width"]),
        }
        if show_filter_button:
            self.filter_button = ctk.CTkButton(
                self,
                text="Filter",
                width=76,
                command=lambda: on_filter(self.filter_button) if on_filter else None,
                **button_options,
            )
            self.filter_button.grid(row=0, column=action_column, padx=3, pady=9)
            action_column += 1
        if show_sort_button:
            self.sort_button = ctk.CTkButton(
                self,
                text="Sort",
                width=70,
                command=lambda: on_sort(self.sort_button) if on_sort else None,
                **button_options,
            )
            self.sort_button.grid(row=0, column=action_column, padx=3, pady=9)
            action_column += 1
        if show_clear_filters_button:
            self.clear_button = ctk.CTkButton(
                self,
                text="Clear",
                width=70,
                command=on_clear,
                **button_options,
            )
            self.clear_button.grid(row=0, column=action_column, padx=3, pady=9)
            action_column += 1
        if show_add_card_button:
            self.add_button = ctk.CTkButton(
                self,
                text="Add card",
                width=90,
                height=32,
                fg_color=theme["button_fg_color"],
                hover_color=theme["button_hover_color"],
                text_color=theme.get("toolbar_primary_button_text_color", theme["button_text_color"]),
                text_color_disabled=theme.get("button_text_color_disabled"),
                font=theme.get("toolbar_font") or theme.get("button_font"),
                corner_radius=theme.get("button_corner_radius", theme["corner_radius"]),
                border_width=theme.get("button_border_width", theme["border_width"]),
                command=lambda: on_add(self.add_button) if on_add else None,
            )
            self.add_button.grid(row=0, column=action_column, padx=(5, 10), pady=9)

    def _queue_search(self, _event: Any) -> None:
        if self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except (ValueError, tk.TclError):
                pass
        self._search_after_id = self.after(180, self._emit_search)

    def _emit_search(self) -> None:
        self._search_after_id = None
        if self._on_search and hasattr(self, "search_entry"):
            self._on_search(self.search_entry.get())

    def set_search_query(self, query: str) -> None:
        """Synchronize the search entry without emitting a duplicate event."""

        if not hasattr(self, "search_entry"):
            return
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, query)

    def set_filter_active(self, active: bool) -> None:
        """Indicate whether the board currently has active filters."""

        if hasattr(self, "filter_button"):
            self.filter_button.configure(text="Filter *" if active else "Filter")

    def destroy(self) -> None:
        """Cancel the pending debounced search before widget destruction."""

        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except (ValueError, tk.TclError):
                pass
            self._search_after_id = None
        super().destroy()
