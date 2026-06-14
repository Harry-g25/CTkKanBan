"""Built-in card forms and filter dialogs."""

from __future__ import annotations

import tkinter as tk
from math import isfinite
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from .utils import clone, display_value, iter_widget_tree, parse_list_value
from .widgets import DateEntry


def _same_value(left: Any, right: Any) -> bool:
    """Compare option values without conflating values such as ``1`` and ``True``."""

    if type(left) is not type(right):
        return False
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False


def _unique_value_labels(values: list[Any], reserved: set[str] | None = None) -> dict[str, Any]:
    """Build stable, unique labels for values displayed by a string-only menu."""

    mapping: dict[str, Any] = {}
    unavailable = set(reserved or ())
    for value in values:
        base = str(value)
        label = base
        suffix = 2
        while label in mapping or label in unavailable:
            label = f"{base} ({suffix})"
            suffix += 1
        mapping[label] = value
    return mapping


def _entry_options(theme: dict[str, Any]) -> dict[str, Any]:
    return {
        "height": 40,
        "fg_color": theme["input_fg_color"],
        "border_color": theme["input_border_color"],
        "text_color": theme.get("input_text_color", theme["text_color"]),
        "placeholder_text_color": theme.get(
            "input_placeholder_text_color",
            theme.get("overlay_text_color", theme["text_color"]),
        ),
        "corner_radius": theme.get("input_corner_radius", theme["corner_radius"]),
        "border_width": theme.get("input_border_width", theme["border_width"]),
        "font": theme.get("input_font"),
    }


def _textbox_options(theme: dict[str, Any]) -> dict[str, Any]:
    return {
        "fg_color": theme["textbox_fg_color"],
        "border_color": theme["textbox_border_color"],
        "text_color": theme.get("textbox_text_color", theme["text_color"]),
        "corner_radius": theme.get("textbox_corner_radius", theme["corner_radius"]),
        "border_width": theme.get("textbox_border_width", theme["border_width"]),
        "scrollbar_button_color": theme["scrollbar_button_color"],
        "scrollbar_button_hover_color": theme["scrollbar_button_hover_color"],
        "font": theme.get("input_font"),
    }


def _checkbox_options(theme: dict[str, Any]) -> dict[str, Any]:
    return {
        "height": 28,
        "fg_color": theme["checkbox_fg_color"],
        "hover_color": theme["checkbox_hover_color"],
        "border_color": theme["checkbox_border_color"],
        "checkmark_color": theme["checkbox_checkmark_color"],
        "text_color": theme.get("checkbox_text_color", theme["text_color"]),
        "text_color_disabled": theme.get("checkbox_text_color_disabled"),
        "corner_radius": theme.get("checkbox_corner_radius", theme["corner_radius"]),
        "border_width": theme.get("checkbox_border_width", theme["border_width"]),
        "font": theme.get("checkbox_font") or theme.get("input_font"),
    }


def _optionmenu_options(theme: dict[str, Any]) -> dict[str, Any]:
    return {
        "height": 40,
        "fg_color": theme["optionmenu_fg_color"],
        "button_color": theme["optionmenu_button_color"],
        "button_hover_color": theme["optionmenu_button_hover_color"],
        "text_color": theme.get("optionmenu_text_color", theme["button_text_color"]),
        "text_color_disabled": theme.get("optionmenu_text_color_disabled"),
        "dropdown_fg_color": theme["optionmenu_dropdown_fg_color"],
        "dropdown_hover_color": theme["optionmenu_dropdown_hover_color"],
        "dropdown_text_color": theme["optionmenu_dropdown_text_color"],
        "corner_radius": theme.get("optionmenu_corner_radius", theme["corner_radius"]),
        "font": theme.get("optionmenu_font") or theme.get("input_font"),
        "dropdown_font": theme.get("menu_font") or theme.get("optionmenu_font") or theme.get("input_font"),
    }


class CardFormFrame(ctk.CTkFrame):
    """Reusable field-driven form used for creating and editing cards."""

    def __init__(
        self,
        master: Any,
        fields: list[dict[str, Any]],
        theme: dict[str, Any],
        *,
        title: str,
        initial_data: dict[str, Any] | None = None,
        on_submit: Callable[[dict[str, Any]], bool | str | None],
        on_close: Callable[[], None] | None = None,
        confirm_discard: bool = True,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", theme["dialog_fg_color"])
        kwargs.setdefault("border_color", theme["dialog_border_color"])
        kwargs.setdefault("border_width", theme.get("dialog_border_width", theme["border_width"]))
        kwargs.setdefault("corner_radius", theme.get("dialog_corner_radius", theme["corner_radius"]))
        super().__init__(master, **kwargs)
        self.fields = fields
        self.theme = theme
        self.initial_data = clone(initial_data) if initial_data is not None else {}
        self.on_submit = on_submit
        self.on_close = on_close
        self.confirm_discard = confirm_discard
        self._submitted = False
        self._fields_by_key = {field["key"]: field for field in fields}
        self.controls: dict[str, Any] = {}
        self.variables: dict[str, Any] = {}
        self.option_maps: dict[str, dict[str, Any]] = {}
        self.field_error_labels: dict[str, ctk.CTkLabel] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        heading = ctk.CTkLabel(
            self,
            text=title,
            anchor="w",
            font=theme.get("form_title_font") or ctk.CTkFont(size=20, weight="bold"),
            text_color=theme.get("panel_title_text_color", theme.get("dialog_title_text_color", theme["text_color"])),
        )
        heading.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))

        self.form = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=theme["scrollbar_button_color"],
            scrollbar_button_hover_color=theme["scrollbar_button_hover_color"],
        )
        self.form.grid(row=1, column=0, sticky="nsew", padx=14)
        self.form.grid_columnconfigure(0, weight=1)
        self._build_fields()

        self.error_label = ctk.CTkLabel(self, text="", text_color=theme["danger_color"], anchor="w")
        self.error_label.grid(row=2, column=0, sticky="ew", padx=22)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="e", padx=18, pady=(7, 18))
        self.cancel_button = ctk.CTkButton(
            actions,
            text="Cancel",
            width=90,
            height=38,
            fg_color=theme["secondary_button_fg_color"],
            hover_color=theme["secondary_button_hover_color"],
            text_color=theme.get("secondary_button_text_color", theme["text_color"]),
            text_color_disabled=theme.get("secondary_button_text_color_disabled"),
            corner_radius=theme.get("secondary_button_corner_radius", theme["button_corner_radius"]),
            border_width=theme.get("secondary_button_border_width", theme["button_border_width"]),
            font=theme.get("secondary_button_font") or theme.get("button_font"),
            command=self._close,
        )
        self.cancel_button.pack(side="left", padx=5)
        self.save_button = ctk.CTkButton(
            actions,
            text="Save",
            width=90,
            height=38,
            fg_color=theme["button_fg_color"],
            hover_color=theme["button_hover_color"],
            text_color=theme.get("button_text_color"),
            text_color_disabled=theme.get("button_text_color_disabled"),
            corner_radius=theme.get("button_corner_radius", theme["corner_radius"]),
            border_width=theme.get("button_border_width", theme["border_width"]),
            font=theme.get("button_font"),
            command=self._submit,
        )
        self.save_button.pack(side="left", padx=5)
        for widget in iter_widget_tree(self):
            widget.bind("<Escape>", self._on_escape, add="+")

    def _on_escape(self, _event: Any) -> str:
        self._close()
        return "break"

    def focus_first_control(self) -> None:
        """Move keyboard focus to the first editable control."""

        for key, control in self.controls.items():
            field = self._fields_by_key.get(key)
            if field is not None and not field.get("read_only"):
                control.focus_set()
                return

    def _build_fields(self) -> None:
        row = 0
        for field in self.fields:
            if not field.get("show_in_form") or field.get("type") == "hidden":
                continue
            key = field["key"]
            label_text = field["label"] + (" *" if field.get("required") else "")
            ctk.CTkLabel(
                self.form,
                text=label_text,
                anchor="w",
                font=self.theme.get("form_label_font"),
                text_color=self.theme.get("dialog_text_color", self.theme["text_color"]),
            ).grid(
                row=row, column=0, sticky="ew", padx=8, pady=(11, 4)
            )
            row += 1
            value = self.initial_data.get(key, field.get("default"))
            field_type = field.get("type", "text")
            state = "disabled" if field.get("read_only") else "normal"

            if field_type == "textarea":
                control = ctk.CTkTextbox(self.form, height=95, **_textbox_options(self.theme))
                if value not in (None, ""):
                    control.insert("1.0", display_value(value))
                control.configure(state=state)
            elif field_type == "checkbox":
                variable = ctk.BooleanVar(value=bool(value))
                control = ctk.CTkCheckBox(
                    self.form,
                    text=str(field.get("checkbox_text") or field["label"]),
                    variable=variable,
                    **_checkbox_options(self.theme),
                )
                self.variables[key] = variable
                if state == "disabled":
                    control.configure(state="disabled")
            elif field_type == "select":
                options = list(field.get("options") or [])
                mapping = {str(option): option for option in options}
                mapping[""] = ""
                self.option_maps[key] = mapping
                variable = ctk.StringVar(value="" if value is None else str(value))
                control = ctk.CTkOptionMenu(
                    self.form,
                    values=list(mapping),
                    variable=variable,
                    **_optionmenu_options(self.theme),
                )
                self.variables[key] = variable
                if state == "disabled":
                    control.configure(state="disabled")
            elif field_type == "date":
                control = DateEntry(
                    self.form,
                    value=value,
                    placeholder_text=str(field.get("placeholder") or "YYYY-MM-DD"),
                    **_entry_options(self.theme),
                )
                control.configure(state=state)
            else:
                control = ctk.CTkEntry(
                    self.form,
                    placeholder_text=str(field.get("placeholder") or ""),
                    **_entry_options(self.theme),
                )
                if value not in (None, ""):
                    control.insert(0, display_value(value))
                control.configure(state=state)
            control.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 5))
            self.controls[key] = control
            row += 1
            if field.get("help_text"):
                ctk.CTkLabel(
                    self.form,
                    text=str(field["help_text"]),
                    anchor="w",
                    text_color=self.theme.get("muted_text_color", self.theme["text_color"]),
                    font=self.theme.get("card_metadata_font"),
                ).grid(row=row, column=0, sticky="ew", padx=8)
                row += 1
            error_label = ctk.CTkLabel(
                self.form,
                text="",
                anchor="w",
                text_color=self.theme["danger_color"],
            )
            error_label.grid(row=row, column=0, sticky="ew", padx=8)
            self.field_error_labels[key] = error_label
            row += 1

    def _collect_data(self) -> dict[str, Any]:
        result = dict(self.initial_data)
        for field in self.fields:
            key = field["key"]
            if key not in self.controls or field.get("read_only"):
                continue
            field_type = field.get("type", "text")
            control = self.controls[key]
            if field_type == "textarea":
                value: Any = control.get("1.0", "end-1c").strip()
            elif field_type == "checkbox":
                value = bool(self.variables[key].get())
            elif field_type == "select":
                selected = self.variables[key].get()
                value = self.option_maps[key].get(selected, selected)
            else:
                value = control.get().strip()

            if field_type == "number" and value != "":
                number = float(value)
                if not isfinite(number):
                    raise ValueError(f"{field['label']} must be finite")
                value = int(number) if number.is_integer() else number
            elif field_type in {"tags", "multiselect"}:
                value = parse_list_value(value)
            if value == "" and not field.get("required"):
                value = clone(field.get("empty_value"))
            result[key] = value
        return result

    def _clear_errors(self) -> None:
        self.error_label.configure(text="")
        for label in self.field_error_labels.values():
            label.configure(text="")

    def _show_error(self, error: Exception) -> None:
        message = str(error).strip() or error.__class__.__name__
        self.error_label.configure(text=message)
        for field in self.fields:
            if str(field["label"]).casefold() in message.casefold():
                key = field["key"]
                self.field_error_labels.get(key, self.error_label).configure(text=message)
                control = self.controls.get(key)
                if control is not None:
                    control.focus_set()
                return

    def is_dirty(self) -> bool:
        """Return whether editable controls differ from their opening values."""

        try:
            current = self._collect_data()
        except Exception:
            return True
        for field in self.fields:
            key = field["key"]
            if key not in self.controls or field.get("read_only"):
                continue
            opening = self.initial_data.get(key, field.get("default"))
            current_value = current.get(key)
            if opening in (None, "", []) and current_value in (None, "", []):
                continue
            if opening != current_value:
                return True
        return False

    def _submit(self) -> None:
        self._clear_errors()
        self.save_button.configure(state="disabled", text="Saving...")
        try:
            data = self._collect_data()
            outcome = self.on_submit(data)
        except Exception as exc:
            self._show_error(exc)
            self.save_button.configure(state="normal", text="Save")
            return
        if outcome is False:
            self.error_label.configure(text="The action was cancelled")
            self.save_button.configure(state="normal", text="Save")
            return
        if isinstance(outcome, str) and outcome:
            self.error_label.configure(text=outcome)
            self.save_button.configure(state="normal", text="Save")
            return
        self._submitted = True
        self._close()

    def _close(self) -> None:
        if self.confirm_discard and not self._submitted and self.is_dirty():
            discard = messagebox.askyesno(
                "Discard changes?",
                "You have unsaved changes. Discard them?",
                parent=self.winfo_toplevel(),
            )
            if not discard:
                return
            self._submitted = True
        if self.on_close is not None:
            self.on_close()
        elif self.winfo_exists():
            self.destroy()


class CardFormDialog(ctk.CTkToplevel):
    """Popup wrapper around :class:`CardFormFrame`."""

    def __init__(
        self,
        master: Any,
        fields: list[dict[str, Any]],
        theme: dict[str, Any],
        *,
        title: str,
        initial_data: dict[str, Any] | None = None,
        on_submit: Callable[[dict[str, Any]], bool | str | None],
        on_close: Callable[[], None] | None = None,
        confirm_discard: bool = True,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("520x650")
        self.minsize(430, 460)
        self.configure(fg_color=theme["dialog_fg_color"])
        self.transient(master.winfo_toplevel())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._on_close = on_close

        self.form_frame = CardFormFrame(
            self,
            fields,
            theme,
            title=title,
            initial_data=initial_data,
            on_submit=on_submit,
            on_close=self._close,
            confirm_discard=confirm_discard,
        )
        self.form_frame.grid(row=0, column=0, sticky="nsew")

        # Preserve the useful attributes exposed by the former dialog class.
        self.fields = self.form_frame.fields
        self.theme = self.form_frame.theme
        self.initial_data = self.form_frame.initial_data
        self.on_submit = self.form_frame.on_submit
        self.controls = self.form_frame.controls
        self.variables = self.form_frame.variables
        self.option_maps = self.form_frame.option_maps
        self.form = self.form_frame.form
        self.error_label = self.form_frame.error_label

        self.bind("<Escape>", lambda _event: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(20, self._activate)

    def _activate(self) -> None:
        if self.winfo_exists():
            self.grab_set()
            self.focus_force()
            self.form_frame.focus_first_control()

    def _collect_data(self) -> dict[str, Any]:
        return self.form_frame._collect_data()

    def _submit(self) -> None:
        self.form_frame._submit()

    def _close(self) -> None:
        if not self.winfo_exists():
            return
        if (
            self.form_frame.confirm_discard
            and not self.form_frame._submitted
            and self.form_frame.is_dirty()
        ):
            discard = messagebox.askyesno(
                "Discard changes?",
                "You have unsaved changes. Discard them?",
                parent=self,
            )
            if not discard:
                return
            self.form_frame._submitted = True
        try:
            if self.grab_current() == self:
                self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if self._on_close is not None:
            self._on_close()


class FilterDialog(ctk.CTkToplevel):
    """Simple exact-value filter editor generated from filterable fields."""

    ANY = "Any"

    def __init__(
        self,
        master: Any,
        fields: list[dict[str, Any]],
        cards: list[dict[str, Any]],
        theme: dict[str, Any],
        *,
        current_filters: dict[str, Any] | None = None,
        on_apply: Callable[[dict[str, Any]], bool | str | None],
    ) -> None:
        super().__init__(master)
        self.title("Filter cards")
        self.geometry("420x520")
        self.minsize(360, 360)
        self.configure(fg_color=theme["dialog_fg_color"])
        self.transient(master.winfo_toplevel())
        self.fields = fields
        self.cards = cards
        self.current_filters = current_filters or {}
        self.on_apply = on_apply
        self.variables: dict[str, ctk.StringVar] = {}
        self.value_maps: dict[str, dict[str, Any]] = {}
        self.any_labels: dict[str, str] = {}
        self.operator_vars: dict[str, ctk.StringVar] = {}
        self.value_controls: dict[str, Any] = {}
        self.field_types: dict[str, str] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            self,
            text="Filter cards",
            font=theme.get("filter_title_font") or ctk.CTkFont(size=19, weight="bold"),
            text_color=theme.get("dialog_title_text_color", theme["text_color"]),
            anchor="w",
        ).grid(
            row=0, column=0, sticky="ew", padx=20, pady=(18, 8)
        )
        body = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=theme["scrollbar_button_color"],
            scrollbar_button_hover_color=theme["scrollbar_button_hover_color"],
        )
        body.grid(row=1, column=0, sticky="nsew", padx=12)
        body.grid_columnconfigure(0, weight=1)
        row = 0
        for field in fields:
            if not field.get("filterable"):
                continue
            key = field["key"]
            field_type = str(field.get("type", "text"))
            self.field_types[key] = field_type
            raw_values: list[Any] = []
            for card in cards:
                value = card.get(key)
                candidates = value if isinstance(value, (list, tuple, set)) else [value]
                for candidate in candidates:
                    if candidate not in (None, "") and not any(
                        _same_value(candidate, existing) for existing in raw_values
                    ):
                        raw_values.append(candidate)
            used_labels = {str(value) for value in raw_values}
            any_label = self.ANY
            if any_label in used_labels:
                any_label = f"{self.ANY} (no filter)"
            suffix = 2
            while any_label in used_labels:
                any_label = f"{self.ANY} (no filter {suffix})"
                suffix += 1
            mapping = {any_label: None}
            mapping.update(_unique_value_labels(raw_values, {any_label}))
            self.value_maps[key] = mapping
            self.any_labels[key] = any_label
            current_filter = self.current_filters.get(key)
            current_operator = "eq"
            current = current_filter
            if isinstance(current_filter, dict) and "op" in current_filter:
                current_operator = str(current_filter["op"])
                current = current_filter.get("value")
            current_label = any_label
            if key in self.current_filters and current_operator == "eq":
                current_label = next(
                    (
                        label
                        for label, mapped_value in mapping.items()
                        if label != any_label and _same_value(current, mapped_value)
                    ),
                    any_label,
                )
            variable = ctk.StringVar(value=current_label)
            self.variables[key] = variable
            ctk.CTkLabel(
                body,
                text=field["label"],
                anchor="w",
                text_color=theme.get("dialog_text_color", theme["text_color"]),
                font=theme.get("form_label_font"),
            ).grid(
                row=row,
                column=0,
                sticky="ew",
                padx=8,
                pady=(8, 2),
            )
            row += 1
            operator_labels = {
                "Any": "any",
                "Is": "eq",
                "Is not": "ne",
                "Contains": "contains",
                "Does not contain": "not_contains",
                "Is any of": "in",
                "Greater than": "gt",
                "At least": "gte",
                "Less than": "lt",
                "At most": "lte",
                "Between": "between",
                "Is empty": "empty",
                "Is not empty": "not_empty",
            }
            if field_type in {"number", "date", "datetime"}:
                available_operators = [
                    "Any", "Is", "Is not", "Greater than", "At least",
                    "Less than", "At most", "Between", "Is empty", "Is not empty",
                ]
            elif field_type in {"select", "badge", "checkbox"}:
                available_operators = ["Any", "Is", "Is not", "Is any of", "Is empty", "Is not empty"]
            else:
                available_operators = ["Any", "Is", "Is not", "Contains", "Does not contain", "Is empty", "Is not empty"]
            current_operator_label = next(
                (label for label, operator in operator_labels.items() if operator == current_operator),
                "Is" if key in self.current_filters else "Any",
            )
            operator_variable = ctk.StringVar(value=current_operator_label)
            self.operator_vars[key] = operator_variable
            ctk.CTkOptionMenu(
                body,
                values=available_operators,
                variable=operator_variable,
                **_optionmenu_options(theme),
            ).grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 4))
            row += 1
            if field_type in {"select", "badge", "checkbox"}:
                value_control = ctk.CTkOptionMenu(
                    body,
                    values=list(mapping),
                    variable=variable,
                    **_optionmenu_options(theme),
                )
            else:
                value_control = ctk.CTkEntry(
                    body,
                    placeholder_text="Use comma-separated values for Between",
                    **_entry_options(theme),
                )
                if current not in (None, ""):
                    if isinstance(current, (list, tuple, set)):
                        value_control.insert(0, ", ".join(str(item) for item in current))
                    else:
                        value_control.insert(0, str(current))
            value_control.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 4))
            self.value_controls[key] = value_control
            row += 1

        self.overdue_var = ctk.BooleanVar(value=bool(self.current_filters.get("overdue_only")))
        ctk.CTkCheckBox(
            body,
            text="Overdue only",
            variable=self.overdue_var,
            **_checkbox_options(theme),
        ).grid(
            row=row, column=0, sticky="w", padx=8, pady=12
        )

        self.error_label = ctk.CTkLabel(
            self,
            text="",
            text_color=theme["danger_color"],
            anchor="w",
        )
        self.error_label.grid(row=2, column=0, sticky="ew", padx=22)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="e", padx=18, pady=15)
        ctk.CTkButton(
            actions,
            text="Clear",
            width=80,
            fg_color=theme["secondary_button_fg_color"],
            hover_color=theme["secondary_button_hover_color"],
            text_color=theme.get("secondary_button_text_color", theme["text_color"]),
            text_color_disabled=theme.get("secondary_button_text_color_disabled"),
            corner_radius=theme.get("secondary_button_corner_radius", theme["button_corner_radius"]),
            border_width=theme.get("secondary_button_border_width", theme["button_border_width"]),
            font=theme.get("secondary_button_font") or theme.get("button_font"),
            command=self._clear,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Apply",
            width=80,
            fg_color=theme["button_fg_color"],
            hover_color=theme["button_hover_color"],
            text_color=theme.get("button_text_color"),
            text_color_disabled=theme.get("button_text_color_disabled"),
            corner_radius=theme.get("button_corner_radius", theme["corner_radius"]),
            border_width=theme.get("button_border_width", theme["border_width"]),
            font=theme.get("button_font"),
            command=self._apply,
        ).pack(side="left", padx=4)
        self.bind("<Escape>", lambda _event: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(20, self._activate)

    def _activate(self) -> None:
        if self.winfo_exists():
            self.grab_set()
            self.focus_force()

    def _apply(self) -> None:
        filters: dict[str, Any] = {}
        operator_map = {
            "Is": "eq",
            "Is not": "ne",
            "Contains": "contains",
            "Does not contain": "not_contains",
            "Is any of": "in",
            "Greater than": "gt",
            "At least": "gte",
            "Less than": "lt",
            "At most": "lte",
            "Between": "between",
            "Is empty": "empty",
            "Is not empty": "not_empty",
        }
        for key, operator_variable in self.operator_vars.items():
            operator_label = operator_variable.get()
            if operator_label == "Any":
                continue
            operator = operator_map[operator_label]
            field_type = self.field_types[key]
            if operator in {"empty", "not_empty"}:
                value: Any = None
            elif field_type in {"select", "badge", "checkbox"}:
                selected = self.variables[key].get()
                value = self.value_maps[key].get(selected, selected)
            else:
                value = self.value_controls[key].get().strip()
            if operator in {"between", "in"}:
                value = [item.strip() for item in str(value).split(",") if item.strip()]
            if field_type == "number":
                if isinstance(value, list):
                    value = [float(item) for item in value]
                elif value not in (None, ""):
                    value = float(value)
            filters[key] = {"op": operator, "value": value}
        if self.overdue_var.get():
            filters["overdue_only"] = True
        self._finish(filters)

    def _clear(self) -> None:
        self._finish({})

    def _finish(self, filters: dict[str, Any]) -> None:
        try:
            outcome = self.on_apply(filters)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.error_label.configure(text=message)
            return
        if outcome is False:
            self.error_label.configure(text="The action was cancelled")
            return
        if isinstance(outcome, str) and outcome:
            self.error_label.configure(text=outcome)
            return
        self._close()

    def _close(self) -> None:
        if not self.winfo_exists():
            return
        try:
            if self.grab_current() == self:
                self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
