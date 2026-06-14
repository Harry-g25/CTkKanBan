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
        on_clear_search: Callable[[], None] | None = None,
        on_retry: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("height", 86)
        kwargs.setdefault("fg_color", theme["toolbar_fg_color"])
        kwargs.setdefault("border_color", theme["toolbar_border_color"])
        kwargs.setdefault("border_width", theme.get("toolbar_border_width", theme["border_width"]))
        kwargs.setdefault("corner_radius", theme.get("toolbar_corner_radius", theme["corner_radius"]))
        super().__init__(master, **kwargs)
        self.theme = theme
        self._on_search = on_search
        self._search_after_id: str | None = None
        self._search_active = False
        self._filter_active = False

        self.grid_columnconfigure(0, weight=1)
        action_column = 1
        if show_search:
            self.search_entry = ctk.CTkEntry(
                self,
                placeholder_text="Search title, tag, assignee...",
                height=40,
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
            self.search_entry.bind("<FocusIn>", lambda _event: self._set_search_focus(True), add="+")
            self.search_entry.bind("<FocusOut>", lambda _event: self._set_search_focus(False), add="+")
            self.search_clear_button = ctk.CTkButton(
                self,
                text="x",
                width=32,
                height=32,
                fg_color="transparent",
                hover_color=theme["secondary_button_hover_color"],
                text_color=theme.get("toolbar_button_text_color", theme["text_color"]),
                corner_radius=9,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=on_clear_search,
            )
            self.search_clear_button.grid(row=0, column=action_column, padx=(0, 3), pady=9)
            self.search_clear_button.grid_remove()
            action_column += 1
        else:
            self.spacer = ctk.CTkFrame(self, fg_color="transparent")
            self.spacer.grid(row=0, column=0, sticky="ew")

        button_options = {
            "height": 36,
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
                text="Filters",
                width=82,
                command=lambda: on_filter(self.filter_button) if on_filter else None,
                **button_options,
            )
            self.filter_button.grid(row=0, column=action_column, padx=3, pady=9)
            action_column += 1
        if show_sort_button:
            self.sort_button = ctk.CTkButton(
                self,
                text="Sort",
                width=76,
                command=lambda: on_sort(self.sort_button) if on_sort else None,
                **button_options,
            )
            self.sort_button.grid(row=0, column=action_column, padx=3, pady=9)
            action_column += 1
        if show_clear_filters_button:
            self.clear_button = ctk.CTkButton(
                self,
                text="Reset",
                width=72,
                command=on_clear,
                **button_options,
            )
            self.clear_button.grid(row=0, column=action_column, padx=3, pady=9)
            self.clear_button.grid_remove()
            action_column += 1
        if show_add_card_button:
            self.add_button = ctk.CTkButton(
                self,
                text="+ Add card",
                width=104,
                height=38,
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

        self.summary_frame = ctk.CTkFrame(self, height=24, fg_color="transparent")
        self.summary_frame.grid(row=1, column=0, columnspan=action_column + 1, sticky="ew", padx=12, pady=(0, 9))
        self.summary_frame.grid_columnconfigure(3, weight=1)
        self.result_label = ctk.CTkLabel(
            self.summary_frame,
            text="",
            text_color=theme.get("toolbar_text_color", theme["text_color"]),
            anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.result_label.grid(row=0, column=0, sticky="w")
        self.filter_summary_label = ctk.CTkLabel(
            self.summary_frame,
            text="",
            text_color=theme.get("toolbar_summary_text_color", theme["muted_text_color"]),
        )
        self.filter_summary_label.grid(row=0, column=1, padx=12)
        self.filter_chip_frame = ctk.CTkFrame(self.summary_frame, height=24, fg_color="transparent")
        self.filter_chip_frame.grid(row=0, column=2, sticky="w")
        self.sort_summary_label = ctk.CTkLabel(
            self.summary_frame,
            text="Manual order",
            text_color=theme.get("toolbar_summary_text_color", theme["muted_text_color"]),
        )
        self.sort_summary_label.grid(row=0, column=3, sticky="w", padx=(8, 0))
        self.persistence_label = ctk.CTkLabel(
            self.summary_frame,
            text="",
            text_color=theme.get("muted_text_color", theme["text_color"]),
            height=22,
            corner_radius=7,
        )
        self.persistence_label.grid(row=0, column=4, padx=(8, 0))
        self.retry_button = ctk.CTkButton(
            self.summary_frame,
            text="Retry",
            width=60,
            height=24,
            fg_color=theme["secondary_button_fg_color"],
            hover_color=theme["secondary_button_hover_color"],
            text_color=theme.get("secondary_button_text_color", theme["text_color"]),
            command=on_retry,
        )
        self.retry_button.grid(row=0, column=5, padx=(6, 0))
        self.retry_button.grid_remove()

    def _set_search_focus(self, focused: bool) -> None:
        if not hasattr(self, "search_entry"):
            return
        self.search_entry.configure(
            border_color=(
                self.theme.get("search_focus_border_color", self.theme["search_border_color"])
                if focused
                else self.theme["search_border_color"]
            )
        )

    def _update_reset_visibility(self) -> None:
        if not hasattr(self, "clear_button"):
            return
        if self._search_active or self._filter_active:
            self.clear_button.grid()
        else:
            self.clear_button.grid_remove()

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
            query = self.search_entry.get()
            self._search_active = bool(query.strip())
            self._update_reset_visibility()
            self._on_search(query)

    def set_search_query(self, query: str) -> None:
        """Synchronize the search entry without emitting a duplicate event."""

        if not hasattr(self, "search_entry"):
            return
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, query)
        self._search_active = bool(query)
        if hasattr(self, "search_clear_button"):
            if query:
                self.search_clear_button.grid()
            else:
                self.search_clear_button.grid_remove()
        self._update_reset_visibility()

    def set_filter_active(self, active: bool, count: int | None = None) -> None:
        """Indicate whether the board currently has active filters."""

        self._filter_active = active
        if hasattr(self, "filter_button"):
            effective_count = count if count is not None else (1 if active else 0)
            self.filter_button.configure(
                text=f"Filters ({effective_count})" if active else "Filters",
                fg_color=(
                    self.theme.get("filter_chip_fg_color", self.theme["secondary_button_fg_color"])
                    if active
                    else self.theme["secondary_button_fg_color"]
                ),
                text_color=(
                    self.theme.get("filter_chip_text_color", self.theme["secondary_button_text_color"])
                    if active
                    else self.theme["secondary_button_text_color"]
                ),
            )
        if hasattr(self, "filter_summary_label"):
            effective_count = count if count is not None else (1 if active else 0)
            self.filter_summary_label.configure(text=f"{effective_count} active filter(s)" if active else "")
        self._update_reset_visibility()

    def set_filter_chips(self, filters: dict[str, Any]) -> None:
        """Render compact labels for each active filter."""

        for child in self.filter_chip_frame.winfo_children():
            child.destroy()
        for key, condition in list(filters.items())[:4]:
            if isinstance(condition, dict) and "op" in condition:
                value = condition.get("value")
                text = f"{key}: {condition['op']} {'' if value is None else value}"
            elif key == "overdue_only":
                text = "Overdue"
            else:
                text = f"{key}: {condition}"
            ctk.CTkLabel(
                self.filter_chip_frame,
                text=text,
                height=22,
                corner_radius=7,
                fg_color=self.theme.get("filter_chip_fg_color", self.theme["secondary_button_fg_color"]),
                text_color=self.theme.get("filter_chip_text_color", self.theme["secondary_button_text_color"]),
                font=ctk.CTkFont(size=10, weight="bold"),
            ).pack(side="left", padx=2)

    def set_sort(self, key: str, reverse: bool = False) -> None:
        """Show the active sort without requiring the menu to be reopened."""

        label = key.replace("_", " ").title()
        direction = "descending" if reverse else "ascending"
        if hasattr(self, "sort_button"):
            self.sort_button.configure(text=f"Sort: {label}")
        self.sort_summary_label.configure(text=f"{label}, {direction}")

    def set_result_count(self, visible: int, total: int | None = None) -> None:
        total = visible if total is None else total
        noun = "card" if total == 1 else "cards"
        text = f"{visible} {noun}" if visible == total else f"{visible} of {total} {noun}"
        self.result_label.configure(text=text)

    def set_persistence_status(self, state: str, message: str | None = None) -> None:
        """Render saving, saved, offline, conflict, and failure states."""

        default_messages = {
            "loading": "Loading...",
            "saving": "Saving...",
            "saved": "Saved",
            "offline": "Offline",
            "retrying": "Retrying...",
            "conflict": "Conflict",
            "error": "Save failed",
        }
        style = {
            "saved": (
                self.theme.get("success_surface_color", "transparent"),
                self.theme.get("success_color", self.theme["muted_text_color"]),
            ),
            "offline": (
                self.theme.get("warning_surface_color", "transparent"),
                self.theme.get("warning_color", self.theme["muted_text_color"]),
            ),
            "conflict": (
                self.theme.get("danger_surface_color", "transparent"),
                self.theme.get("danger_color", self.theme["muted_text_color"]),
            ),
            "error": (
                self.theme.get("danger_surface_color", "transparent"),
                self.theme.get("danger_color", self.theme["muted_text_color"]),
            ),
        }
        fg_color, text_color = style.get(
            state,
            ("transparent", self.theme.get("muted_text_color", self.theme["text_color"])),
        )
        status_text = message or default_messages.get(state, "")
        self.persistence_label.configure(
            text=f"  {status_text}  " if status_text else "",
            fg_color=fg_color,
            text_color=text_color,
        )
        if state in {"offline", "conflict", "error"}:
            self.retry_button.grid()
        else:
            self.retry_button.grid_remove()

    def destroy(self) -> None:
        """Cancel the pending debounced search before widget destruction."""

        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except (ValueError, tk.TclError):
                pass
            self._search_after_id = None
        super().destroy()
