"""Embedded, schema-driven, explicit-save card inspector."""

from __future__ import annotations

import tkinter as tk
from collections import OrderedDict
from collections.abc import Sequence
from copy import deepcopy
from functools import partial
from typing import Any, Callable, Mapping, cast

import customtkinter as ctk

from ._scrolling import ManagedScrollableFrame
from .fields import FieldInput, default_for_field, normalize_field_value, normalize_fields
from .themes import merge_theme

SaveCallback = Callable[[dict[str, Any]], bool | str | None]


class _FastOptionMenu(ctk.CTkOptionMenu):
    """CTk option menu without a full application idle flush per redraw."""

    def _draw(self, no_color_updates: bool = False) -> None:
        canvas = getattr(self, "_canvas", None)
        if canvas is None:
            super()._draw(no_color_updates)
            return
        flush = canvas.update_idletasks
        canvas.update_idletasks = lambda: None
        try:
            super()._draw(no_color_updates)
        finally:
            canvas.update_idletasks = flush


class _FastTextbox(ctk.CTkTextbox):
    """Textbox that defers its compound scrollbars' eager idle flushes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        original_draw = ctk.CTkScrollbar._draw

        def fast_draw(scrollbar: Any, no_color_updates: bool = False) -> None:
            canvas = getattr(scrollbar, "_canvas", None)
            if canvas is None:
                original_draw(scrollbar, no_color_updates)
                return
            flush = canvas.update_idletasks
            canvas.update_idletasks = lambda: None
            try:
                original_draw(scrollbar, no_color_updates)
            finally:
                canvas.update_idletasks = flush

        ctk.CTkScrollbar._draw = fast_draw
        try:
            super().__init__(*args, **kwargs)
        finally:
            ctk.CTkScrollbar._draw = original_draw


class _FastLabel(tk.Label):
    """Native label with CTk-compatible appearance-aware color options."""

    def __init__(
        self,
        master: Any,
        *,
        resolve: Callable[[Any], Any],
        background: Any,
        text_color: Any,
        **kwargs: Any,
    ) -> None:
        self._resolve = resolve
        self._background_token = background
        self._text_token = text_color
        super().__init__(
            master,
            borderwidth=0,
            highlightthickness=0,
            background=resolve(background),
            foreground=resolve(text_color),
            **kwargs,
        )

    def apply_appearance(self) -> None:
        super().configure(
            background=self._resolve(self._background_token),
            foreground=self._resolve(self._text_token),
        )

    def configure(  # type: ignore[override]
        self, cnf: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        values = dict(cnf or {})
        values.update(kwargs)
        if "text_color" in values:
            self._text_token = values.pop("text_color")
            values["foreground"] = self._resolve(self._text_token)
        if "fg_color" in values:
            self._background_token = values.pop("fg_color")
            values["background"] = self._resolve(self._background_token)
        super().configure(**values)

    config = configure  # type: ignore[assignment]


class CardEditor(ctk.CTkFrame):
    """Generate card controls from field definitions in a right-side drawer."""

    PANEL_WIDTH = 420

    def __init__(
        self,
        master: Any,
        *,
        title: str,
        initial: Mapping[str, Any],
        columns: Sequence[Mapping[str, Any]],
        on_save: SaveCallback,
        on_close: Callable[[CardEditor], None] | None = None,
        theme: Mapping[str, Any] | None = None,
        fields: Sequence[FieldInput] | None = None,
        panel_width: int | None = None,
        allow_column_change: bool = True,
        _normalized_fields: bool = False,
        _normalized_theme: bool = False,
        _font_cache: dict[str, ctk.CTkFont] | None = None,
    ) -> None:
        self.theme = (
            theme if _normalized_theme and theme is not None else merge_theme(theme)
        )
        self.fields: tuple[Mapping[str, Any], ...] = (
            tuple(cast(Sequence[Mapping[str, Any]], fields or ()))
            if _normalized_fields
            else normalize_fields(fields)
        )
        self._font_cache = {} if _font_cache is None else _font_cache
        self._native_labels: list[_FastLabel] = []
        self._native_pill_buttons: list[tuple[tk.Button, Any]] = []
        self._native_sections: list[tk.Frame] = []
        self.panel_width = self.PANEL_WIDTH if panel_width is None else panel_width
        self.allow_column_change = bool(allow_column_change)
        super().__init__(
            master,
            width=self.panel_width,
            corner_radius=0,
            fg_color=self.theme["editor_fg_color"],
            border_width=self.theme["editor_border_width"],
            border_color=self.theme["divider_color"],
        )
        self.grid_propagate(False)
        self._initial = deepcopy(dict(initial))
        self._on_save = on_save
        self._on_close = on_close
        self._saving = False
        self._destroying = False
        self._close_notified = False
        self._tracking_changes = False
        self._dirty_state: bool | None = None
        self._dirty_after_id: str | None = None
        self._column_values: dict[str, Any] = {}
        self._variables: dict[str, tk.Variable] = {}
        self._textboxes: dict[str, ctk.CTkTextbox] = {}
        self._select_values: dict[str, dict[str, Any]] = {}
        self._list_values: dict[str, list[Any]] = {}
        self._list_drafts: dict[str, tk.StringVar] = {}
        self._list_frames: dict[str, ctk.CTkFrame] = {}
        self._field_widgets: dict[str, Any] = {}
        self._slide_x = 0
        self._slide_target = 0
        self._slide_after_id: str | None = None
        self._activate_after_id: str | None = None
        self._shortcut_bindings: list[tuple[str, str]] = []

        self._owner = master.winfo_toplevel()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header(title)
        ctk.CTkFrame(self, height=1, fg_color=self.theme["divider_color"]).grid(
            row=1, column=0, sticky="ew"
        )
        self.form: Any = ManagedScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=self.theme["scrollbar_color"],
            scrollbar_button_hover_color=self.theme["scrollbar_hover_color"],
            _defer_initial_scrollbar_flush=True,
        )
        self.form.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=self.theme["editor_form_padding_x"],
            pady=self.theme["editor_form_padding_y"],
        )
        self.form.grid_columnconfigure(0, weight=1)
        if hasattr(self.form, "_scrollbar"):
            self.form.set_scrollbar_thickness(self.theme["scrollbar_width"])

        column_labels, selected_column = self._prepare_columns(
            columns, initial.get("column", initial.get("column_id"))
        )
        self._column_var = tk.StringVar(self, value=selected_column)
        self._build_schema_form(column_labels)
        self._build_footer()

        self._baseline = self._snapshot_values()
        self._bind_change_tracking()
        self._tracking_changes = True
        self._update_dirty_state()
        self._bind_shortcuts()

        self.place(relx=1.0, rely=0.0, x=0, relheight=1.0)
        self.lift()
        self._slide_target = -self.winfo_reqwidth()
        self._slide_after_id = self.after_idle(self._slide_open)
        self._activate_after_id = self.after(20, self._activate)

    def _label_background(self, master: Any) -> Any:
        current = master
        while current is not None:
            try:
                if isinstance(current, ctk.CTkBaseClass):
                    color = current.cget("fg_color")
                    if color != "transparent":
                        return color
                elif isinstance(current, tk.Misc):
                    return current.cget("background")
            except (AttributeError, tk.TclError, ValueError):
                pass
            current = getattr(current, "master", None)
        return self.theme["editor_fg_color"]

    def _make_label(
        self,
        master: Any,
        *,
        text_color: Any | None = None,
        fg_color: Any | None = None,
        **kwargs: Any,
    ) -> _FastLabel:
        label = _FastLabel(
            master,
            resolve=self._apply_appearance_mode,
            background=(self._label_background(master) if fg_color is None else fg_color),
            text_color=self.theme["text_color"] if text_color is None else text_color,
            **kwargs,
        )
        self._native_labels.append(label)
        return label

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        for label in getattr(self, "_native_labels", ()):
            label.apply_appearance()
        for button, color in getattr(self, "_native_pill_buttons", ()):
            try:
                button.configure(
                    background=self._apply_appearance_mode(color),
                    foreground=self._apply_appearance_mode(self.theme["pill_text_color"]),
                    activebackground=self._apply_appearance_mode(
                        self.theme["danger_color"]
                    ),
                )
            except tk.TclError:
                pass
        for section in getattr(self, "_native_sections", ()):
            try:
                section.configure(
                    background=self._apply_appearance_mode(
                        self.theme["editor_section_fg_color"]
                    ),
                    highlightbackground=self._apply_appearance_mode(
                        self.theme["divider_color"]
                    ),
                )
            except tk.TclError:
                pass

    def _build_header(self, title: str) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=self.theme["editor_header_padding_x"],
            pady=self.theme["editor_header_padding_y"],
        )
        header.grid_columnconfigure(0, weight=1)
        self._make_label(
            header,
            text="CARD DETAILS",
            anchor="w",
            text_color=self.theme["accent_color"],
            font=self._font("editor_eyebrow_font"),
        ).grid(row=0, column=0, sticky="ew")
        heading_row = ctk.CTkFrame(header, height=1, fg_color="transparent")
        heading_row.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._make_label(
            heading_row,
            text=title,
            anchor="w",
            font=self._font("editor_title_font"),
        ).pack(side="left")
        self._make_label(
            heading_row,
            text="NEW" if title.casefold().startswith("add") else "EDITING",
            fg_color=self.theme["count_fg_color"],
            text_color=self.theme["muted_text_color"],
            font=self._font("editor_status_font"),
            padx=7,
            pady=2,
        ).pack(side="left", padx=(9, 0))
        self.close_button = ctk.CTkButton(
            header,
            text="×",
            width=self.theme["small_control_size"],
            height=self.theme["small_control_size"],
            corner_radius=self.theme["control_corner_radius"],
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self.close,
        )
        self.close_button.grid(row=0, column=1, rowspan=2, padx=(12, 0))

    def _build_schema_form(self, column_labels: list[str]) -> None:
        sections: OrderedDict[str, list[Mapping[str, Any]]] = OrderedDict()
        for field in self.fields:
            if field["show_in_editor"]:
                sections.setdefault(field["section"], []).append(field)
        sections.setdefault("Organisation", [])

        for section_index, (section_name, section_fields) in enumerate(sections.items()):
            section = self._section(self.form, row=section_index, title=section_name)
            section.grid_columnconfigure(0, weight=1)
            row = 1
            for section_field in section_fields:
                row = self._build_field(section, row, section_field)
            if section_name == "Organisation":
                self._label(section, "Column", row=row)
                self.column_menu = _FastOptionMenu(
                    section,
                    values=column_labels,
                    variable=self._column_var,
                    dynamic_resizing=False,
                    height=self.theme["input_height"],
                    corner_radius=self.theme["input_corner_radius"],
                )
                self.column_menu.grid(
                    row=row + 1,
                    column=0,
                    sticky="ew",
                    padx=self.theme["editor_field_padding_x"],
                    pady=(0, self.theme["editor_field_gap"]),
                )
                if not self._column_values or not self.allow_column_change:
                    self.column_menu.configure(state="disabled")

    def _build_field(self, section: tk.Misc, row: int, field: Mapping[str, Any]) -> int:
        key = str(field["key"])
        field_type = field["type"]
        label = str(field["label"]) + (" *" if field.get("required") else "")
        self._label(section, label, row=row)
        row += 1
        initial = deepcopy(self._initial.get(key, default_for_field(field)))

        if field_type == "textarea":
            widget = _FastTextbox(
                section,
                height=self.theme["textbox_height"],
                wrap="word",
                border_width=self.theme["input_border_width"],
                border_color=self.theme["input_border_color"],
                corner_radius=self.theme["input_corner_radius"],
            )
            widget.insert("1.0", self._text(initial))
            widget.edit_modified(False)
            self._textboxes[key] = widget
            if key == "description":
                self.description_textbox = widget
        elif field_type == "checkbox":
            bool_variable = tk.BooleanVar(self, value=bool(initial))
            widget = ctk.CTkCheckBox(
                section,
                text=str(field.get("help_text") or field["label"]),
                variable=bool_variable,
                height=self.theme["input_height"],
            )
            self._variables[key] = bool_variable
        elif field_type == "select":
            labels, selected = self._prepare_options(field, initial)
            select_variable = tk.StringVar(self, value=selected)
            widget = _FastOptionMenu(
                section,
                values=labels,
                variable=select_variable,
                dynamic_resizing=False,
                height=self.theme["input_height"],
                corner_radius=self.theme["input_corner_radius"],
            )
            self._variables[key] = select_variable
            if key == "priority":
                self._priority_var = select_variable
                self.priority_menu = widget
        elif field_type in {"tags", "multiselect"}:
            widget = self._build_list_field(section, key, field, initial)
        else:
            text_variable = tk.StringVar(self, value=self._text(initial))
            widget = ctk.CTkEntry(
                section,
                textvariable=text_variable,
                placeholder_text=str(field.get("placeholder", "")),
                height=self.theme["input_height"],
                corner_radius=self.theme["input_corner_radius"],
                border_width=self.theme["input_border_width"],
                border_color=self.theme["input_border_color"],
            )
            self._variables[key] = text_variable
            if field.get("card_role") == "title":
                self._title_var = text_variable
                self.title_entry = widget

        widget.grid(
            row=row,
            column=0,
            sticky="ew",
            padx=self.theme["editor_field_padding_x"],
            pady=(0, 4 if field.get("help_text") and field_type != "checkbox" else self.theme["editor_field_gap"]),
        )
        self._field_widgets[key] = widget
        if field.get("read_only"):
            widget.configure(state="disabled")
        row += 1
        if field.get("help_text") and field_type != "checkbox":
            self._make_label(
                section,
                text=str(field["help_text"]),
                anchor="w",
                justify="left",
                wraplength=max(180, self.panel_width - 90),
                text_color=self.theme["muted_text_color"],
                font=self._font("help_text_font"),
            ).grid(
                row=row,
                column=0,
                sticky="ew",
                padx=self.theme["editor_field_padding_x"],
                pady=(0, self.theme["editor_field_gap"]),
            )
            row += 1
        return row

    def _build_list_field(
        self,
        section: ctk.CTkFrame,
        key: str,
        field: Mapping[str, Any],
        initial: Any,
    ) -> ctk.CTkFrame:
        values = self._normalise_list(initial, tags=field["type"] == "tags")
        self._list_values[key] = values
        container = ctk.CTkFrame(section, fg_color="transparent")
        container.grid_columnconfigure(0, weight=1)
        pills = ctk.CTkFrame(container, height=1, fg_color="transparent")
        pills.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._list_frames[key] = pills
        draft = tk.StringVar(self)
        self._list_drafts[key] = draft
        entry = ctk.CTkEntry(
            container,
            textvariable=draft,
            placeholder_text=str(field.get("placeholder") or "Add a value"),
            height=self.theme["compact_input_height"],
            corner_radius=self.theme["input_corner_radius"],
            border_width=self.theme["input_border_width"],
            border_color=self.theme["input_border_color"],
        )
        entry.grid(row=1, column=0, sticky="ew", padx=(0, 7), pady=(7, 0))
        entry.bind(
            "<Return>", lambda _event, field_key=key: self._list_return(field_key), add="+"
        )
        button = ctk.CTkButton(
            container,
            text="Add",
            width=58,
            height=self.theme["compact_input_height"],
            corner_radius=self.theme["control_corner_radius"],
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["column_border_color"],
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=lambda field_key=key: self._commit_list_field(field_key),
        )
        button.grid(row=1, column=1, pady=(7, 0))
        self._render_list_field(key)
        if key == "tags":
            self._tags = values
            self._tag_var = draft
            self.tags_frame = pills
            self.tags_entry = entry
            self.add_tag_button = button
        return container

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=self.theme["editor_fg_color"], corner_radius=0)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(footer, height=1, fg_color=self.theme["divider_color"]).grid(
            row=0, column=0, columnspan=3, sticky="ew"
        )
        self.error_label = self._make_label(
            footer,
            text="",
            anchor="w",
            wraplength=max(240, self.panel_width - 50),
            text_color=self.theme["error_text_color"],
        )
        self.error_label.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(9, 0))
        self.error_label.grid_remove()
        self.status_label = self._make_label(
            footer,
            text="",
            anchor="w",
            text_color=self.theme["muted_text_color"],
            font=self._font("status_text_font"),
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=(20, 8), pady=(13, 18))
        self.cancel_button = ctk.CTkButton(
            footer,
            text="Cancel",
            width=80,
            height=self.theme["button_height"],
            corner_radius=self.theme["control_corner_radius"],
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["column_border_color"],
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self.close,
        )
        self.cancel_button.grid(row=2, column=1, padx=(0, 8), pady=(13, 18))
        self.save_button = ctk.CTkButton(
            footer,
            text="Save changes",
            width=108,
            height=self.theme["button_height"],
            corner_radius=self.theme["control_corner_radius"],
            command=self.save,
        )
        self.save_button.grid(row=2, column=2, padx=(0, 20), pady=(13, 18))

    def _section(self, master: Any, *, row: int, title: str) -> tk.Frame:
        section = tk.Frame(
            master,
            height=1,
            borderwidth=0,
            highlightthickness=self.theme["editor_section_border_width"],
            background=self._apply_appearance_mode(
                self.theme["editor_section_fg_color"]
            ),
            highlightbackground=self._apply_appearance_mode(
                self.theme["divider_color"]
            ),
        )
        self._native_sections.append(section)
        section.grid(
            row=row,
            column=0,
            sticky="ew",
            pady=(0, self.theme["editor_section_gap"]),
            padx=(0, 2),
        )
        self._make_label(
            section,
            text=title,
            anchor="w",
            font=self._font("section_title_font"),
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=self.theme["editor_field_padding_x"],
            pady=self.theme["editor_section_title_padding_y"],
        )
        return section

    def _label(self, master: Any, text: str, *, row: int) -> None:
        self._make_label(
            master,
            text=text,
            anchor="w",
            font=self._font("field_label_font"),
        ).grid(
            row=row,
            column=0,
            sticky="ew",
            padx=self.theme["editor_field_padding_x"],
            pady=(0, 5),
        )

    def _prepare_options(
        self, field: Mapping[str, Any], initial: Any
    ) -> tuple[list[str], str]:
        labels: list[str] = []
        values: dict[str, Any] = {}
        selected = ""
        options = list(field.get("options", ()))
        if not field.get("required") and "" not in options:
            options.insert(0, "")
        if initial not in options and initial not in (None, ""):
            options.append(initial)
        for option in options:
            base = "None" if option == "" else str(option)
            label = base
            suffix = 2
            while label in values:
                label = f"{base} ({suffix})"
                suffix += 1
            labels.append(label)
            values[label] = deepcopy(option)
            if self._same_id(option, initial):
                selected = label
        if not labels:
            labels = ["None"]
            values["None"] = ""
        self._select_values[str(field["key"])] = values
        return labels, selected or labels[0]

    def _font(self, key: str) -> ctk.CTkFont:
        font = self._font_cache.get(key)
        if font is None:
            font = ctk.CTkFont(**self.theme[key])
            self._font_cache[key] = font
        return font

    def _bind_change_tracking(self) -> None:
        for variable in [*self._variables.values(), *self._list_drafts.values(), self._column_var]:
            variable.trace_add("write", self._field_changed)
        for textbox in self._textboxes.values():
            textbox.bind("<<Modified>>", self._textbox_changed, add="+")

    def _field_changed(self, *_args: Any) -> None:
        if not self._tracking_changes or self._dirty_after_id is not None:
            return
        # Keep the expensive full-form comparison coalesced, but make the
        # primary action responsive immediately.  CTkButton.invoke() ignores
        # disabled buttons, so waiting for idle here can otherwise drop a
        # rapid edit-then-save interaction.
        if hasattr(self, "save_button"):
            self.save_button.configure(state="normal")
        try:
            self._dirty_after_id = self.after_idle(self._apply_queued_dirty_state)
        except tk.TclError:
            self._dirty_after_id = None

    def _apply_queued_dirty_state(self) -> None:
        self._dirty_after_id = None
        if not self._destroying:
            self._update_dirty_state()

    def _textbox_changed(self, event: Any = None) -> None:
        textbox = getattr(event, "widget", None)
        if textbox is not None and textbox.edit_modified():
            textbox.edit_modified(False)
            self._field_changed()

    def _update_dirty_state(self) -> None:
        if not hasattr(self, "save_button"):
            return
        has_draft = any(variable.get().strip() for variable in self._list_drafts.values())
        dirty = has_draft or self._snapshot_values() != self._baseline
        if dirty == self._dirty_state:
            if dirty:
                self.error_label.grid_remove()
            return
        self._dirty_state = dirty
        self.save_button.configure(state="normal" if dirty else "disabled")
        self.status_label.configure(
            text="Unsaved changes" if dirty else "No changes yet",
            text_color=self.theme["accent_color"] if dirty else self.theme["muted_text_color"],
        )
        if dirty:
            self.error_label.grid_remove()

    def _snapshot_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in self.fields:
            key = str(field["key"])
            field_type = field["type"]
            if key in self._textboxes:
                result[key] = self._textboxes[key].get("1.0", "end-1c").strip()
            elif key in self._list_values:
                result[key] = deepcopy(self._list_values[key])
            elif key in self._variables:
                raw = self._variables[key].get()
                if field_type == "select":
                    raw = self._select_values[key].get(str(raw), raw)
                elif field_type != "checkbox":
                    raw = str(raw).strip()
                result[key] = deepcopy(raw)
            elif key in self._initial:
                result[key] = deepcopy(self._initial[key])
            elif "default" in field:
                result[key] = deepcopy(field["default"])
        result["column"] = self._column_values.get(self._column_var.get())
        return result

    def _render_list_field(self, key: str) -> None:
        frame = self._list_frames[key]
        for child in frame.winfo_children():
            child.destroy()
        self._native_pill_buttons = [
            (button, color)
            for button, color in self._native_pill_buttons
            if button.winfo_exists()
        ]
        values = self._list_values[key]
        if not values:
            self._make_label(
                frame,
                text="No values added",
                anchor="w",
                text_color=self.theme["muted_text_color"],
                font=self._font("help_text_font"),
            ).grid(row=0, column=0, sticky="w")
            return
        palette = self.theme["tag_pill_colors"]
        for index, item in enumerate(values):
            text = str(item)
            prefix = "#" if self._field_type(key) == "tags" else ""
            color = palette[index % len(palette)]
            button = tk.Button(
                frame,
                text=f"{prefix}{text}  ×",
                width=max(6, len(text) + 4),
                borderwidth=0,
                highlightthickness=0,
                relief="flat",
                cursor="hand2",
                padx=5,
                pady=2,
                background=self._apply_appearance_mode(color),
                foreground=self._apply_appearance_mode(self.theme["pill_text_color"]),
                activebackground=self._apply_appearance_mode(self.theme["danger_color"]),
                activeforeground=self._apply_appearance_mode(
                    self.theme["pill_text_color"]
                ),
                font=self._font("pill_font"),
                command=partial(self._remove_list_value, key, item),
            )
            self._native_pill_buttons.append((button, color))
            button.grid(
                row=index // 3,
                column=index % 3,
                padx=(0, 6),
                pady=(0, 6),
                sticky="w",
            )

    def _commit_list_field(self, key: str) -> None:
        draft = self._list_drafts[key].get()
        additions = self._normalise_list(draft, tags=self._field_type(key) == "tags")
        known = {str(item).casefold() for item in self._list_values[key]}
        for item in additions:
            if str(item).casefold() not in known:
                self._list_values[key].append(item)
                known.add(str(item).casefold())
        self._list_drafts[key].set("")
        self._render_list_field(key)
        self._update_dirty_state()

    def _remove_list_value(self, key: str, value: Any) -> None:
        self._list_values[key] = [item for item in self._list_values[key] if item != value]
        if key == "tags":
            self._tags = self._list_values[key]
        self._render_list_field(key)
        self._update_dirty_state()

    def _list_return(self, key: str) -> str:
        self._commit_list_field(key)
        return "break"

    # Backwards-compatible helpers used by existing integrations and tests.
    def _commit_tags(self) -> None:
        if "tags" in self._list_values:
            self._commit_list_field("tags")

    def _remove_tag(self, value: str) -> None:
        if "tags" in self._list_values:
            self._remove_list_value("tags", value)

    def _tag_return(self, _event: Any) -> str:
        return self._list_return("tags")

    def _field_type(self, key: str) -> str:
        return next(str(field["type"]) for field in self.fields if field["key"] == key)

    @staticmethod
    def _normalise_list(value: Any, *, tags: bool) -> list[Any]:
        if value is None:
            return []
        values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
        result: list[Any] = []
        for item in values:
            normalized = str(item).strip().lstrip("#") if tags else str(item).strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _normalise_tags(value: Any) -> list[str]:
        return [str(item) for item in CardEditor._normalise_list(value, tags=True)]

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _same_id(left: Any, right: Any) -> bool:
        if type(left) is not type(right):
            return False
        try:
            return bool(left == right)
        except (TypeError, ValueError):
            return False

    def _prepare_columns(
        self, columns: Sequence[Mapping[str, Any]], initial_id: Any
    ) -> tuple[list[str], str]:
        labels: list[str] = []
        selected = ""
        for column in columns:
            if "id" not in column:
                raise ValueError("Each column must define an 'id'.")
            column_id = column["id"]
            base = self._text(column.get("title")) or self._text(column_id)
            label = base
            suffix = 2
            while label in self._column_values:
                label = f"{base} ({suffix})"
                suffix += 1
            labels.append(label)
            self._column_values[label] = column_id
            if self._same_id(column_id, initial_id):
                selected = label
        if not labels:
            return ["No columns available"], "No columns available"
        return labels, selected or labels[0]

    def _activate(self) -> None:
        self._activate_after_id = None
        if not self.winfo_exists():
            return
        self.lift()
        widget = self._field_widgets.get("title")
        if widget is None:
            widget = next(iter(self._field_widgets.values()), None)
        if widget is not None:
            widget.focus_set()
            if isinstance(widget, ctk.CTkEntry):
                widget.icursor("end")

    def _slide_open(self) -> None:
        self._slide_after_id = None
        if not self.winfo_exists():
            return
        target = self._slide_target
        self._slide_x = max(target, self._slide_x - self.theme["editor_slide_step"])
        self.place_configure(x=self._slide_x)
        self.lift()
        if self._slide_x > target:
            self._slide_after_id = self.after(self.theme["editor_slide_interval_ms"], self._slide_open)

    def _bind_shortcuts(self) -> None:
        for sequence, callback in (
            ("<Return>", self._return_pressed),
            ("<Control-Return>", self._save_pressed),
            ("<Escape>", self._cancel_pressed),
        ):
            func_id = self._owner.bind(sequence, callback, add="+")
            if func_id:
                self._shortcut_bindings.append((sequence, func_id))

    def _inside_editor(self, widget: Any) -> bool:
        current = widget
        while current is not None:
            if current is self:
                return True
            current = getattr(current, "master", None)
        return False

    def _inside_textbox(self, widget: Any) -> bool:
        current = widget
        while current is not None:
            if current in self._textboxes.values():
                return True
            current = getattr(current, "master", None)
        return False

    def _inside_description(self, widget: Any) -> bool:
        return self._inside_textbox(widget)

    def _return_pressed(self, event: tk.Event[Any]) -> str | None:
        if not self._inside_editor(event.widget) or self._inside_textbox(event.widget):
            return None
        self.save()
        return "break"

    def _save_pressed(self, event: tk.Event[Any]) -> str | None:
        if not self._inside_editor(event.widget):
            return None
        self.save()
        return "break"

    def _cancel_pressed(self, event: tk.Event[Any]) -> str | None:
        if not self._inside_editor(event.widget):
            return None
        self.close()
        return "break"

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.error_label.grid()

    def save(self) -> None:
        if self._saving:
            return
        for key in self._list_values:
            self._commit_list_field(key)
        if not self._column_values:
            self._show_error("A column is required.")
            return
        data = self._snapshot_values()
        context = {**self._initial, **data}
        try:
            for field in self.fields:
                key = str(field["key"])
                if key in data:
                    data[key] = normalize_field_value(field, data[key], context)
                    context[key] = data[key]
        except ValueError as exc:
            self._show_error(str(exc))
            key = str(field["key"])
            widget = self._field_widgets.get(key)
            if widget is not None:
                widget.focus_set()
            return

        self._saving = True
        self.save_button.configure(state="disabled", text="Saving…")
        self.error_label.grid_remove()
        try:
            outcome = self._on_save(data)
        except Exception as exc:
            self._save_failed(str(exc) or "Could not save the card.")
            return
        if outcome is False:
            self._save_failed("Could not save the card.")
            return
        if isinstance(outcome, str):
            self._save_failed(outcome or "Could not save the card.")
            return
        self.close()

    def _save_failed(self, message: str) -> None:
        self._saving = False
        self.save_button.configure(state="normal", text="Save changes")
        self._show_error(message)

    def close(self) -> None:
        self.destroy()

    def destroy(self) -> None:
        """Cancel drawer callbacks and release window-level shortcuts."""

        if self._destroying:
            return
        self._destroying = True
        for after_id in (self._slide_after_id, self._activate_after_id):
            if after_id is None:
                continue
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._slide_after_id = None
        self._activate_after_id = None
        if self._dirty_after_id is not None:
            try:
                self.after_cancel(self._dirty_after_id)
            except tk.TclError:
                pass
            self._dirty_after_id = None
        for sequence, func_id in self._shortcut_bindings:
            try:
                self._owner.unbind(sequence, func_id)
            except tk.TclError:
                pass
        self._shortcut_bindings.clear()
        if hasattr(self, "form"):
            self.form.destroy()
        try:
            super().destroy()
        finally:
            if not self._close_notified and self._on_close is not None:
                self._close_notified = True
                self._on_close(self)
