"""Compact card widget for the Kanban board."""

from __future__ import annotations

from typing import Any, Callable, Mapping

import customtkinter as ctk

CardCallback = Callable[["CTkKanbanCard"], None]
PointerCallback = Callable[["CTkKanbanCard", Any], None]


class CTkKanbanCard(ctk.CTkFrame):
    """Render one card with an open action, menu, and handle-only dragging."""

    def __init__(
        self,
        master: Any,
        card: Mapping[str, Any],
        theme: Mapping[str, Any],
        *,
        on_select: CardCallback | None = None,
        on_edit: CardCallback | None = None,
        on_menu: CardCallback | None = None,
        on_drag_press: PointerCallback | None = None,
        on_drag_motion: PointerCallback | None = None,
        on_drag_release: PointerCallback | None = None,
        drag_enabled: bool = True,
        width: int = 264,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=1,
            fg_color=theme["card_fg_color"],
            border_color=theme["card_border_color"],
            border_width=1,
            corner_radius=10,
        )
        self.card = dict(card)
        self.card_id = self.card["id"]
        self.theme = dict(theme)
        self._on_select = on_select
        self._on_edit = on_edit
        self._on_menu = on_menu
        self._selected = False
        self._dragging = False
        self._hovered = False

        self.grid_columnconfigure(1, weight=1)

        priority = str(self.card.get("priority") or "").strip()
        priority_key = priority.casefold()
        strip_color = (
            self.theme.get(f"priority_{priority_key}_color", self.theme["accent_color"])
            if priority
            else self.theme["accent_color"]
        )
        self.priority_strip = ctk.CTkFrame(
            self,
            width=4,
            height=1,
            corner_radius=2,
            fg_color=strip_color,
        )
        self.priority_strip.grid(
            row=0,
            column=0,
            rowspan=3,
            padx=(8, 0),
            pady=10,
            sticky="ns",
        )

        self.title_label = ctk.CTkLabel(
            self,
            text=str(self.card.get("title") or "Untitled"),
            anchor="w",
            justify="left",
            wraplength=max(140, width - 104),
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.title_label.grid(
            row=0,
            column=1,
            padx=(12, 4),
            pady=(11, 3),
            sticky="ew",
        )

        self.drag_handle = ctk.CTkLabel(
            self,
            text="⠇",
            width=24,
            height=26,
            cursor="fleur" if drag_enabled else "arrow",
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        if drag_enabled:
            self.drag_handle.grid(row=0, column=2, padx=(2, 0), pady=(8, 2), sticky="n")

        self.menu_button = ctk.CTkButton(
            self,
            text="⋯",
            width=30,
            height=26,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self._menu,
        )
        self.menu_button.grid(row=0, column=3, padx=(0, 8), pady=(8, 2), sticky="n")

        # Compatibility for integrations that invoked the former visible edit
        # button directly. The card surface is now the visible open action.
        self.edit_button = ctk.CTkButton(
            self,
            text="",
            width=1,
            height=1,
            command=self._edit,
        )

        next_row = 1
        description = str(self.card.get("description") or "").strip()
        if description:
            if len(description) > 150:
                description = f"{description[:149].rstrip()}…"
            self.description_label = ctk.CTkLabel(
                self,
                text=description,
                anchor="w",
                justify="left",
                wraplength=max(160, width - 48),
                text_color=self.theme["muted_text_color"],
                font=ctk.CTkFont(size=11),
            )
            self.description_label.grid(
                row=next_row,
                column=1,
                columnspan=3,
                padx=(12, 10),
                pady=(1, 7),
                sticky="ew",
            )
            next_row += 1

        raw_tags = self.card.get("tags") or []
        if isinstance(raw_tags, str):
            tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
        else:
            tags = [str(item).strip() for item in raw_tags if str(item).strip()]
        self.priority_pill: ctk.CTkLabel | None = None
        self.tag_pills: list[ctk.CTkLabel] = []
        if priority or tags:
            self.metadata_frame = ctk.CTkFrame(self, height=1, fg_color="transparent")
            self.metadata_frame.grid(
                row=next_row,
                column=1,
                columnspan=3,
                padx=(12, 10),
                pady=(0, 11),
                sticky="ew",
            )
            pills: list[tuple[str, Any, bool]] = []
            if priority:
                color = self.theme.get(
                    f"priority_{priority.casefold()}_color",
                    self.theme["accent_color"],
                )
                pills.append((priority, color, True))
            palette = self.theme["tag_pill_colors"]
            for tag in tags[:4]:
                display = tag if len(tag) <= 18 else f"{tag[:17]}…"
                color_index = sum(ord(character) for character in tag) % len(palette)
                pills.append((f"#{display}", palette[color_index], False))
            self._build_pill_rows(pills, max_width=max(160, width - 48))
        elif not description:
            self.title_label.grid_configure(pady=(11, 11))

        interactive: list[Any] = [self, self.priority_strip, self.title_label]
        if hasattr(self, "description_label"):
            interactive.append(self.description_label)
        if hasattr(self, "metadata_frame"):
            interactive.append(self.metadata_frame)
        interactive.extend(pill for pill in [self.priority_pill, *self.tag_pills] if pill is not None)
        for widget in interactive:
            self._bind_select(widget)
            self._bind_hover(widget)

        if drag_enabled:
            self.drag_handle.bind(
                "<ButtonPress-1>",
                lambda event: self._dispatch_pointer(on_drag_press, event),
                add="+",
            )
            self.drag_handle.bind(
                "<B1-Motion>",
                lambda event: self._dispatch_pointer(on_drag_motion, event),
                add="+",
            )
            self.drag_handle.bind(
                "<ButtonRelease-1>",
                lambda event: self._dispatch_pointer(on_drag_release, event),
                add="+",
            )

    def _bind_select(self, widget: Any) -> None:
        widget.bind("<ButtonRelease-1>", lambda _event: self._select(), add="+")

    def _bind_hover(self, widget: Any) -> None:
        widget.bind("<Enter>", lambda _event: self._set_hovered(True), add="+")
        widget.bind("<Leave>", lambda _event: self._set_hovered(False), add="+")

    def _build_pill_rows(self, pills: list[tuple[str, Any, bool]], *, max_width: int) -> None:
        row: ctk.CTkFrame | None = None
        row_width = 0
        for text, color, is_priority in pills:
            pill_width = max(42, 18 + len(text) * 6)
            if row is None or row_width + pill_width > max_width:
                has_previous_row = row is not None
                row = ctk.CTkFrame(self.metadata_frame, height=1, fg_color="transparent")
                row.pack(fill="x", pady=(3, 0) if has_previous_row else 0)
                row_width = 0
            pill = ctk.CTkLabel(
                row,
                text=text,
                width=pill_width,
                height=21,
                corner_radius=7,
                fg_color=color,
                text_color=self.theme["pill_text_color"],
                font=ctk.CTkFont(size=10, weight="bold"),
            )
            pill.pack(side="left", padx=(0, 5))
            if is_priority:
                self.priority_pill = pill
            else:
                self.tag_pills.append(pill)
            row_width += pill_width + 5

    def _select(self) -> None:
        if self._on_select is not None:
            self._on_select(self)
        self._edit()

    def _edit(self) -> None:
        if self._on_edit is not None:
            self._on_edit(self)

    def _menu(self) -> None:
        if self._on_menu is not None:
            self._on_menu(self)

    def _dispatch_pointer(self, callback: PointerCallback | None, event: Any) -> str:
        if callback is not None:
            callback(self, event)
        return "break"

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.configure(
            border_width=2 if self._selected else 1,
            border_color=(
                self.theme["selected_border_color"]
                if self._selected
                else self.theme["card_border_color"]
            ),
        )

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = bool(hovered)
        if self._dragging:
            return
        self.configure(
            fg_color=(
                self.theme["card_hover_color"]
                if self._hovered
                else self.theme["card_fg_color"]
            )
        )

    def set_dragging(self, dragging: bool) -> None:
        self._dragging = bool(dragging)
        self.configure(
            fg_color=(
                self.theme["dragging_card_fg_color"]
                if dragging
                else (
                    self.theme["card_hover_color"]
                    if self._hovered
                    else self.theme["card_fg_color"]
                )
            )
        )
