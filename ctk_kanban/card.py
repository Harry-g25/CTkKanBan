"""Visual representation of an individual Kanban card."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk

from .utils import clone, coerce_field_value, display_value, format_temporal, iter_widget_tree
from .widgets import DateEntry, Tooltip


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
        on_inline_edit_start: Callable[["CTkKanbanCard", str], bool | None] | None = None,
        on_inline_edit_commit: (
            Callable[["CTkKanbanCard", str, Any], bool | str | None] | None
        ) = None,
        on_inline_edit_end: Callable[["CTkKanbanCard"], None] | None = None,
        inline_editing_enabled: bool = False,
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
        self.on_inline_edit_start = on_inline_edit_start
        self.on_inline_edit_commit = on_inline_edit_commit
        self.on_inline_edit_end = on_inline_edit_end
        self.inline_editing_enabled = bool(inline_editing_enabled and renderer is None)
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
        self._wrap_labels: list[tuple[ctk.CTkLabel, int]] = []
        self._half_wrap_labels: list[ctk.CTkLabel] = []
        self._fields_by_key = {str(field["key"]): field for field in fields}
        self._inline_widget_fields: dict[Any, str] = {}
        self._inline_field_widgets: dict[str, list[Any]] = {}
        self.editing_field_key: str | None = None
        self.inline_editor: ctk.CTkFrame | None = None
        self.inline_control: Any | None = None
        self.inline_error_label: ctk.CTkLabel | None = None
        self._inline_original_value: Any = None
        self._inline_variable: Any | None = None
        self._inline_option_map: dict[str, Any] = {}
        self._inline_committing = False
        self._inline_blur_after_id: str | None = None
        self._suppress_inline_release_once = False
        self._content_last_row = 0

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
        density_padding = {"compact": 8, "comfortable": 10, "spacious": 13}.get(self.density, 10)
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
        self.accent_bar.place(x=0, rely=0.5, anchor="w", relheight=0.86)

        visible_fields = [
            field
            for field in self.fields
            if field.get("show_on_card")
            and field["key"] != "title"
            and field.get("type") != "hidden"
            and (
                self.card_data.get(field["key"]) not in (None, "", [])
                or self._field_is_inline_editable(field)
            )
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

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=(13, 10), pady=(density_padding, 3))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(2, minsize=18)
        title_reserve = 58
        title = ctk.CTkLabel(
            header,
            text=str(self.card_data.get("title", "Untitled card")),
            height=22,
            anchor="w",
            justify="left",
            wraplength=max(120, self.card_width - title_reserve),
            font=self.theme.get("card_title_font") or ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme.get("card_title_text_color", self.theme["text_color"]),
        )
        self.title_label = title
        title.grid(row=0, column=0, sticky="ew")
        self._register_inline_widget("title", title)

        priority_field = self._fields_by_key.get("priority")
        show_priority = bool(
            priority_field
            and priority_field.get("show_on_card")
            and priority_field.get("type") != "hidden"
            and (
                priority not in (None, "")
                or self._field_is_inline_editable(priority_field)
            )
        )
        if show_priority and priority_field is not None:
            priority_color = self.priority_colors.get(str(priority), self.theme["tag_text_color"])
            priority_text_color = (
                priority_color
                if priority not in (None, "") and isinstance(priority_color, str)
                else self.theme.get("tag_text_color", self.theme["text_color"])
            )
            self.priority_badge = ctk.CTkLabel(
                header,
                text=(
                    str(priority).upper()
                    if priority not in (None, "")
                    else f"+ {priority_field['label']}"
                ),
                height=19,
                corner_radius=6,
                fg_color=(
                    self.theme.get("card_priority_fg_color", self.theme["tag_fg_color"])
                    if priority not in (None, "")
                    else "transparent"
                ),
                text_color=(
                    priority_text_color
                    if priority not in (None, "")
                    else self.theme.get("overlay_text_color", self.theme["muted_text_color"])
                ),
                font=self.theme.get("badge_font") or ctk.CTkFont(size=9, weight="bold"),
            )
            self.priority_badge.grid(row=0, column=1, padx=(7, 1))
            self._register_inline_widget("priority", self.priority_badge)
            title_reserve += 58
            title.configure(wraplength=max(100, self.card_width - title_reserve))

        if self.show_drag_handle:
            self.drag_handle = ctk.CTkLabel(
                header,
                text="⠿",
                width=18,
                text_color=self.theme.get("card_drag_handle_color", self.theme["muted_text_color"]),
                cursor="fleur",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            self.drag_handle.grid(row=0, column=2, padx=(4, 0))
            self.drag_handle.grid_remove()
            Tooltip(self.drag_handle, "Drag to move card", theme=self.theme)
        self._title_reserved_width = title_reserve

        max_description = int(self.theme.get("card_description_max_chars", 150))
        if self.card_mode == "compact":
            max_description = min(max_description, 82)
        row = 1
        for field in description_fields:
            value = self.card_data.get(field["key"])
            text = (
                display_value(value)
                if value not in (None, "", [])
                else f"+ Add {str(field['label']).casefold()}"
            )
            if value not in (None, "", []) and len(text) > max_description:
                text = f"{text[: max_description - 3].rstrip()}..."
            label = ctk.CTkLabel(
                self,
                text=text,
                anchor="w",
                justify="left",
                wraplength=max(100, self.card_width - 42),
                text_color=(
                    self.theme.get("card_body_text_color", self.theme["muted_text_color"])
                    if value not in (None, "", [])
                    else self.theme.get("overlay_text_color", self.theme["muted_text_color"])
                ),
                font=self.theme.get("card_body_font") or ctk.CTkFont(size=12),
            )
            label.grid(row=row, column=1, sticky="ew", padx=(13, 12), pady=(0, 5))
            self._wrap_labels.append((label, 44))
            self._register_inline_widget(str(field["key"]), label)
            row += 1

        for field in badge_fields:
            self._build_badges(row, field, self.card_data.get(field["key"]))
            row += 1

        if metadata_fields:
            separator = ctk.CTkFrame(
                self,
                height=1,
                fg_color=self.theme.get("card_separator_color", self.theme["card_border_color"]),
            )
            separator.grid(row=row, column=1, sticky="ew", padx=(13, 12), pady=(5, 4))
            row += 1
            metadata_holder = ctk.CTkFrame(self, fg_color="transparent")
            metadata_holder.grid(row=row, column=1, sticky="ew", padx=(13, 12), pady=(0, 2))
            metadata_holder.grid_columnconfigure(0, weight=1)
            metadata_holder.grid_columnconfigure(1, weight=1)
            self.metadata_labels: dict[str, ctk.CTkLabel] = {}
            for index, field in enumerate(metadata_fields):
                value = self.card_data.get(field["key"])
                metadata_label = ctk.CTkLabel(
                    metadata_holder,
                    text=(
                        self._format_metadata(field, value)
                        if value not in (None, "", [])
                        else f"+ Add {str(field['label']).casefold()}"
                    ),
                    height=17,
                    anchor="w",
                    justify="left",
                    wraplength=(
                        max(70, (self.card_width - 54) // 2)
                        if len(metadata_fields) > 1
                        else max(100, self.card_width - 44)
                    ),
                    text_color=(
                        self.theme.get(
                            "card_metadata_text_color",
                            self.theme["muted_text_color"],
                        )
                        if value not in (None, "", [])
                        else self.theme.get(
                            "overlay_text_color",
                            self.theme["muted_text_color"],
                        )
                    ),
                    font=self.theme.get("card_metadata_font") or ctk.CTkFont(size=10),
                )
                metadata_label.grid(
                    row=index // 2,
                    column=index % 2,
                    sticky="ew",
                    padx=(0, 5) if index % 2 == 0 else (5, 0),
                )
                key = str(field["key"])
                self.metadata_labels[key] = metadata_label
                if len(metadata_fields) > 1:
                    self._half_wrap_labels.append(metadata_label)
                else:
                    self._wrap_labels.append((metadata_label, 44))
                self._register_inline_widget(key, metadata_label)
            if self.metadata_labels:
                self.metadata_label = next(iter(self.metadata_labels.values()))
            row += 1

        spacer = ctk.CTkFrame(self, height=max(4, density_padding // 2), fg_color="transparent")
        spacer.grid(row=row, column=1)
        self._content_last_row = row

    def _format_metadata(self, field: dict[str, Any], value: Any) -> str:
        """Return a concise, readable footer item for one field."""

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
        key = str(field["key"]).casefold()
        label = str(field["label"]).split(" (", 1)[0]
        if key in {"assignee", "assigned_to", "owner"}:
            return shown_value
        if key in {"due", "due_date", "deadline"}:
            return f"Due {shown_value}"
        if key in {"estimate", "effort", "story_points"}:
            return f"{label} {shown_value}"
        return f"{label}: {shown_value}"

    def _build_badges(self, row: int, field: dict[str, Any], value: Any) -> None:
        """Render tag, tags, and badge values as compact chips."""

        empty = value in (None, "", [])
        values = (
            [f"+ Add {str(field['label']).casefold()}"]
            if empty
            else list(value)
            if isinstance(value, (list, tuple, set))
            else [value]
        )
        hidden_count = max(0, len(values) - self.max_visible_tags)
        values = values[: self.max_visible_tags]
        if hidden_count:
            values.append(f"+{hidden_count} more")
        holder = ctk.CTkFrame(self, fg_color="transparent")
        holder.grid(row=row, column=1, sticky="w", padx=(11, 12), pady=(2, 2))
        for index, item in enumerate(values):
            text = str(item)
            color = self.tag_colors.get(text, self.theme["tag_fg_color"])
            if field["key"] == "priority" or field.get("type") == "badge":
                color = self.priority_colors.get(text, color)
            chip = ctk.CTkLabel(
                holder,
                text=text,
                height=19,
                corner_radius=5,
                fg_color="transparent" if empty else color,
                text_color=(
                    self.theme.get("overlay_text_color", self.theme["muted_text_color"])
                    if empty
                    else self.theme["tag_text_color"]
                    if isinstance(color, tuple)
                    else self.theme.get("badge_text_color", "#FFFFFF")
                ),
                font=self.theme.get("badge_font") or ctk.CTkFont(size=9, weight="bold"),
            )
            chip.grid(row=index // self.tags_per_row, column=index % self.tags_per_row, padx=2, pady=1)
            if text.startswith("+") and hidden_count:
                Tooltip(
                    chip,
                    ", ".join(str(item) for item in list(value)[self.max_visible_tags :]),
                    theme=self.theme,
                )
        self._register_inline_widget(str(field["key"]), holder)

    def _field_is_inline_editable(self, field: dict[str, Any]) -> bool:
        """Return whether a configured field may be changed inside the card."""

        return bool(
            self.inline_editing_enabled
            and field.get("show_on_card")
            and field.get("type") != "hidden"
            and not field.get("read_only")
        )

    def _register_inline_widget(self, field_key: str, widget: Any) -> None:
        """Associate a rendered field subtree with its inline-edit action."""

        field = self._fields_by_key.get(field_key)
        if field is None or not self._field_is_inline_editable(field):
            return
        self._inline_field_widgets.setdefault(field_key, []).append(widget)
        for descendant in iter_widget_tree(widget):
            self._inline_widget_fields[descendant] = field_key
            try:
                descendant.configure(cursor="hand2")
            except (tk.TclError, AttributeError, TypeError, ValueError):
                pass

    def start_inline_edit(self, field_key: str = "title") -> bool:
        """Open an editor inside the card for one visible, writable field."""

        field_key = str(field_key)
        field = self._fields_by_key.get(field_key)
        if field is None or not self._field_is_inline_editable(field):
            return False
        if field_key not in self._inline_field_widgets:
            return False
        if self.editing_field_key == field_key and self.inline_editor is not None:
            self._focus_inline_control()
            return True
        if self.editing_field_key is not None:
            if not self.commit_inline_edit():
                return False
            try:
                if not self.winfo_exists():
                    if self.on_inline_edit_start is None:
                        return False
                    return bool(self.on_inline_edit_start(self, field_key))
            except tk.TclError:
                if self.on_inline_edit_start is None:
                    return False
                return bool(self.on_inline_edit_start(self, field_key))
        if self.on_inline_edit_start is not None:
            outcome = self.on_inline_edit_start(self, field_key)
            if outcome is False:
                return False

        self.editing_field_key = field_key
        self._inline_original_value = clone(self.card_data.get(field_key))
        control_value = self.card_data.get(field_key, field.get("default"))
        self._inline_variable = None
        self._inline_option_map = {}

        editor = ctk.CTkFrame(
            self,
            fg_color=self.theme.get(
                "card_metadata_fg_color",
                self.theme["input_fg_color"],
            ),
            border_color=self.theme.get(
                "card_selected_border_color",
                self.theme["input_border_color"],
            ),
            border_width=1,
            corner_radius=self.theme.get("input_corner_radius", 8),
        )
        editor.grid(
            row=self._content_last_row + 1,
            column=1,
            sticky="ew",
            padx=(11, 10),
            pady=(2, 9),
        )
        editor.grid_columnconfigure(0, weight=1)
        self.inline_editor = editor

        heading = ctk.CTkFrame(editor, fg_color="transparent")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 4))
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            heading,
            text=str(field["label"]),
            height=18,
            anchor="w",
            text_color=self.theme.get("card_title_text_color", self.theme["text_color"]),
            font=self.theme.get("form_label_font"),
        ).grid(row=0, column=0, sticky="ew")
        save_hint = (
            "Ctrl+Enter saves · Esc cancels"
            if field.get("type", "text") == "textarea"
            else "Enter saves · Esc cancels"
        )
        ctk.CTkLabel(
            heading,
            text=save_hint,
            height=18,
            text_color=self.theme.get("overlay_text_color", self.theme["muted_text_color"]),
            font=self.theme.get("card_metadata_font"),
        ).grid(row=0, column=1, padx=(6, 0))

        control = self._build_inline_control(editor, field, control_value)
        control.grid(row=1, column=0, sticky="ew", padx=(8, 5), pady=(0, 5))
        self.inline_control = control

        actions = ctk.CTkFrame(editor, fg_color="transparent")
        actions.grid(row=1, column=1, sticky="ne", padx=(0, 7), pady=(0, 5))
        ctk.CTkButton(
            actions,
            text="✓",
            width=30,
            height=30,
            fg_color=self.theme["button_fg_color"],
            hover_color=self.theme["button_hover_color"],
            text_color=self.theme.get("button_text_color"),
            corner_radius=7,
            font=self.theme.get("button_font"),
            command=self.commit_inline_edit,
        ).pack(side="left", padx=(0, 3))
        ctk.CTkButton(
            actions,
            text="×",
            width=30,
            height=30,
            fg_color=self.theme["secondary_button_fg_color"],
            hover_color=self.theme["secondary_button_hover_color"],
            text_color=self.theme.get("secondary_button_text_color", self.theme["text_color"]),
            corner_radius=7,
            font=self.theme.get("button_font"),
            command=self.cancel_inline_edit,
        ).pack(side="left")

        self.inline_error_label = ctk.CTkLabel(
            editor,
            text="",
            anchor="w",
            justify="left",
            wraplength=max(120, self.card_width - 78),
            text_color=self.theme["danger_color"],
            font=self.theme.get("card_metadata_font"),
        )
        self.inline_error_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 5),
        )
        self.inline_error_label.grid_remove()
        self._bind_inline_control(field, control)
        self.after_idle(self._focus_inline_control)
        return True

    def _build_inline_control(
        self,
        master: Any,
        field: dict[str, Any],
        value: Any,
    ) -> Any:
        """Create the compact control used by an active inline field editor."""

        field_type = field.get("type", "text")
        entry_options = {
            "height": 32,
            "fg_color": self.theme["input_fg_color"],
            "border_color": self.theme["input_border_color"],
            "text_color": self.theme.get("input_text_color", self.theme["text_color"]),
            "placeholder_text_color": self.theme.get(
                "input_placeholder_text_color",
                self.theme.get("overlay_text_color", self.theme["text_color"]),
            ),
            "corner_radius": self.theme.get("input_corner_radius", self.theme["corner_radius"]),
            "border_width": self.theme.get("input_border_width", self.theme["border_width"]),
            "font": self.theme.get("input_font"),
        }
        if field_type == "textarea":
            control = ctk.CTkTextbox(
                master,
                height=72,
                fg_color=self.theme["textbox_fg_color"],
                border_color=self.theme["textbox_border_color"],
                text_color=self.theme.get("textbox_text_color", self.theme["text_color"]),
                corner_radius=self.theme.get(
                    "textbox_corner_radius",
                    self.theme["corner_radius"],
                ),
                border_width=self.theme.get(
                    "textbox_border_width",
                    self.theme["border_width"],
                ),
                scrollbar_button_color=self.theme["scrollbar_button_color"],
                scrollbar_button_hover_color=self.theme["scrollbar_button_hover_color"],
                font=self.theme.get("input_font"),
            )
            if value not in (None, ""):
                control.insert("1.0", display_value(value))
            return control
        if field_type == "checkbox":
            variable = ctk.BooleanVar(value=bool(value))
            self._inline_variable = variable
            return ctk.CTkCheckBox(
                master,
                text=str(field.get("checkbox_text") or field["label"]),
                variable=variable,
                height=30,
                fg_color=self.theme["checkbox_fg_color"],
                hover_color=self.theme["checkbox_hover_color"],
                border_color=self.theme["checkbox_border_color"],
                checkmark_color=self.theme["checkbox_checkmark_color"],
                text_color=self.theme.get("checkbox_text_color", self.theme["text_color"]),
                corner_radius=self.theme.get(
                    "checkbox_corner_radius",
                    self.theme["corner_radius"],
                ),
                border_width=self.theme.get(
                    "checkbox_border_width",
                    self.theme["border_width"],
                ),
                font=self.theme.get("checkbox_font") or self.theme.get("input_font"),
            )
        if field_type in {"select", "badge"} and field.get("options"):
            options = list(field.get("options") or [])
            mapping = {str(option): option for option in options}
            mapping[""] = ""
            self._inline_option_map = mapping
            variable = ctk.StringVar(value="" if value is None else str(value))
            self._inline_variable = variable
            return ctk.CTkOptionMenu(
                master,
                values=list(mapping),
                variable=variable,
                height=32,
                fg_color=self.theme["optionmenu_fg_color"],
                button_color=self.theme["optionmenu_button_color"],
                button_hover_color=self.theme["optionmenu_button_hover_color"],
                text_color=self.theme.get(
                    "optionmenu_text_color",
                    self.theme["button_text_color"],
                ),
                dropdown_fg_color=self.theme["optionmenu_dropdown_fg_color"],
                dropdown_hover_color=self.theme["optionmenu_dropdown_hover_color"],
                dropdown_text_color=self.theme["optionmenu_dropdown_text_color"],
                corner_radius=self.theme.get(
                    "optionmenu_corner_radius",
                    self.theme["corner_radius"],
                ),
                font=self.theme.get("optionmenu_font") or self.theme.get("input_font"),
                dropdown_font=self.theme.get("menu_font") or self.theme.get("input_font"),
            )
        if field_type == "date":
            return DateEntry(
                master,
                value=value,
                theme=self.theme,
                placeholder_text=str(field.get("placeholder") or "YYYY-MM-DD"),
                **entry_options,
            )

        control = ctk.CTkEntry(
            master,
            placeholder_text=str(field.get("placeholder") or ""),
            **entry_options,
        )
        if value not in (None, ""):
            control.insert(0, display_value(value))
        return control

    def _bind_inline_control(self, field: dict[str, Any], control: Any) -> None:
        """Give inline controls predictable save, cancel, and blur behavior."""

        field_type = field.get("type", "text")
        for widget in iter_widget_tree(control):
            tk.Misc.bind(widget, "<Escape>", self._cancel_inline_event, add="+")
            if field_type == "textarea":
                tk.Misc.bind(
                    widget,
                    "<Control-Return>",
                    self._commit_inline_event,
                    add="+",
                )
                tk.Misc.bind(
                    widget,
                    "<Control-KP_Enter>",
                    self._commit_inline_event,
                    add="+",
                )
            else:
                tk.Misc.bind(widget, "<Return>", self._commit_inline_event, add="+")
                tk.Misc.bind(widget, "<KP_Enter>", self._commit_inline_event, add="+")
            tk.Misc.bind(widget, "<FocusOut>", self._schedule_inline_blur, add="+")

    def _focus_inline_control(self) -> None:
        control = self.inline_control
        if control is None:
            return
        try:
            control.focus_set()
        except (tk.TclError, AttributeError, ValueError):
            pass

    def _cancel_inline_event(self, _event: Any = None) -> str:
        self.cancel_inline_edit()
        return "break"

    def _commit_inline_event(self, _event: Any = None) -> str:
        self.commit_inline_edit()
        return "break"

    def _schedule_inline_blur(self, _event: Any = None) -> None:
        if self.editing_field_key is None or self._inline_committing:
            return
        if self._inline_blur_after_id is not None:
            try:
                self.after_cancel(self._inline_blur_after_id)
            except (tk.TclError, ValueError):
                pass
        self._inline_blur_after_id = self.after_idle(self._commit_if_focus_left)

    def _commit_if_focus_left(self) -> None:
        self._inline_blur_after_id = None
        editor = self.inline_editor
        if editor is None or self.editing_field_key is None:
            return
        focus = self.focus_get()
        picker = getattr(self.inline_control, "_picker", None)
        target = focus
        while target is not None:
            if target is picker:
                return
            target = getattr(target, "master", None)
        while focus is not None:
            if focus is editor:
                return
            focus = getattr(focus, "master", None)
        self.commit_inline_edit()

    def _collect_inline_value(self) -> Any:
        field_key = self.editing_field_key
        control = self.inline_control
        if field_key is None or control is None:
            raise ValueError("No inline field is being edited")
        field = self._fields_by_key[field_key]
        field_type = field.get("type", "text")
        if field_type == "textarea":
            value: Any = control.get("1.0", "end-1c")
        elif field_type == "checkbox":
            value = bool(self._inline_variable.get())
        elif field_type in {"select", "badge"} and self._inline_option_map:
            selected = self._inline_variable.get()
            value = self._inline_option_map.get(selected, selected)
        else:
            value = control.get()
        preserve_option_value = (
            field_type in {"select", "badge"} and bool(self._inline_option_map)
        )
        return coerce_field_value(
            field,
            value,
            strip_strings=not preserve_option_value,
        )

    @staticmethod
    def _same_inline_value(left: Any, right: Any) -> bool:
        if left in (None, "", []) and right in (None, "", []):
            return True
        if type(left) is not type(right):
            return False
        try:
            return bool(left == right)
        except (TypeError, ValueError):
            return False

    def _show_inline_error(self, message: str) -> None:
        label = self.inline_error_label
        if label is None:
            return
        label.configure(text=message)
        label.grid()
        self._focus_inline_control()

    def commit_inline_edit(self) -> bool:
        """Validate and save the active inline value through the board callback."""

        field_key = self.editing_field_key
        if field_key is None or self._inline_committing:
            return False
        try:
            value = self._collect_inline_value()
        except Exception as exc:
            self._show_inline_error(str(exc).strip() or exc.__class__.__name__)
            return False
        if self._same_inline_value(value, self._inline_original_value):
            self._close_inline_editor()
            return True
        if self.on_inline_edit_commit is None:
            self._show_inline_error("Inline editing is not connected to the board")
            return False

        self._inline_committing = True
        try:
            outcome = self.on_inline_edit_commit(self, field_key, clone(value))
        except Exception as exc:
            self._inline_committing = False
            self._show_inline_error(str(exc).strip() or exc.__class__.__name__)
            return False
        self._inline_committing = False
        if outcome is False:
            self._show_inline_error("The change was cancelled")
            return False
        if isinstance(outcome, str) and outcome:
            self._show_inline_error(outcome)
            return False
        if outcome is not True:
            self._show_inline_error("The change could not be saved")
            return False

        self.card_data[field_key] = clone(value)
        self._close_inline_editor()
        return True

    def cancel_inline_edit(self) -> bool:
        """Discard the active inline value without mutating board data."""

        if self.editing_field_key is None:
            return False
        self._close_inline_editor()
        return True

    def _close_inline_editor(self) -> None:
        was_editing = self.editing_field_key is not None
        editor = self.inline_editor
        self.inline_editor = None
        self.inline_control = None
        self.inline_error_label = None
        self.editing_field_key = None
        self._inline_original_value = None
        self._inline_variable = None
        self._inline_option_map = {}
        if self._inline_blur_after_id is not None:
            try:
                self.after_cancel(self._inline_blur_after_id)
            except (tk.TclError, ValueError, AttributeError):
                pass
            self._inline_blur_after_id = None
        if editor is not None:
            try:
                editor.destroy()
            except Exception:
                pass
        if was_editing and self.on_inline_edit_end is not None:
            self.on_inline_edit_end(self)

    def _press_inline_field(self, event: Any) -> str:
        self._dispatch(self.on_press, self, event)
        return "break"

    def _activate_inline_field(self, field_key: str, event: Any = None) -> str:
        if event is not None:
            self._dispatch(self.on_release, self, event)
        if self._suppress_inline_release_once:
            self._suppress_inline_release_once = False
            return "break"
        self.start_inline_edit(field_key)
        return "break"

    def _double_click_inline_field(self, field_key: str, event: Any) -> str:
        self._suppress_inline_release_once = True
        try:
            event.inline_field_key = field_key
        except (AttributeError, TypeError):
            pass
        self._dispatch(self.on_double_click, self, event)
        return "break"

    def _bind_pointer_events(self) -> None:
        """Bind the same gestures to card descendants for natural clicking."""

        for widget in iter_widget_tree(self):
            field_key = self._inline_widget_fields.get(widget)
            if field_key is not None:
                widget.bind("<ButtonPress-1>", self._press_inline_field, add="+")
                widget.bind("<B1-Motion>", lambda _event: "break", add="+")
                widget.bind(
                    "<ButtonRelease-1>",
                    lambda event, key=field_key: self._activate_inline_field(key, event),
                    add="+",
                )
                widget.bind(
                    "<Double-Button-1>",
                    lambda event, key=field_key: self._double_click_inline_field(
                        key,
                        event,
                    ),
                    add="+",
                )
            else:
                widget.bind(
                    "<ButtonPress-1>",
                    lambda event, card=self: self._dispatch(self.on_press, card, event),
                    add="+",
                )
                widget.bind(
                    "<B1-Motion>",
                    lambda event, card=self: self._dispatch(self.on_motion, card, event),
                    add="+",
                )
                widget.bind(
                    "<ButtonRelease-1>",
                    lambda event, card=self: self._dispatch(self.on_release, card, event),
                    add="+",
                )
                widget.bind(
                    "<Double-Button-1>",
                    lambda event, card=self: self._dispatch(
                        self.on_double_click,
                        card,
                        event,
                    ),
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
        if self.show_drag_handle and hasattr(self, "drag_handle"):
            self.drag_handle.grid()
        if self.hover_enabled and not self.selected and not self.dimmed:
            self.configure(
                fg_color=self.theme["card_hover_color"],
                border_color=self.theme.get("card_hover_border_color", self.theme["card_border_color"]),
            )

    def _on_leave(self, event: Any) -> None:
        if self.dragging or not self._hovered:
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        while target is not None:
            if target is self:
                return
            target = getattr(target, "master", None)
        self._hovered = False
        if self.show_drag_handle and hasattr(self, "drag_handle"):
            self.drag_handle.grid_remove()
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
            if self.show_drag_handle and hasattr(self, "drag_handle"):
                self.drag_handle.grid_remove()
            self._apply_visual_state()

    def reflow(self, width: int) -> None:
        """Update wrapping after a responsive or user-driven column resize."""

        self.card_width = width
        if hasattr(self, "title_label"):
            self.title_label.configure(
                wraplength=max(100, width - getattr(self, "_title_reserved_width", 58))
            )
        for label, reserved_width in self._wrap_labels:
            label.configure(wraplength=max(80, width - reserved_width))
        for label in self._half_wrap_labels:
            label.configure(wraplength=max(60, (width - 54) // 2))
        if self.inline_error_label is not None:
            self.inline_error_label.configure(wraplength=max(120, width - 78))
