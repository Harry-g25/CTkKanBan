"""Visual representation of an individual Kanban card."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from .utils import display_value, format_temporal, iter_widget_tree
from .widgets import Tooltip


class CTkKanbanCard(ctk.CTkFrame):
    """Render a card and translate pointer gestures into board callbacks.

    The board remains responsible for mutating data. This class owns only the
    visual state and low-level mouse bindings for one card.
    """

    def __init__(
        self,
        master: Any,
        card_data: dict[str, Any],
        fields: list[dict[str, Any]],
        theme: dict[str, Any],
        *,
        card_mode: str = "detailed",
        priority_colors: dict[str, str] | None = None,
        tag_colors: dict[str, str] | None = None,
        renderer: Callable[[Any, dict[str, Any], list[dict[str, Any]], dict[str, Any]], None] | None = None,
        on_press: Callable[["CTkKanbanCard", Any], None] | None = None,
        on_motion: Callable[["CTkKanbanCard", Any], None] | None = None,
        on_release: Callable[["CTkKanbanCard", Any], None] | None = None,
        on_double_click: Callable[["CTkKanbanCard", Any], None] | None = None,
        on_right_click: Callable[["CTkKanbanCard", Any], None] | None = None,
        hover_enabled: bool = True,
        card_width: int = 280,
        show_drag_handle: bool = True,
        density: str = "comfortable",
        max_visible_tags: int = 6,
        tags_per_row: int = 3,
        timezone_info: Any = None,
        locale_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", theme["card_fg_color"])
        kwargs.setdefault("border_color", theme["card_border_color"])
        kwargs.setdefault("border_width", theme.get("card_border_width", theme["border_width"]))
        kwargs.setdefault("corner_radius", theme["card_corner_radius"])
        kwargs.setdefault("height", theme["card_min_height"])
        super().__init__(master, **kwargs)

        self.card_data = card_data
        self.card_id = card_data["id"]
        self.fields = fields
        self.theme = theme
        self.card_mode = card_mode
        self.priority_colors = priority_colors or {}
        self.tag_colors = tag_colors or {}
        self.renderer = renderer
        self.on_press = on_press
        self.on_motion = on_motion
        self.on_release = on_release
        self.on_double_click = on_double_click
        self.on_right_click = on_right_click
        self.hover_enabled = hover_enabled
        self.card_width = card_width
        self.show_drag_handle = show_drag_handle
        self.density = density
        self.max_visible_tags = max_visible_tags
        self.tags_per_row = max(1, tags_per_row)
        self.timezone_info = timezone_info
        self.locale_name = locale_name
        self.selected = False
        self.dimmed = False
        self.dragging = False
        self.search_matched = False
        self._hovered = False
        self._wrap_labels: list[ctk.CTkLabel] = []

        self.grid_columnconfigure(0, weight=1)
        self._build_card()
        self._text_labels = [
            (widget, widget.cget("text_color"))
            for widget in iter_widget_tree(self)
            if isinstance(widget, ctk.CTkLabel)
        ]
        self._labels_dimmed = False
        self._bind_pointer_events()
        self.configure(cursor="hand2")

    def _build_card(self) -> None:
        """Build either custom content or the default field-driven layout."""

        if self.renderer is not None:
            self.renderer(self, self.card_data, self.fields, self.theme)
            return

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        density_padding = {"compact": 8, "comfortable": 11, "spacious": 14}.get(self.density, 11)
        priority = self.card_data.get("priority")
        accent_color = self.priority_colors.get(
            str(priority),
            self.theme.get("card_accent_default_color", self.theme["card_border_color"]),
        )
        self.accent_bar = ctk.CTkFrame(
            self,
            width=int(self.theme.get("card_accent_width", 4)),
            corner_radius=4,
            fg_color=accent_color,
        )
        self.accent_bar.grid(row=0, column=0, rowspan=50, sticky="ns", padx=(7, 0), pady=8)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=(10, 8), pady=(density_padding, 4))
        header.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(
            header,
            text=str(self.card_data.get("title", "Untitled card")),
            anchor="w",
            justify="left",
            wraplength=max(100, self.card_width - 110),
            font=self.theme.get("card_title_font") or ctk.CTkFont(size=15, weight="bold"),
            text_color=self.theme.get("card_title_text_color", self.theme["text_color"]),
        )
        self.title_label = title
        title.grid(row=0, column=0, sticky="ew")
        if priority not in (None, ""):
            priority_color = self.priority_colors.get(str(priority), self.theme["tag_fg_color"])
            self.priority_badge = ctk.CTkLabel(
                header,
                text=str(priority).upper(),
                height=22,
                corner_radius=7,
                fg_color=priority_color,
                text_color=self.theme.get("badge_text_color", "#FFFFFF"),
                font=self.theme.get("badge_font") or ctk.CTkFont(size=9, weight="bold"),
            )
            self.priority_badge.grid(row=0, column=1, padx=(8, 2))
        if self.show_drag_handle:
            self.drag_handle = ctk.CTkLabel(
                header,
                text="::::",
                width=28,
                text_color=self.theme.get("card_drag_handle_color", self.theme["muted_text_color"]),
                cursor="fleur",
                font=ctk.CTkFont(size=10, weight="bold"),
            )
            self.drag_handle.grid(row=0, column=2, padx=(4, 0))
            Tooltip(self.drag_handle, "Drag to move card")

        visible_fields = [
            field
            for field in self.fields
            if field.get("show_on_card")
            and field["key"] != "title"
            and field.get("type") != "hidden"
            and self.card_data.get(field["key"]) not in (None, "", [])
        ]
        description_fields = [
            field
            for field in visible_fields
            if field.get("type") == "textarea" or field["key"] == "description"
        ]
        badge_fields = [
            field
            for field in visible_fields
            if field.get("type") in {"tag", "tags", "badge"} and field["key"] != "priority"
        ]
        metadata_fields = [
            field
            for field in visible_fields
            if field not in description_fields and field not in badge_fields and field["key"] != "priority"
        ]
        if self.card_mode == "compact":
            description_fields = description_fields[:1]
            metadata_fields = metadata_fields[:2]
            badge_fields = badge_fields[:1]

        max_description = int(self.theme.get("card_description_max_chars", 150))
        if self.card_mode == "compact":
            max_description = min(max_description, 82)
        row = 1
        for field in description_fields:
            value = self.card_data.get(field["key"])
            text = display_value(value)
            if len(text) > max_description:
                text = f"{text[: max_description - 3].rstrip()}..."
            label = ctk.CTkLabel(
                self,
                text=text,
                anchor="w",
                justify="left",
                wraplength=max(100, self.card_width - 42),
                text_color=self.theme.get("card_body_text_color", self.theme["muted_text_color"]),
                font=self.theme.get("card_body_font") or ctk.CTkFont(size=12),
            )
            label.grid(row=row, column=1, sticky="ew", padx=(10, 12), pady=(1, 5))
            self._wrap_labels.append(label)
            row += 1

        if metadata_fields:
            metadata = ctk.CTkFrame(self, fg_color="transparent")
            metadata.grid(row=row, column=1, sticky="ew", padx=(8, 10), pady=(3, 4))
            metadata.grid_columnconfigure((0, 1), weight=1, uniform="card_meta")
            for index, field in enumerate(metadata_fields):
                value = self.card_data.get(field["key"])
                field_type = field.get("type", "text")
                shown_value = (
                    format_temporal(
                        value,
                        field_type=field_type,
                        timezone_info=self.timezone_info,
                        locale_name=self.locale_name,
                    )
                    if field_type in {"date", "datetime"}
                    else display_value(value)
                )
                tile = ctk.CTkFrame(
                    metadata,
                    fg_color=self.theme.get("card_metadata_fg_color", "transparent"),
                    corner_radius=8,
                )
                tile.grid(
                    row=index // 2,
                    column=index % 2,
                    sticky="ew",
                    padx=2,
                    pady=2,
                )
                ctk.CTkLabel(
                    tile,
                    text=str(field["label"]).split(" (", 1)[0].upper(),
                    anchor="w",
                    text_color=self.theme.get(
                        "card_metadata_label_text_color",
                        self.theme["muted_text_color"],
                    ),
                    font=ctk.CTkFont(size=9, weight="bold"),
                ).pack(fill="x", padx=8, pady=(5, 0))
                value_label = ctk.CTkLabel(
                    tile,
                    text=shown_value,
                    anchor="w",
                    justify="left",
                    wraplength=max(70, (self.card_width - 64) // 2),
                    text_color=self.theme.get("card_metadata_text_color", self.theme["text_color"]),
                    font=self.theme.get("card_metadata_font") or ctk.CTkFont(size=11),
                )
                value_label.pack(fill="x", padx=8, pady=(0, 5))
                self._wrap_labels.append(value_label)
            row += 1

        for field in badge_fields:
            self._build_badges(row, field, self.card_data.get(field["key"]))
            row += 1

        spacer = ctk.CTkFrame(self, height=max(4, density_padding // 2), fg_color="transparent")
        spacer.grid(row=row, column=1)

    def _build_badges(self, row: int, field: dict[str, Any], value: Any) -> None:
        """Render tag, tags, and badge values as compact chips."""

        values = list(value) if isinstance(value, (list, tuple, set)) else [value]
        hidden_count = max(0, len(values) - self.max_visible_tags)
        values = values[: self.max_visible_tags]
        if hidden_count:
            values.append(f"+{hidden_count} more")
        holder = ctk.CTkFrame(self, fg_color="transparent")
        holder.grid(row=row, column=1, sticky="w", padx=(8, 10), pady=(3, 4))
        for index, item in enumerate(values):
            text = str(item)
            color = self.tag_colors.get(text, self.theme["tag_fg_color"])
            if field["key"] == "priority" or field.get("type") == "badge":
                color = self.priority_colors.get(text, color)
            chip = ctk.CTkLabel(
                holder,
                text=text,
                height=22,
                corner_radius=8,
                fg_color=color,
                text_color=(
                    self.theme["tag_text_color"]
                    if isinstance(color, tuple)
                    else self.theme.get("badge_text_color", "#FFFFFF")
                ),
                font=self.theme.get("badge_font") or ctk.CTkFont(size=10, weight="bold"),
            )
            chip.grid(row=index // self.tags_per_row, column=index % self.tags_per_row, padx=2, pady=1)
            if text.startswith("+") and hidden_count:
                Tooltip(chip, ", ".join(str(item) for item in list(value)[self.max_visible_tags :]))

    def _bind_pointer_events(self) -> None:
        """Bind the same gestures to card descendants for natural clicking."""

        for widget in iter_widget_tree(self):
            widget.bind(
                "<ButtonPress-1>",
                lambda event, card=self: self._dispatch(self.on_press, card, event),
                add="+",
            )
            widget.bind("<B1-Motion>", lambda event, card=self: self._dispatch(self.on_motion, card, event), add="+")
            widget.bind(
                "<ButtonRelease-1>",
                lambda event, card=self: self._dispatch(self.on_release, card, event),
                add="+",
            )
            widget.bind(
                "<Double-Button-1>",
                lambda event, card=self: self._dispatch(self.on_double_click, card, event),
                add="+",
            )
            widget.bind(
                "<Button-3>",
                lambda event, card=self: self._dispatch(self.on_right_click, card, event),
                add="+",
            )
            widget.bind(
                "<Button-2>",
                lambda event, card=self: self._dispatch(self.on_right_click, card, event),
                add="+",
            )
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")

    @staticmethod
    def _dispatch(callback: Callable[..., None] | None, *args: Any) -> None:
        if callback is not None:
            callback(*args)

    def _on_enter(self, _event: Any) -> None:
        if self._hovered or self.dragging:
            return
        self._hovered = True
        if self.hover_enabled and not self.selected and not self.dimmed:
            self.configure(fg_color=self.theme["card_hover_color"])

    def _on_leave(self, event: Any) -> None:
        if self.dragging or not self._hovered:
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        while target is not None:
            if target is self:
                return
            target = getattr(target, "master", None)
        self._hovered = False
        self._apply_visual_state()

    def _apply_visual_state(self) -> None:
        if self.selected:
            self.configure(
                fg_color=self.theme["card_selected_color"],
                border_color=self.theme["card_selected_border_color"],
                border_width=max(2, int(self.theme.get("card_border_width", self.theme["border_width"]))),
            )
        else:
            self.configure(
                fg_color=self.theme["card_fg_color"],
                border_color=(
                    self.theme.get("card_search_border_color", self.theme["card_border_color"])
                    if self.search_matched
                    else self.theme["card_border_color"]
                ),
                border_width=(
                    max(2, int(self.theme.get("card_border_width", self.theme["border_width"])))
                    if self.search_matched
                    else self.theme.get("card_border_width", self.theme["border_width"])
                ),
            )
        if self.dimmed and not self._labels_dimmed:
            self.configure(border_color=self.theme["column_border_color"])
            for label, _text_color in self._text_labels:
                try:
                    label.configure(text_color=self.theme["overlay_text_color"])
                except (ValueError, TypeError):
                    pass
            self._labels_dimmed = True
        elif not self.dimmed and self._labels_dimmed:
            for label, text_color in self._text_labels:
                try:
                    label.configure(text_color=text_color)
                except (ValueError, TypeError):
                    pass
            self._labels_dimmed = False

    def set_selected(self, selected: bool) -> None:
        """Set the single-selection visual state."""

        if self.selected == selected:
            return
        self.selected = selected
        self._apply_visual_state()

    def set_dimmed(self, dimmed: bool) -> None:
        """Visually de-emphasize a card filtered out in ``dim`` mode."""

        if self.dimmed == dimmed:
            return
        self.dimmed = dimmed
        self._apply_visual_state()

    def set_search_match(self, matched: bool) -> None:
        """Emphasize cards matching an active search query."""

        if self.search_matched == matched:
            return
        self.search_matched = matched
        self._apply_visual_state()

    def set_dragging(self, dragging: bool) -> None:
        """Suppress hover redraws while the card owns the pointer grab."""

        if self.dragging == dragging:
            return
        self.dragging = dragging
        if not dragging:
            self._hovered = False
            self._apply_visual_state()

    def reflow(self, width: int) -> None:
        """Update wrapping after a responsive or user-driven column resize."""

        self.card_width = width
        if hasattr(self, "title_label"):
            self.title_label.configure(wraplength=max(100, width - 110))
        for label in self._wrap_labels:
            label.configure(wraplength=max(70, width - 42))
