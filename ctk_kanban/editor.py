"""Embedded, explicit-save editor used by the simplified board."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from typing import Any, Callable, Mapping

import customtkinter as ctk

SaveCallback = Callable[[dict[str, Any]], bool | str | None]


class CardEditor(ctk.CTkFrame):
    """Edit the five supported card fields in a right-side drawer."""

    PRIORITIES = ("None", "Low", "Medium", "High", "Critical")
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
    ) -> None:
        super().__init__(master, width=self.PANEL_WIDTH)
        self._initial = dict(initial)
        self._on_save = on_save
        self._on_close = on_close
        self._saving = False
        self._destroying = False
        self._close_notified = False
        self._column_values: dict[str, Any] = {}
        self._panel_width = self.PANEL_WIDTH
        self._slide_x = 0
        self._slide_after_id: str | None = None
        self._activate_after_id: str | None = None
        self._shortcut_bindings: list[tuple[str, str]] = []

        self._owner = master.winfo_toplevel()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 4))
        header.grid_columnconfigure(0, weight=1)
        heading = ctk.CTkLabel(
            header,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        heading.grid(row=0, column=0, sticky="ew")
        self.close_button = ctk.CTkButton(
            header,
            text="\u00d7",
            width=34,
            height=30,
            command=self.close,
        )
        self.close_button.grid(row=0, column=1, padx=(12, 0))
        subtitle = ctk.CTkLabel(
            self,
            text="Edit the details, then choose Save.",
            anchor="w",
        )
        subtitle.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 18))
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, sticky="nsew", padx=24)
        form.grid_columnconfigure((0, 1), weight=1)

        self.title_entry = self._entry_field(
            form, 0, "Title", self._text(initial.get("title")), "Card title"
        )
        self._label(form, "Description", row=2, columnspan=2)
        self.description_textbox = ctk.CTkTextbox(form, height=145, wrap="word")
        self.description_textbox.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.description_textbox.insert("1.0", self._text(initial.get("description")))
        priority = self._text(initial.get("priority")) or "None"
        priorities = list(self.PRIORITIES)
        if priority not in priorities:
            priorities.append(priority)
        self._priority_var = tk.StringVar(self, value=priority)
        self._label(form, "Priority", row=4, column=0)
        self.priority_menu = ctk.CTkOptionMenu(
            form, values=priorities, variable=self._priority_var, dynamic_resizing=False
        )
        self.priority_menu.grid(row=5, column=0, sticky="ew", padx=(0, 6), pady=(0, 14))
        column_labels, selected_column = self._prepare_columns(
            columns,
            initial.get("column", initial.get("column_id")),
        )
        self._column_var = tk.StringVar(self, value=selected_column)
        self._label(form, "Column", row=4, column=1)
        self.column_menu = ctk.CTkOptionMenu(
            form, values=column_labels, variable=self._column_var, dynamic_resizing=False
        )
        self.column_menu.grid(row=5, column=1, sticky="ew", padx=(6, 0), pady=(0, 14))
        if not self._column_values:
            self.column_menu.configure(state="disabled")
        self.tags_entry = self._entry_field(
            form, 6, "Tags", self._format_tags(initial.get("tags")), "design, urgent, client"
        )
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(10, 22))
        footer.grid_columnconfigure(0, weight=1)
        self.error_label = ctk.CTkLabel(
            footer, text="", anchor="w", wraplength=260, text_color=("#B91C1C", "#FCA5A5")
        )
        self.error_label.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.error_label.grid_remove()
        self.cancel_button = ctk.CTkButton(
            footer,
            text="Cancel",
            width=90,
            command=self.close,
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))
        self.save_button = ctk.CTkButton(footer, text="Save", width=90, command=self.save)
        self.save_button.grid(row=0, column=2)

        self._bind_shortcuts()
        self.place(relx=1.0, rely=0.0, x=0, relheight=1.0)
        self.lift()
        self._slide_after_id = self.after_idle(self._slide_open)
        self._activate_after_id = self.after(20, self._activate)

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _format_tags(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value)
        return str(value)

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

    @staticmethod
    def _label(master: Any, text: str, *, row: int, column: int = 0, columnspan: int = 1) -> None:
        label = ctk.CTkLabel(master, text=text, anchor="w")
        label.grid(row=row, column=column, columnspan=columnspan, sticky="ew", pady=(0, 5))

    def _entry_field(
        self, master: Any, row: int, label: str, value: str, placeholder: str
    ) -> ctk.CTkEntry:
        self._label(master, label, row=row, columnspan=2)
        entry = ctk.CTkEntry(master, placeholder_text=placeholder)
        entry.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        if value:
            entry.insert(0, value)
        return entry

    def _activate(self) -> None:
        self._activate_after_id = None
        if not self.winfo_exists():
            return
        self.lift()
        self.title_entry.focus_set()
        self.title_entry.icursor("end")

    def _slide_open(self) -> None:
        self._slide_after_id = None
        if not self.winfo_exists():
            return
        target = -self._panel_width
        self._slide_x = max(target, self._slide_x - 70)
        self.place_configure(x=self._slide_x)
        self.lift()
        if self._slide_x > target:
            self._slide_after_id = self.after(12, self._slide_open)

    def _bind_shortcuts(self) -> None:
        shortcuts = (
            ("<Return>", self._return_pressed),
            ("<Control-Return>", self._save_pressed),
            ("<Escape>", self._cancel_pressed),
        )
        for sequence, callback in shortcuts:
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

    def _inside_description(self, widget: Any) -> bool:
        current = widget
        while current is not None:
            if current is self.description_textbox:
                return True
            current = getattr(current, "master", None)
        return False

    def _return_pressed(self, event: tk.Event[Any]) -> str | None:
        if not self._inside_editor(event.widget) or self._inside_description(event.widget):
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
        title = self.title_entry.get().strip()
        if not title:
            self._show_error("Title is required.")
            self.title_entry.focus_set()
            return
        if not self._column_values:
            self._show_error("A column is required.")
            return

        priority = self._priority_var.get()
        data = dict(
            title=title,
            description=self.description_textbox.get("1.0", "end-1c").strip(),
            priority="" if priority == "None" else priority,
            tags=[tag.strip() for tag in self.tags_entry.get().split(",") if tag.strip()],
            column=self._column_values[self._column_var.get()],
        )
        self._saving = True
        self.save_button.configure(state="disabled", text="Saving...")
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
        self.save_button.configure(state="normal", text="Save")
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
        for sequence, func_id in self._shortcut_bindings:
            try:
                self._owner.unbind(sequence, func_id)
            except tk.TclError:
                pass
        self._shortcut_bindings.clear()
        try:
            super().destroy()
        finally:
            if not self._close_notified and self._on_close is not None:
                self._close_notified = True
                self._on_close(self)
