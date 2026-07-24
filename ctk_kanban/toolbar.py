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
        kwargs.setdefault("height", int(theme.get("toolbar_height", 64)))
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

        self.grid_columnconfigure(1, weight=1)
        if show_search:
            self.search_group = ctk.CTkFrame(self, fg_color="transparent")
            self.search_group.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=10)
            self.search_group.grid_columnconfigure(0, weight=1)
            self.search_entry = ctk.CTkEntry(
                self.search_group,
                width=int(theme.get("toolbar_search_width", 400)),
                placeholder_text="Search cards…",
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
                font=theme.get("input_font") or theme.get("toolbar_font"),
            )
            self.search_entry.grid(row=0, column=0, sticky="ew")
            self.search_entry.bind("<KeyRelease>", self._queue_search)
            self.search_entry.bind("<FocusIn>", lambda _event: self._set_search_focus(True), add="+")
            self.search_entry.bind("<FocusOut>", lambda _event: self._set_search_focus(False), add="+")
            self.search_clear_button = ctk.CTkButton(
                self.search_group,
                text="×",
                width=30,
                height=30,
                fg_color=theme["secondary_button_fg_color"],
                hover_color=theme["secondary_button_hover_color"],
                text_color=theme.get("toolbar_button_text_color", theme["text_color"]),
                corner_radius=8,
                font=ctk.CTkFont(size=15),
                command=on_clear_search,
            )
            self.search_clear_button.grid(row=0, column=1, padx=(6, 0))
            self.search_clear_button.grid_remove()
        else:
            self.spacer = ctk.CTkFrame(self, fg_color="transparent")
            self.spacer.grid(row=0, column=0, sticky="ew", padx=(12, 0))

        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.grid(row=0, column=1, sticky="w")
        self.result_label = ctk.CTkLabel(
            self.status_frame,
            text="",
            height=28,
            corner_radius=8,
            fg_color=theme.get("toolbar_count_fg_color", theme["secondary_button_fg_color"]),
            text_color=theme.get("toolbar_text_color", theme["text_color"]),
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.result_label.pack(side="left")
        self.persistence_label = ctk.CTkLabel(
            self.status_frame,
            text="",
            text_color=theme.get("muted_text_color", theme["text_color"]),
            height=28,
            corner_radius=8,
        )
        self.persistence_label.pack(side="left", padx=(7, 0))
        self.retry_button = ctk.CTkButton(
            self.status_frame,
            text="Retry",
            width=58,
            height=28,
            fg_color=theme["secondary_button_fg_color"],
            hover_color=theme["secondary_button_hover_color"],
            text_color=theme.get("secondary_button_text_color", theme["text_color"]),
            corner_radius=8,
            command=on_retry,
        )
        self.retry_button.pack(side="left", padx=(6, 0))
        self.retry_button.pack_forget()

        button_options = {
            "height": 38,
            "fg_color": theme["secondary_button_fg_color"],
            "hover_color": theme["secondary_button_hover_color"],
            "text_color": theme.get("toolbar_button_text_color", theme["secondary_button_text_color"]),
            "text_color_disabled": theme.get(
                "secondary_button_text_color_disabled",
                theme.get("button_text_color_disabled"),
            ),
            "font": theme.get("toolbar_font") or theme.get("secondary_button_font"),
            "corner_radius": theme.get("secondary_button_corner_radius", theme["button_corner_radius"]),
            "border_color": theme.get("toolbar_action_border_color", theme["toolbar_border_color"]),
            "border_width": 1,
        }
        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.grid(row=0, column=2, sticky="e", padx=(8, 11), pady=9)
        action_column = 0
        if show_filter_button:
            self.filter_button = ctk.CTkButton(
                self.actions,
                text="Filters",
                width=82,
                command=lambda: on_filter(self.filter_button) if on_filter else None,
                **button_options,
            )
            self.filter_button.grid(row=0, column=action_column, padx=3)
            action_column += 1
        if show_sort_button:
            self.sort_button = ctk.CTkButton(
                self.actions,
                text="↕  Sort",
                width=94,
                command=lambda: on_sort(self.sort_button) if on_sort else None,
                **button_options,
            )
            self.sort_button.grid(row=0, column=action_column, padx=3)
            action_column += 1
        if show_clear_filters_button:
            self.clear_button = ctk.CTkButton(
                self.actions,
                text="Clear",
                width=70,
                command=on_clear,
                **button_options,
            )
            self.clear_button.grid(row=0, column=action_column, padx=3)
            self.clear_button.grid_remove()
            action_column += 1
        if show_add_card_button:
            self.add_button = ctk.CTkButton(
                self.actions,
                text="＋  Add card",
                width=116,
                height=40,
                fg_color=theme["button_fg_color"],
                hover_color=theme["button_hover_color"],
                text_color=theme.get("toolbar_primary_button_text_color", theme["button_text_color"]),
                text_color_disabled=theme.get("button_text_color_disabled"),
                font=theme.get("toolbar_font") or theme.get("button_font"),
                corner_radius=theme.get("button_corner_radius", theme["corner_radius"]),
                border_width=theme.get("button_border_width", theme["border_width"]),
                command=lambda: on_add(self.add_button) if on_add else None,
            )
            self.add_button.grid(row=0, column=action_column, padx=(5, 0))

        self.summary_frame = ctk.CTkFrame(
            self,
            height=30,
            fg_color=theme.get("toolbar_context_fg_color", "transparent"),
            border_color=theme.get("toolbar_context_border_color", theme["toolbar_border_color"]),
            border_width=1,
            corner_radius=9,
        )
        self.summary_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 10))
        self.summary_frame.grid_columnconfigure(2, weight=1)
        self.filter_summary_label = ctk.CTkLabel(
            self.summary_frame,
            text="",
            text_color=theme.get("toolbar_summary_text_color", theme["muted_text_color"]),
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.filter_summary_label.grid(row=0, column=0, sticky="w", padx=(10, 0), pady=5)
        self.filter_chip_frame = ctk.CTkFrame(self.summary_frame, height=22, fg_color="transparent")
        self.filter_chip_frame.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=4)
        self.sort_summary_label = ctk.CTkLabel(
            self.summary_frame,
            text="Manual order",
            text_color=theme.get("toolbar_summary_text_color", theme["muted_text_color"]),
            font=ctk.CTkFont(size=10),
        )
        self.sort_summary_label.grid(row=0, column=2, sticky="e", padx=10, pady=5)
        self.summary_frame.grid_remove()
        if hasattr(self, "search_entry"):
            self.bind("<Configure>", self._resize_search, add="+")

    def _resize_search(self, event: Any) -> None:
        """Keep the command bar usable when an embedded form narrows the board."""

        if not hasattr(self, "search_entry"):
            return
        scaling = self._get_widget_scaling()
        logical_width = event.width / scaling
        show_count = logical_width >= 720
        if show_count and not self.result_label.winfo_manager():
            self.result_label.pack(side="left", before=self.persistence_label)
        elif not show_count and self.result_label.winfo_manager():
            self.result_label.pack_forget()

        reserved = self.actions.winfo_reqwidth() / scaling + 44
        if show_count:
            reserved += self.status_frame.winfo_reqwidth() / scaling
        target = max(
            170,
            min(
                int(self.theme.get("toolbar_search_width", 400)),
                int(logical_width - reserved),
            ),
        )
        if int(float(self.search_entry.cget("width"))) != target:
            self.search_entry.configure(width=target)

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

    def _sync_context_visibility(self) -> None:
        """Only spend a second toolbar row when active filters need context."""

        if self._filter_active:
            self.summary_frame.grid()
        else:
            self.summary_frame.grid_remove()

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
                text=f"Filters · {effective_count}" if active else "Filters",
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
            noun = "filter" if effective_count == 1 else "filters"
            self.filter_summary_label.configure(text=f"{effective_count} active {noun}" if active else "")
        self._sync_context_visibility()
        self._update_reset_visibility()

    def set_filter_chips(self, filters: dict[str, Any]) -> None:
        """Render compact labels for each active filter."""

        for child in self.filter_chip_frame.winfo_children():
            child.destroy()
        operator_labels = {
            "eq": "is",
            "ne": "is not",
            "contains": "contains",
            "not_contains": "excludes",
            "in": "is any of",
            "gt": ">",
            "gte": "≥",
            "lt": "<",
            "lte": "≤",
            "between": "between",
            "empty": "is empty",
            "not_empty": "is not empty",
        }
        for key, condition in list(filters.items())[:4]:
            label = key.replace("_", " ").capitalize()
            if isinstance(condition, dict) and "op" in condition:
                value = condition.get("value")
                operation = operator_labels.get(str(condition["op"]), str(condition["op"]))
                text = f"{label} {operation}"
                if value not in (None, ""):
                    shown = (
                        ", ".join(str(item) for item in value)
                        if isinstance(value, (list, tuple, set))
                        else value
                    )
                    text = f"{text} {shown}"
            elif key == "overdue_only":
                text = "Overdue"
            else:
                text = f"{label}: {condition}"
            ctk.CTkLabel(
                self.filter_chip_frame,
                text=text,
                height=19,
                corner_radius=5,
                fg_color=self.theme.get("filter_chip_fg_color", self.theme["secondary_button_fg_color"]),
                text_color=self.theme.get("filter_chip_text_color", self.theme["secondary_button_text_color"]),
                font=ctk.CTkFont(size=9, weight="bold"),
            ).pack(side="left", padx=2)
        self._sync_context_visibility()

    def set_sort(self, key: str, reverse: bool = False) -> None:
        """Show the active sort without requiring the menu to be reopened."""

        label = key.replace("_", " ").title()
        direction = "descending" if reverse else "ascending"
        if hasattr(self, "sort_button"):
            arrow = "↕" if key == "manual" else ("↓" if reverse else "↑")
            self.sort_button.configure(text=f"{arrow}  {label}")
        self.sort_summary_label.configure(
            text="Manual order" if key == "manual" else f"{label}, {direction}"
        )

    def set_result_count(self, visible: int, total: int | None = None) -> None:
        total = visible if total is None else total
        noun = "card" if total == 1 else "cards"
        text = f"{visible} {noun}" if visible == total else f"{visible} of {total} {noun}"
        self.result_label.configure(text=f"  {text}  ")

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
            if not self.retry_button.winfo_manager():
                self.retry_button.pack(side="left", padx=(6, 0))
        else:
            self.retry_button.pack_forget()

    def destroy(self) -> None:
        """Cancel the pending debounced search before widget destruction."""

        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except (ValueError, tk.TclError):
                pass
            self._search_after_id = None
        super().destroy()
