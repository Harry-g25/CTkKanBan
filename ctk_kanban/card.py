"""Compact, schema-driven card widget for the Kanban board."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Callable, Mapping

import customtkinter as ctk

from .fields import format_field_value, normalize_fields

CardCallback = Callable[["CTkKanbanCard"], None]
PointerCallback = Callable[["CTkKanbanCard", Any], None]


class CTkKanbanCard(ctk.CTkFrame):
    """Render one card using schema display roles and handle-only dragging."""

    def __init__(
        self,
        master: Any,
        card: Mapping[str, Any],
        theme: Mapping[str, Any],
        *,
        fields: Sequence[Mapping[str, Any]] | None = None,
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
            border_width=theme["card_border_width"],
            corner_radius=theme["card_corner_radius"],
        )
        self.card = dict(card)
        self.card_id = self.card["id"]
        self.theme = dict(theme)
        self.fields = normalize_fields(fields)
        self._on_select = on_select
        self._on_edit = on_edit
        self._on_menu = on_menu
        self._selected = False
        self._dragging = False
        self._hovered = False
        self.grid_columnconfigure(1, weight=1)

        accent_field, accent_value = self._accent_value()
        strip_color = self._value_color(accent_field, accent_value, self.theme["accent_color"])
        self.priority_strip = ctk.CTkFrame(
            self,
            width=self.theme["card_accent_width"],
            height=1,
            corner_radius=max(1, self.theme["card_accent_width"] // 2),
            fg_color=strip_color,
        )
        self.priority_strip.grid(
            row=0,
            column=0,
            rowspan=100,
            padx=(8, 0),
            pady=10,
            sticky="ns",
        )

        title_field = next(field for field in self.fields if field["card_role"] == "title")
        title = format_field_value(title_field, self.card.get(title_field["key"]), self.card)
        self.title_label = ctk.CTkLabel(
            self,
            text=title or "Untitled",
            anchor="w",
            justify="left",
            wraplength=max(140, width - 104),
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(**self.theme["card_title_font"]),
        )
        self.title_label.grid(row=0, column=1, padx=(12, 4), pady=(11, 3), sticky="ew")

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
            corner_radius=self.theme["control_corner_radius"],
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self._menu,
        )
        if on_menu is not None:
            self.menu_button.grid(row=0, column=3, padx=(0, 8), pady=(8, 2), sticky="n")

        # Kept as a non-gridded compatibility command surface.
        self.edit_button = ctk.CTkButton(self, text="", width=1, height=1, command=self._edit)

        interactive: list[Any] = [self, self.priority_strip, self.title_label]
        next_row = 1
        self.body_labels: list[ctk.CTkLabel] = []
        for field in self._visible_fields("body"):
            value = format_field_value(field, self.card.get(field["key"]), self.card)
            if not value:
                continue
            limit = int(self.theme["card_description_max_chars"])
            if len(value) > limit:
                value = f"{value[: limit - 1].rstrip()}…"
            label = ctk.CTkLabel(
                self,
                text=value,
                anchor="w",
                justify="left",
                wraplength=max(160, width - 48),
                text_color=self.theme["muted_text_color"],
                font=ctk.CTkFont(**self.theme["card_body_font"]),
            )
            label.grid(
                row=next_row,
                column=1,
                columnspan=3,
                padx=(12, 10),
                pady=(1, 7),
                sticky="ew",
            )
            self.body_labels.append(label)
            if field["key"] == "description":
                self.description_label = label
            interactive.append(label)
            next_row += 1

        self.priority_pill: ctk.CTkLabel | None = None
        self.tag_pills: list[ctk.CTkLabel] = []
        self.metadata_pills: list[ctk.CTkLabel] = []
        self.all_pills: list[ctk.CTkLabel] = []
        metadata_fields = [
            *self._visible_fields("badge"),
            *self._visible_fields("tags"),
            *self._visible_fields("metadata"),
        ]
        if any(self._has_display_value(field) for field in metadata_fields):
            self.metadata_frame = ctk.CTkFrame(self, height=1, fg_color="transparent")
            self.metadata_frame.grid(
                row=next_row,
                column=1,
                columnspan=3,
                padx=(12, 10),
                pady=(0, 11),
                sticky="ew",
            )
            pills: list[tuple[str, Any, str]] = []
            for field in self._visible_fields("badge"):
                badge_value = self.card.get(field["key"])
                display = format_field_value(field, badge_value, self.card)
                if display:
                    kind = "priority" if field["key"] == "priority" else "metadata"
                    pills.append((display, self._value_color(field, badge_value), kind))
            palette = self.theme["tag_pill_colors"]
            for field in self._visible_fields("tags"):
                values = self.card.get(field["key"]) or []
                if isinstance(values, str):
                    values = [item.strip() for item in values.split(",") if item.strip()]
                for item in list(values)[: int(self.theme["card_max_visible_tags"])]:
                    display = str(item)
                    if len(display) > 18:
                        display = f"{display[:17]}…"
                    color_index = sum(ord(character) for character in str(item)) % len(palette)
                    pills.append((f"#{display}", palette[color_index], "tag"))
            for field in self._visible_fields("metadata"):
                metadata_value = self.card.get(field["key"])
                display = format_field_value(field, metadata_value, self.card)
                if display:
                    pills.append(
                        (
                            f"{field['label']}: {display}",
                            self._value_color(
                                field, metadata_value, self.theme["count_fg_color"]
                            ),
                            "metadata",
                        )
                    )
            self._build_pill_rows(pills, max_width=max(160, width - 48))
            interactive.append(self.metadata_frame)
            interactive.extend(self.all_pills)
        elif not self.body_labels:
            self.title_label.grid_configure(pady=(11, 11))

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

    def _visible_fields(self, role: str) -> list[Mapping[str, Any]]:
        return [
            field
            for field in self.fields
            if field["show_on_card"] and field["card_role"] == role
        ]

    def _has_display_value(self, field: Mapping[str, Any]) -> bool:
        value = self.card.get(field["key"])
        return value is not None and value != "" and value != [] and value != ()

    def _accent_value(self) -> tuple[Mapping[str, Any] | None, Any]:
        for field in self._visible_fields("badge"):
            value = self.card.get(field["key"])
            if value not in (None, ""):
                return field, value
        return None, None

    def _value_color(
        self,
        field: Mapping[str, Any] | None,
        value: Any,
        fallback: Any | None = None,
    ) -> Any:
        fallback = self.theme["accent_color"] if fallback is None else fallback
        if field is None:
            return fallback
        colors = field.get("colors", {})
        try:
            if value in colors:
                return colors[value]
        except TypeError:
            pass
        if field["key"] == "priority" and value:
            return self.theme.get(f"priority_{str(value).casefold()}_color", fallback)
        return fallback

    def _bind_select(self, widget: Any) -> None:
        widget.bind("<ButtonRelease-1>", lambda _event: self._select(), add="+")

    def _bind_hover(self, widget: Any) -> None:
        widget.bind("<Enter>", lambda _event: self._set_hovered(True), add="+")
        widget.bind("<Leave>", lambda _event: self._set_hovered(False), add="+")

    def _build_pill_rows(self, pills: list[tuple[str, Any, str]], *, max_width: int) -> None:
        row: ctk.CTkFrame | None = None
        row_width = 0
        for text, color, kind in pills:
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
                height=self.theme["pill_height"],
                corner_radius=self.theme["pill_corner_radius"],
                fg_color=color,
                text_color=self.theme["pill_text_color"],
                font=ctk.CTkFont(**self.theme["pill_font"]),
            )
            pill.pack(side="left", padx=(0, 5))
            self.all_pills.append(pill)
            if kind == "priority":
                self.priority_pill = pill
            elif kind == "tag":
                self.tag_pills.append(pill)
            else:
                self.metadata_pills.append(pill)
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
            border_width=(
                self.theme["card_selected_border_width"]
                if self._selected
                else self.theme["card_border_width"]
            ),
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
