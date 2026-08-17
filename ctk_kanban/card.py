"""Small, display-only card widget for the simplified board."""

from __future__ import annotations

from typing import Any, Callable, Mapping

import customtkinter as ctk

CardCallback = Callable[["CTkKanbanCard"], None]
PointerCallback = Callable[["CTkKanbanCard", Any], None]


class CTkKanbanCard(ctk.CTkFrame):
    """Render one card with explicit edit, menu, and drag controls.

    Card content never starts a drag and is never edited in place.  This keeps
    click, edit, and drag gestures independent from one another.
    """

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
            fg_color=theme["card_fg_color"],
            border_color=theme["card_border_color"],
            border_width=1,
        )
        self.card = dict(card)
        self.card_id = self.card["id"]
        self.theme = dict(theme)
        self._on_select = on_select
        self._on_edit = on_edit
        self._on_menu = on_menu
        self._selected = False

        self.grid_columnconfigure(1, weight=1)

        self.drag_handle = ctk.CTkLabel(
            self,
            text="::",
            width=24,
            height=28,
            cursor="fleur" if drag_enabled else "arrow",
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        if drag_enabled:
            self.drag_handle.grid(row=0, column=0, rowspan=2, padx=(8, 2), pady=(8, 4), sticky="n")

        self.title_label = ctk.CTkLabel(
            self,
            text=str(self.card.get("title") or "Untitled"),
            anchor="w",
            justify="left",
            wraplength=max(120, width - 112),
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.title_label.grid(
            row=0,
            column=1,
            padx=(4, 4) if drag_enabled else (10, 4),
            pady=(9, 2),
            sticky="ew",
        )

        self.edit_button = ctk.CTkButton(
            self,
            text="Edit",
            width=42,
            height=26,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self._edit,
        )
        self.edit_button.grid(row=0, column=2, padx=(2, 2), pady=(7, 2))

        self.menu_button = ctk.CTkButton(
            self,
            text="...",
            width=30,
            height=26,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self._menu,
        )
        self.menu_button.grid(row=0, column=3, padx=(0, 7), pady=(7, 2))

        next_row = 1
        description = str(self.card.get("description") or "").strip()
        if description:
            self.description_label = ctk.CTkLabel(
                self,
                text=description,
                anchor="w",
                justify="left",
                wraplength=max(140, width - 60),
                text_color=self.theme["muted_text_color"],
                font=ctk.CTkFont(size=11),
            )
            self.description_label.grid(
                row=next_row,
                column=1,
                columnspan=3,
                padx=(4, 9),
                pady=(0, 5),
                sticky="ew",
            )
            next_row += 1

        priority = str(self.card.get("priority") or "").strip()
        raw_tags = self.card.get("tags") or []
        if isinstance(raw_tags, str):
            tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
        else:
            tags = [str(item).strip() for item in raw_tags if str(item).strip()]
        self.priority_pill: ctk.CTkLabel | None = None
        self.tag_pills: list[ctk.CTkLabel] = []
        if priority or tags:
            self.metadata_frame = ctk.CTkFrame(self, fg_color="transparent")
            self.metadata_frame.grid(
                row=next_row,
                column=1,
                columnspan=3,
                padx=(4, 9),
                pady=(0, 9),
                sticky="ew",
            )
            pills: list[tuple[str, Any, bool]] = []
            if priority:
                color = self.theme[f"priority_{priority.casefold()}_color"]
                pills.append((priority, color, True))
            palette = self.theme["tag_pill_colors"]
            for tag in tags[:4]:
                display = tag if len(tag) <= 18 else f"{tag[:17]}…"
                color_index = sum(ord(character) for character in tag) % len(palette)
                pills.append((f"#{display}", palette[color_index], False))
            self._build_pill_rows(pills, max_width=max(140, width - 60))
        else:
            self.title_label.grid_configure(pady=(9, 9))

        self._bind_select(self)
        self._bind_select(self.title_label)
        if hasattr(self, "description_label"):
            self._bind_select(self.description_label)
        if hasattr(self, "metadata_frame"):
            self._bind_select(self.metadata_frame)
        for pill in [self.priority_pill, *self.tag_pills]:
            if pill is not None:
                self._bind_select(pill)

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

    def _build_pill_rows(self, pills: list[tuple[str, Any, bool]], *, max_width: int) -> None:
        row: ctk.CTkFrame | None = None
        row_width = 0
        for text, color, is_priority in pills:
            pill_width = max(42, 18 + len(text) * 6)
            if row is None or row_width + pill_width > max_width:
                has_previous_row = row is not None
                row = ctk.CTkFrame(self.metadata_frame, fg_color="transparent")
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

    def set_dragging(self, dragging: bool) -> None:
        self.configure(
            fg_color=(
                self.theme["dragging_card_fg_color"]
                if dragging
                else self.theme["card_fg_color"]
            )
        )
