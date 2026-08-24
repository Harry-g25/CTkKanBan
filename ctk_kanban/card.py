"""Fast hybrid-rendered card widget for the Kanban board."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from typing import Any, Callable, Mapping, cast

import customtkinter as ctk

from .fields import FieldInput, format_field_value, normalize_fields

CardCallback = Callable[["CTkKanbanCard"], None]
PointerCallback = Callable[["CTkKanbanCard", Any], None]


class _CanvasValue:
    """Compatibility view over text or pill values rendered on a card."""

    __slots__ = ("_canvas", "_fg_color", "_label", "_text", "_text_color")

    def __init__(
        self,
        canvas: tk.Canvas,
        *,
        text: str,
        fg_color: Any,
        text_color: Any,
    ) -> None:
        self._canvas = canvas
        self._label = canvas
        self._text = text
        self._fg_color = fg_color
        self._text_color = text_color

    def cget(self, key: str) -> Any:
        if key == "text":
            return self._text
        if key == "fg_color":
            return self._fg_color
        if key == "text_color":
            return self._text_color
        if key in {"background", "bg"}:
            return self._canvas.cget("background")
        raise tk.TclError(f"unknown option {key!r}")


class CTkKanbanCard(ctk.CTkFrame):
    """Render one rich card with retained text and native visual controls.

    Static text stays inexpensive on one canvas. Native CustomTkinter widgets
    supply anti-aliased action buttons and the accent strip, while a reusable
    label pool does the same for pills without rebuilding their widget tree.
    """

    def __init__(
        self,
        master: Any,
        card: Mapping[str, Any],
        theme: Mapping[str, Any],
        *,
        fields: Sequence[FieldInput] | None = None,
        on_select: CardCallback | None = None,
        on_edit: CardCallback | None = None,
        on_menu: CardCallback | None = None,
        on_drag_press: PointerCallback | None = None,
        on_drag_motion: PointerCallback | None = None,
        on_drag_release: PointerCallback | None = None,
        drag_enabled: bool = True,
        width: int = 264,
        _normalized_fields: bool = False,
        _font_cache: dict[str, ctk.CTkFont] | None = None,
        _shared_theme: bool = False,
        _initial_content_width: int | None = None,
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
        self.theme = theme if _shared_theme else dict(theme)
        self._logical_width = width
        self.fields: tuple[Mapping[str, Any], ...] = (
            tuple(cast(Sequence[Mapping[str, Any]], fields or ()))
            if _normalized_fields
            else normalize_fields(fields)
        )
        self._fields_by_role: dict[str, tuple[Mapping[str, Any], ...]] = {
            role: tuple(
                field
                for field in self.fields
                if field["show_on_card"] and field["card_role"] == role
            )
            for role in ("title", "body", "badge", "tags", "metadata")
        }
        self._font_cache = {} if _font_cache is None else _font_cache
        self._on_select = on_select
        self._on_edit = on_edit
        self._on_menu = on_menu
        self._on_drag_press = on_drag_press
        self._on_drag_motion = on_drag_motion
        self._on_drag_release = on_drag_release
        self._selected = False
        self._dragging = False
        self._hovered = False
        self._handle_pressed = False
        self._hover_leave_after_id: str | None = None
        self._drag_enabled = bool(drag_enabled)
        self._canvas_cursor = ""
        border = self._scale(self.theme["card_border_width"])
        scaled_width = round(float(self._apply_widget_scaling(width)))
        self._content_width = max(
            self._scale(120),
            scaled_width - border * 2
            if _initial_content_width is None
            else int(_initial_content_width),
        )
        # The outer card may expand with a fill-column layout, but readable
        # content should not collapse into one dense strip. Keep the original
        # design measure for text and pill wrapping while allowing the canvas
        # and action controls to use the full displayed width.
        self._update_readable_widths()
        self._pill_row_count = 0
        self._rendered_height = 1
        self._interaction_item: int | None = None
        self._interaction_color = ""
        self._handle_bounds = (0, 0, 0, 0)
        self._menu_bounds = (0, 0, 0, 0)
        self._context_menu_position: tuple[int, int] | None = None
        self._pill_widgets: list[ctk.CTkLabel] = []

        self._content_canvas = tk.Canvas(
            self,
            width=self._content_width,
            height=1,
            borderwidth=0,
            highlightthickness=0,
            background=self._apply_appearance_mode(self.theme["card_fg_color"]),
        )
        self._content_canvas.grid(row=0, column=0, padx=border, pady=border, sticky="nsew")
        self.grid_columnconfigure(0, weight=1)

        surface_color = self._apply_appearance_mode(self.theme["card_fg_color"])
        self.priority_strip = ctk.CTkFrame(
            self._content_canvas,
            width=self.theme["card_accent_width"],
            height=1,
            corner_radius=2,
            bg_color=surface_color,
            fg_color=self.theme["accent_color"],
            cursor="hand2" if self._on_edit is not None else "arrow",
        )
        self.drag_handle = ctk.CTkButton(
            self._content_canvas,
            text="⠇",
            width=self.theme["card_action_size"],
            height=self.theme["card_action_size"],
            corner_radius=self.theme["pill_corner_radius"],
            border_width=0,
            border_spacing=0,
            bg_color=surface_color,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["muted_text_color"],
            font=self._font("card_action_font"),
            cursor="fleur",
        )
        self.menu_button = ctk.CTkButton(
            self._content_canvas,
            text="⋯",
            width=self.theme["card_action_size"],
            height=self.theme["card_action_size"],
            corner_radius=self.theme["pill_corner_radius"],
            border_width=0,
            border_spacing=0,
            bg_color=surface_color,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            font=self._font("card_action_font"),
            command=self._menu,
            cursor="hand2",
        )
        self._bind_overlay_hover(self.priority_strip)
        self._bind_overlay_hover(self.drag_handle)
        self._bind_overlay_hover(self.menu_button)
        for target in (self.priority_strip, *self.priority_strip.winfo_children()):
            target.bind("<ButtonRelease-1>", self._pill_released, add="+")
        self.drag_handle.bind("<ButtonPress-1>", self._drag_press, add="+")
        self.drag_handle.bind("<B1-Motion>", self._drag_motion, add="+")
        self.drag_handle.bind("<ButtonRelease-1>", self._drag_release, add="+")

        # Compatibility aliases retain their historical native widget shapes.
        self.metadata_frame = self._content_canvas
        self.body_labels: list[_CanvasValue] = []
        self.description_label: _CanvasValue | None = None
        self.priority_pill: _CanvasValue | None = None
        self.tag_pills: list[_CanvasValue] = []
        self.metadata_pills: list[_CanvasValue] = []
        self.all_pills: list[_CanvasValue] = []
        self.title_label = _CanvasValue(
            self._content_canvas,
            text="",
            fg_color=self.theme["card_fg_color"],
            text_color=self.theme["text_color"],
        )
        self._edit_button: ctk.CTkButton | None = None

        self._render()
        self._content_canvas.bind("<Configure>", self._canvas_configured, add="+")
        self._content_canvas.bind("<Enter>", self._hover_enter, add="+")
        self._content_canvas.bind("<Leave>", self._hover_leave, add="+")
        self._content_canvas.bind("<Motion>", self._canvas_motion, add="+")
        self._content_canvas.bind("<ButtonPress-1>", self._canvas_press, add="+")
        self._content_canvas.bind("<B1-Motion>", self._canvas_drag, add="+")
        self._content_canvas.bind("<ButtonRelease-1>", self._canvas_release, add="+")
        if self._on_menu is not None:
            self._content_canvas.bind("<Button-3>", self._context_menu, add="+")
            self.bind("<Button-3>", self._context_menu, add="+")
        self.bind("<Enter>", self._hover_enter, add="+")
        self.bind("<Leave>", self._hover_leave, add="+")

    def _scale(self, value: Any) -> int:
        return round(float(self._apply_widget_scaling(value)))

    def _update_readable_widths(self) -> None:
        self._preferred_text_width = max(
            self._scale(100),
            self._scale(self._logical_width - 50),
        )
        self._preferred_title_width = max(
            self._scale(80),
            self._scale(self._logical_width - 104),
        )
        self._text_width = min(
            self._preferred_text_width,
            max(self._scale(100), self._content_width - self._scale(50)),
        )

    def _canvas_configured(self, event: tk.Event[Any]) -> None:
        """Reflow retained items when a fill-column card changes width."""

        width = max(self._scale(120), int(event.width))
        if width == self._content_width and self._interaction_item is not None:
            return
        self._content_width = width
        self._update_readable_widths()
        self._render()

    def _font(self, key: str, **fallback: Any) -> ctk.CTkFont:
        font = self._font_cache.get(key)
        if font is None:
            font = ctk.CTkFont(**self.theme.get(key, fallback))
            self._font_cache[key] = font
        return font

    def _visible_fields(self, role: str) -> tuple[Mapping[str, Any], ...]:
        return self._fields_by_role.get(role, ())

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

    def _pill_specs(self) -> list[tuple[str, Any, str]]:
        pills: list[tuple[str, Any, str]] = []
        for field in self._visible_fields("badge"):
            value = self.card.get(field["key"])
            display = format_field_value(field, value, self.card)
            if display:
                kind = "priority" if field["key"] == "priority" else "metadata"
                pills.append((display, self._value_color(field, value), kind))
        palette = self.theme["tag_pill_colors"]
        for field in self._visible_fields("tags"):
            values = self.card.get(field["key"]) or []
            if isinstance(values, str):
                values = [item.strip() for item in values.split(",") if item.strip()]
            for item in list(values)[: int(self.theme["card_max_visible_tags"])]:
                display = str(item)
                if len(display) > 18:
                    display = f"{display[:17]}…"
                color_index = sum(map(ord, str(item))) % len(palette)
                pills.append((f"#{display}", palette[color_index], "tag"))
        for field in self._visible_fields("metadata"):
            value = self.card.get(field["key"])
            display = format_field_value(field, value, self.card)
            if display:
                pills.append(
                    (
                        f"{field['label']}: {display}",
                        self._value_color(
                            field,
                            value,
                            self.theme["card_metadata_fg_color"],
                        ),
                        "metadata",
                    )
                )
        return pills

    def _bind_overlay_hover(self, widget: Any) -> None:
        targets = (
            (widget,)
            if isinstance(widget, (ctk.CTkButton, ctk.CTkLabel))
            else (widget, *widget.winfo_children())
        )
        for target in targets:
            target.bind("<Enter>", self._hover_enter, add="+")
            target.bind("<Leave>", self._hover_leave, add="+")
            if self._on_menu is not None:
                target.bind("<Button-3>", self._context_menu, add="+")

    def _draw_pill(
        self,
        index: int,
        x: int,
        y: int,
        width: int,
        text: str,
        color: Any,
        *,
        text_color: Any,
    ) -> None:
        if index == len(self._pill_widgets):
            widget = ctk.CTkLabel(
                self._content_canvas,
                text="",
                cursor="hand2",
            )
            self._bind_overlay_hover(widget)
            widget.bind("<ButtonRelease-1>", self._pill_released, add="+")
            for target in widget.winfo_children():
                try:
                    target.configure(cursor="hand2")
                except tk.TclError:
                    pass
            self._pill_widgets.append(widget)
        else:
            widget = self._pill_widgets[index]
        widget.configure(
            width=round(float(self._reverse_widget_scaling(width))),
            height=self.theme["pill_height"],
            corner_radius=self.theme["pill_corner_radius"],
            bg_color=self._surface_color(),
            fg_color=color,
            text_color=text_color,
            text=text,
            font=self._font("pill_font"),
        )
        widget.place(
            x=self._reverse_widget_scaling(x),
            y=self._reverse_widget_scaling(y),
        )
        widget.lift()

    def _pill_released(self, _event: Any = None) -> str:
        self._select()
        return "break"

    def _surface_color(self) -> str:
        token = "dragging_card_fg_color" if self._dragging else "card_fg_color"
        return self._apply_appearance_mode(self.theme[token])

    def _sync_surface_color(self) -> None:
        color = self._surface_color()
        self._content_canvas.configure(background=color)
        for widget in (self.priority_strip, self.drag_handle, self.menu_button):
            if widget.winfo_manager():
                widget.configure(bg_color=color)
        for widget in self._pill_widgets:
            if widget.winfo_manager():
                widget.configure(bg_color=color)

    def _render(self) -> None:
        """Redraw card content without creating or destroying Tk widgets."""

        canvas = self._content_canvas
        background = self._surface_color()
        canvas.configure(background=background)
        canvas.delete("all")
        self.priority_strip.place_forget()
        self.drag_handle.place_forget()
        self.menu_button.place_forget()
        for widget in self._pill_widgets:
            widget.place_forget()
        self.body_labels = []
        self.description_label = None
        self.priority_pill = None
        self.tag_pills = []
        self.metadata_pills = []
        self.all_pills = []

        left = self._scale(self.theme["card_padding_x"])
        top = self._scale(self.theme["card_padding_y"])
        content_gap = self._scale(self.theme["card_content_gap"])
        action_size = self._scale(self.theme["card_action_size"])
        action_margin = self._scale(self.theme["card_action_margin"])
        action_count = int(self._drag_enabled) + int(self._on_menu is not None)
        right = self._content_width - action_margin
        if action_count:
            right -= action_count * action_size + content_gap
        title_field = self._visible_fields("title")[0]
        title = format_field_value(
            title_field,
            self.card.get(title_field["key"]),
            self.card,
        ) or "Untitled"
        title_item = canvas.create_text(
            left,
            top,
            text=title,
            anchor="nw",
            justify="left",
            width=min(self._preferred_title_width, max(self._scale(80), right - left)),
            fill=self._apply_appearance_mode(self.theme["text_color"]),
            font=self._apply_font_scaling(self._font("card_title_font")),
            tags=("card_title",),
        )
        self.title_label = _CanvasValue(
            canvas,
            text=title,
            fg_color=self.theme["card_fg_color"],
            text_color=self.theme["text_color"],
        )
        bounds = canvas.bbox(title_item)
        y = (bounds[3] if bounds is not None else top + self._scale(18)) + content_gap

        body_font = self._font("card_body_font")
        body_color = self._apply_appearance_mode(self.theme["muted_text_color"])
        for field in self._visible_fields("body"):
            value = format_field_value(field, self.card.get(field["key"]), self.card)
            if not value:
                continue
            limit = int(self.theme["card_description_max_chars"])
            if len(value) > limit:
                value = f"{value[: limit - 1].rstrip()}…"
            item = canvas.create_text(
                left,
                y,
                text=value,
                anchor="nw",
                justify="left",
                width=self._text_width,
                fill=body_color,
                font=self._apply_font_scaling(body_font),
            )
            label = _CanvasValue(
                canvas,
                text=value,
                fg_color=self.theme["card_fg_color"],
                text_color=self.theme["muted_text_color"],
            )
            self.body_labels.append(label)
            if field["key"] == "description":
                self.description_label = label
            bounds = canvas.bbox(item)
            if bounds is not None:
                y = bounds[3] + content_gap

        pill_specs = self._pill_specs()
        self._pill_row_count = 0
        if pill_specs:
            self._pill_row_count = 1
            x = left
            pill_height = self._scale(self.theme["pill_height"])
            pill_padding_x = self._scale(self.theme["pill_padding_x"])
            pill_gap = self._scale(self.theme["pill_gap"])
            pill_row_gap = self._scale(self.theme["pill_row_gap"])
            pill_font = self._font("pill_font")
            for index, (text, color, kind) in enumerate(pill_specs):
                pill_width = min(
                    self._text_width,
                    max(
                        self._scale(46),
                        self._scale(pill_font.measure(text)) + pill_padding_x * 2,
                    ),
                )
                if x > left and x + pill_width > left + self._text_width:
                    x = left
                    y += pill_height + pill_row_gap
                    self._pill_row_count += 1
                text_color = (
                    self.theme["text_color"]
                    if kind == "metadata"
                    else self.theme["pill_text_color"]
                )
                self._draw_pill(
                    index,
                    x,
                    y,
                    pill_width,
                    text,
                    color,
                    text_color=text_color,
                )
                pill = _CanvasValue(
                    canvas,
                    text=text,
                    fg_color=color,
                    text_color=text_color,
                )
                self.all_pills.append(pill)
                if kind == "priority":
                    self.priority_pill = pill
                elif kind == "tag":
                    self.tag_pills.append(pill)
                else:
                    self.metadata_pills.append(pill)
                x += pill_width + pill_gap
            y += pill_height

        vertical_padding = self._scale(self.theme["card_padding_y"])
        height = max(self._scale(52), y + vertical_padding)
        self._rendered_height = height
        accent_field, accent_value = self._accent_value()
        accent_color = self._apply_appearance_mode(
            self._value_color(accent_field, accent_value, self.theme["accent_color"])
        )
        accent_height = max(self._scale(8), height - vertical_padding * 2)
        self.priority_strip.configure(
            width=self.theme["card_accent_width"],
            height=round(float(self._reverse_widget_scaling(accent_height))),
            corner_radius=2,
            bg_color=background,
            fg_color=accent_color,
        )
        self.priority_strip.place(
            x=self._reverse_widget_scaling(self._scale(7)),
            y=self._reverse_widget_scaling(vertical_padding),
        )
        self.priority_strip.lift()

        action_top = max(self._scale(6), top - self._scale(6))
        action_right = self._content_width - action_margin
        self._handle_bounds = (0, 0, 0, 0)
        self._menu_bounds = (0, 0, 0, 0)
        if self._on_menu is not None:
            menu_left = action_right - action_size
            self._menu_bounds = (
                menu_left,
                action_top,
                action_right,
                action_top + action_size,
            )
            self.menu_button.configure(
                width=self.theme["card_action_size"],
                height=self.theme["card_action_size"],
                corner_radius=self.theme["pill_corner_radius"],
                bg_color=background,
            )
            self.menu_button.place(
                x=self._reverse_widget_scaling(menu_left),
                y=self._reverse_widget_scaling(action_top),
            )
            self.menu_button.lift()
            action_right = menu_left
        if self._drag_enabled:
            handle_left = action_right - action_size
            self._handle_bounds = (
                handle_left,
                action_top,
                action_right,
                action_top + action_size,
            )
            self.drag_handle.configure(
                width=self.theme["card_action_size"],
                height=self.theme["card_action_size"],
                corner_radius=self.theme["pill_corner_radius"],
                bg_color=background,
            )
            self.drag_handle.place(
                x=self._reverse_widget_scaling(handle_left),
                y=self._reverse_widget_scaling(action_top),
            )
            self.drag_handle.lift()

        self._interaction_color = self._apply_appearance_mode(
            self.theme["selected_border_color"]
        )
        self._interaction_item = canvas.create_line(
            self._scale(9),
            self._scale(4),
            self._content_width - self._scale(9),
            self._scale(4),
            width=max(1, self._scale(2)),
            capstyle="round",
            fill=self._interaction_color,
            state="hidden",
        )
        canvas.configure(height=height)
        tk.Misc.lower(self._canvas)
        self._sync_interaction_indicator()

    def _set_canvas_cursor(self, cursor: str) -> None:
        if cursor == self._canvas_cursor:
            return
        self._canvas_cursor = cursor
        self._content_canvas.configure(cursor=cursor)

    def _canvas_motion(self, _event: tk.Event[Any]) -> None:
        self._set_canvas_cursor("hand2" if self._on_edit is not None else "arrow")

    def _canvas_press(self, _event: tk.Event[Any]) -> None:
        return None

    def _canvas_drag(self, _event: tk.Event[Any]) -> None:
        return None

    def _drag_press(self, event: Any) -> str | None:
        if not self._drag_enabled:
            return None
        self._handle_pressed = True
        return self._dispatch_pointer(self._on_drag_press, event)

    def _drag_motion(self, event: Any) -> str | None:
        if not self._handle_pressed:
            return None
        return self._dispatch_pointer(self._on_drag_motion, event)

    def _drag_release(self, event: Any) -> str | None:
        if not self._handle_pressed:
            return None
        self._handle_pressed = False
        return self._dispatch_pointer(self._on_drag_release, event)

    def _canvas_release(self, _event: tk.Event[Any]) -> str:
        self._select()
        return "break"

    def _hover_enter(self, _event: Any = None) -> None:
        if self._hover_leave_after_id is not None:
            try:
                self.after_cancel(self._hover_leave_after_id)
            except tk.TclError:
                pass
            self._hover_leave_after_id = None
        self._set_hovered(True)

    def _hover_leave(self, _event: Any = None) -> None:
        if self._hover_leave_after_id is not None:
            return
        try:
            self._hover_leave_after_id = self.after_idle(self._settle_hover)
        except tk.TclError:
            self._hover_leave_after_id = None

    def _settle_hover(self) -> None:
        self._hover_leave_after_id = None
        try:
            widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        except tk.TclError:
            return
        while widget is not None:
            if widget is self:
                return
            widget = getattr(widget, "master", None)
        self._set_hovered(False)

    def _sync_interaction_indicator(self) -> None:
        """Keep the legacy canvas indicator hidden.

        Hover is communicated by the card surface and pointer cursor. Selection
        already has the outer frame border, so a second line only creates a
        visually doubled outline.
        """

        item = self._interaction_item
        if item is None:
            return
        canvas = self._content_canvas
        canvas.tk.call(str(canvas), "itemconfigure", item, "-state", "hidden")

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "_content_canvas"):
            self._render()

    def _set_scaling(
        self,
        new_widget_scaling: float,
        new_window_scaling: float,
    ) -> None:
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "_content_canvas"):
            border = self._scale(self.theme["card_border_width"])
            self._content_canvas.grid_configure(padx=border, pady=border)
            self._update_readable_widths()
            self._render()

    def update_card(self, card: Mapping[str, Any]) -> None:
        """Update content in place, preserving the card's Tk widget tree."""

        value = dict(card)
        if value.get("id") != self.card_id:
            raise ValueError("cannot change a card widget's ID")
        if value == self.card:
            return
        self.card = value
        self._render()

    def set_drag_enabled(self, enabled: bool) -> None:
        """Show or hide the drag affordance and reclaim its title space."""

        enabled = bool(enabled)
        if self._drag_enabled == enabled:
            return
        self._drag_enabled = enabled
        if not enabled:
            self._handle_pressed = False
        self._render()

    @property
    def edit_button(self) -> ctk.CTkButton:
        """Return the lazily-created compatibility edit command button."""

        if self._edit_button is None:
            self._edit_button = ctk.CTkButton(
                self,
                text="",
                width=1,
                height=1,
                command=self._edit,
            )
        return self._edit_button

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

    def _context_menu(self, event: Any) -> str:
        self._context_menu_position = (int(event.x_root), int(event.y_root))
        try:
            if self._on_select is not None:
                self._on_select(self)
            self._menu()
        finally:
            self._context_menu_position = None
        return "break"

    def _dispatch_pointer(self, callback: PointerCallback | None, event: Any) -> str:
        if callback is not None:
            callback(self, event)
        return "break"

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if self._selected == selected:
            return
        self._selected = selected
        self.configure(
            border_width=(
                self.theme["card_selected_border_width"]
                if selected
                else self.theme["card_border_width"]
            ),
            border_color=(
                self.theme["selected_border_color"]
                if selected
                else self.theme["card_border_color"]
            ),
        )
        tk.Misc.lower(self._canvas)
        # Canvas overrides ``lift`` for canvas items; use the window-level
        # implementation to keep the content widget above CTk's surface.
        tk.Misc.lift(self._content_canvas)

    def _set_hovered(self, hovered: bool) -> None:
        hovered = bool(hovered)
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self._sync_interaction_indicator()

    def set_dragging(self, dragging: bool) -> None:
        dragging = bool(dragging)
        if self._dragging == dragging:
            return
        self._dragging = dragging
        self._sync_surface_color()
        self._sync_interaction_indicator()

    def destroy(self) -> None:
        if self._hover_leave_after_id is not None:
            try:
                self.after_cancel(self._hover_leave_after_id)
            except tk.TclError:
                pass
            self._hover_leave_after_id = None
        super().destroy()
