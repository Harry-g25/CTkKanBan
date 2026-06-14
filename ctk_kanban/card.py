"""Visual representation of an individual Kanban card."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from .utils import display_value, iter_widget_tree


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
        self.selected = False
        self.dimmed = False
        self.dragging = False
        self._hovered = False

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

        title = ctk.CTkLabel(
            self,
            text=str(self.card_data.get("title", "Untitled card")),
            anchor="w",
            justify="left",
            wraplength=230,
            font=self.theme.get("card_title_font") or ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme.get("card_title_text_color", self.theme["text_color"]),
        )
        title.grid(row=0, column=0, sticky="ew", padx=11, pady=(9, 5))

        visible_fields = [
            field
            for field in self.fields
            if field.get("show_on_card")
            and field["key"] != "title"
            and field.get("type") != "hidden"
            and self.card_data.get(field["key"]) not in (None, "", [])
        ]
        if self.card_mode == "compact":
            visible_fields = visible_fields[:2]

        row = 1
        for field in visible_fields:
            value = self.card_data.get(field["key"])
            field_type = field.get("type", "text")
            if field_type in {"tag", "tags", "badge"} or field["key"] == "priority":
                self._build_badges(row, field, value)
            elif field_type == "textarea":
                text = display_value(value)
                if self.card_mode == "compact" and len(text) > 80:
                    text = f"{text[:77]}..."
                label = ctk.CTkLabel(
                    self,
                    text=text,
                    anchor="w",
                    justify="left",
                    wraplength=230,
                    text_color=self.theme.get("card_body_text_color", self.theme["muted_text_color"]),
                    font=self.theme.get("card_body_font") or ctk.CTkFont(size=12),
                )
                label.grid(row=row, column=0, sticky="ew", padx=11, pady=2)
            else:
                label = ctk.CTkLabel(
                    self,
                    text=f"{field['label']}: {display_value(value)}",
                    anchor="w",
                    justify="left",
                    wraplength=230,
                    text_color=self.theme.get("card_metadata_text_color", self.theme["muted_text_color"]),
                    font=self.theme.get("card_metadata_font") or ctk.CTkFont(size=11),
                )
                label.grid(row=row, column=0, sticky="ew", padx=11, pady=2)
            row += 1

        spacer = ctk.CTkFrame(self, height=5, fg_color="transparent")
        spacer.grid(row=row, column=0)

    def _build_badges(self, row: int, field: dict[str, Any], value: Any) -> None:
        """Render tag, tags, and badge values as compact chips."""

        values = value if isinstance(value, (list, tuple, set)) else [value]
        holder = ctk.CTkFrame(self, fg_color="transparent")
        holder.grid(row=row, column=0, sticky="w", padx=9, pady=3)
        for index, item in enumerate(values):
            text = str(item)
            color = self.tag_colors.get(text, self.theme["tag_fg_color"])
            if field["key"] == "priority" or field.get("type") == "badge":
                color = self.priority_colors.get(text, color)
            chip = ctk.CTkLabel(
                holder,
                text=text,
                height=20,
                corner_radius=7,
                fg_color=color,
                text_color=(
                    self.theme["tag_text_color"]
                    if isinstance(color, tuple)
                    else self.theme.get("badge_text_color", "#FFFFFF")
                ),
                font=self.theme.get("badge_font") or ctk.CTkFont(size=10, weight="bold"),
            )
            chip.grid(row=0, column=index, padx=2)

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
                border_color=self.theme["card_border_color"],
                border_width=self.theme.get("card_border_width", self.theme["border_width"]),
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

    def set_dragging(self, dragging: bool) -> None:
        """Suppress hover redraws while the card owns the pointer grab."""

        if self.dragging == dragging:
            return
        self.dragging = dragging
        if not dragging:
            self._hovered = False
            self._apply_visual_state()
