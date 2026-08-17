"""Embedded, explicit-save card inspector."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from typing import Any, Callable, Mapping

import customtkinter as ctk

from ._scrolling import ManagedScrollableFrame
from .themes import merge_theme

SaveCallback = Callable[[dict[str, Any]], bool | str | None]


class CardEditor(ctk.CTkFrame):
    """Edit the supported card fields in a structured right-side drawer."""

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
        theme: Mapping[str, Any] | None = None,
    ) -> None:
        self.theme = merge_theme(theme)
        super().__init__(
            master,
            width=self.PANEL_WIDTH,
            corner_radius=0,
            fg_color=self.theme["editor_fg_color"],
            border_width=1,
            border_color=self.theme["divider_color"],
        )
        self.grid_propagate(False)
        self._initial = dict(initial)
        self._on_save = on_save
        self._on_close = on_close
        self._saving = False
        self._destroying = False
        self._close_notified = False
        self._tracking_changes = False
        self._column_values: dict[str, Any] = {}
        self._slide_x = 0
        self._slide_after_id: str | None = None
        self._activate_after_id: str | None = None
        self._shortcut_bindings: list[tuple[str, str]] = []
        self._tags = self._normalise_tags(initial.get("tags"))

        self._owner = master.winfo_toplevel()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header(title)

        ctk.CTkFrame(self, height=1, fg_color=self.theme["divider_color"]).grid(
            row=1,
            column=0,
            sticky="ew",
        )
        self.form: Any = ManagedScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=self.theme["scrollbar_color"],
            scrollbar_button_hover_color=self.theme["scrollbar_hover_color"],
        )
        self.form.grid(row=2, column=0, sticky="nsew", padx=(18, 10), pady=(16, 8))
        self.form.grid_columnconfigure(0, weight=1)
        if hasattr(self.form, "_scrollbar"):
            self.form._scrollbar.configure(width=7)

        self._build_details_section(initial)
        self._build_organisation_section(initial, columns)
        self._build_footer()

        self._baseline = self._snapshot_values()
        self._bind_change_tracking()
        self._tracking_changes = True
        self._update_dirty_state()
        self._bind_shortcuts()

        self.place(relx=1.0, rely=0.0, x=0, relheight=1.0)
        self.lift()
        self._slide_after_id = self.after_idle(self._slide_open)
        self._activate_after_id = self.after(20, self._activate)

    def _build_header(self, title: str) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(17, 15))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="CARD DETAILS",
            anchor="w",
            text_color=self.theme["accent_color"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).grid(row=0, column=0, sticky="ew")

        heading_row = ctk.CTkFrame(header, height=1, fg_color="transparent")
        heading_row.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ctk.CTkLabel(
            heading_row,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=21, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            heading_row,
            text="NEW" if title.casefold().startswith("add") else "EDITING",
            height=21,
            corner_radius=7,
            fg_color=self.theme["count_fg_color"],
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(size=9, weight="bold"),
        ).pack(side="left", padx=(9, 0))

        self.close_button = ctk.CTkButton(
            header,
            text="×",
            width=32,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self.close,
        )
        self.close_button.grid(row=0, column=1, rowspan=2, padx=(12, 0))

    def _build_details_section(self, initial: Mapping[str, Any]) -> None:
        section = self._section(self.form, row=0, title="Details")
        section.grid_columnconfigure(0, weight=1)

        self._label(section, "Title", row=1)
        self._title_var = tk.StringVar(self, value=self._text(initial.get("title")))
        self.title_entry = ctk.CTkEntry(
            section,
            textvariable=self._title_var,
            placeholder_text="Card title",
            height=36,
            border_color=self.theme["input_border_color"],
        )
        self.title_entry.grid(row=2, column=0, sticky="ew", pady=(0, 13))
        self.title_entry.grid_configure(padx=14)

        self._label(section, "Description", row=3)
        self.description_textbox = ctk.CTkTextbox(
            section,
            height=105,
            wrap="word",
            border_width=1,
            border_color=self.theme["input_border_color"],
        )
        self.description_textbox.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.description_textbox.insert("1.0", self._text(initial.get("description")))
        self.description_textbox.edit_modified(False)

    def _build_organisation_section(
        self,
        initial: Mapping[str, Any],
        columns: Sequence[Mapping[str, Any]],
    ) -> None:
        section = self._section(self.form, row=1, title="Organisation")
        section.grid_columnconfigure((0, 1), weight=1)

        priority = self._text(initial.get("priority")) or "None"
        priorities = list(self.PRIORITIES)
        if priority not in priorities:
            priorities.append(priority)
        self._priority_var = tk.StringVar(self, value=priority)
        self._label(section, "Priority", row=1, column=0)
        self.priority_menu = ctk.CTkOptionMenu(
            section,
            values=priorities,
            variable=self._priority_var,
            dynamic_resizing=False,
            height=36,
        )
        self.priority_menu.grid(row=2, column=0, sticky="ew", padx=(14, 6), pady=(0, 13))

        column_labels, selected_column = self._prepare_columns(
            columns,
            initial.get("column", initial.get("column_id")),
        )
        self._column_var = tk.StringVar(self, value=selected_column)
        self._label(section, "Column", row=1, column=1)
        self.column_menu = ctk.CTkOptionMenu(
            section,
            values=column_labels,
            variable=self._column_var,
            dynamic_resizing=False,
            height=36,
        )
        self.column_menu.grid(row=2, column=1, sticky="ew", padx=(6, 14), pady=(0, 13))
        if not self._column_values:
            self.column_menu.configure(state="disabled")

        self._label(section, "Tags", row=3, columnspan=2)
        self.tags_frame = ctk.CTkFrame(section, height=1, fg_color="transparent")
        self.tags_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14)
        self._render_tags()

        tag_input = ctk.CTkFrame(section, height=1, fg_color="transparent")
        tag_input.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(8, 14),
        )
        tag_input.grid_columnconfigure(0, weight=1)
        self._tag_var = tk.StringVar(self)
        self.tags_entry = ctk.CTkEntry(
            tag_input,
            textvariable=self._tag_var,
            placeholder_text="Type a tag",
            height=34,
            border_color=self.theme["input_border_color"],
        )
        self.tags_entry.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.tags_entry.bind("<Return>", self._tag_return, add="+")
        self.add_tag_button = ctk.CTkButton(
            tag_input,
            text="Add",
            width=58,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme["column_border_color"],
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
            command=self._commit_tags,
        )
        self.add_tag_button.grid(row=0, column=1)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(
            self,
            fg_color=self.theme["editor_fg_color"],
            corner_radius=0,
        )
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(footer, height=1, fg_color=self.theme["divider_color"]).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        self.error_label = ctk.CTkLabel(
            footer,
            text="",
            anchor="w",
            wraplength=370,
            text_color=("#B91C1C", "#FCA5A5"),
        )
        self.error_label.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(9, 0))
        self.error_label.grid_remove()

        self.status_label = ctk.CTkLabel(
            footer,
            text="",
            anchor="w",
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(size=11),
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=(20, 8), pady=(13, 18))
        self.cancel_button = ctk.CTkButton(
            footer,
            text="Cancel",
            width=80,
            height=36,
            corner_radius=8,
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
            height=36,
            corner_radius=8,
            command=self.save,
        )
        self.save_button.grid(row=2, column=2, padx=(0, 20), pady=(13, 18))

    def _section(self, master: Any, *, row: int, title: str) -> ctk.CTkFrame:
        section = ctk.CTkFrame(
            master,
            height=1,
            fg_color=self.theme["editor_section_fg_color"],
            border_width=1,
            border_color=self.theme["divider_color"],
            corner_radius=10,
        )
        section.grid(row=row, column=0, sticky="ew", pady=(0, 12), padx=(0, 2))
        ctk.CTkLabel(
            section,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(14, 12))
        for child in section.grid_slaves(row=0):
            child.grid_configure(padx=14)
        return section

    @staticmethod
    def _label(
        master: Any,
        text: str,
        *,
        row: int,
        column: int = 0,
        columnspan: int = 1,
    ) -> None:
        ctk.CTkLabel(
            master,
            text=text,
            anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="ew",
            padx=(14, 7) if column == 0 else (7, 14),
            pady=(0, 5),
        )

    def _bind_change_tracking(self) -> None:
        for variable in (
            self._title_var,
            self._tag_var,
            self._priority_var,
            self._column_var,
        ):
            variable.trace_add("write", self._field_changed)
        self.description_textbox.bind("<<Modified>>", self._description_changed, add="+")

    def _field_changed(self, *_args: Any) -> None:
        if self._tracking_changes:
            self._update_dirty_state()

    def _description_changed(self, _event: Any = None) -> None:
        if self.description_textbox.edit_modified():
            self.description_textbox.edit_modified(False)
            self._field_changed()

    def _update_dirty_state(self) -> None:
        if not hasattr(self, "save_button"):
            return
        dirty = bool(self._tag_var.get().strip()) or self._snapshot_values() != self._baseline
        self.save_button.configure(state="normal" if dirty else "disabled")
        self.status_label.configure(
            text="Unsaved changes" if dirty else "No changes yet",
            text_color=(
                self.theme["accent_color"] if dirty else self.theme["muted_text_color"]
            ),
        )
        if dirty:
            self.error_label.grid_remove()

    def _snapshot_values(self) -> dict[str, Any]:
        priority = self._priority_var.get()
        column_label = self._column_var.get()
        return {
            "title": self._title_var.get().strip(),
            "description": self.description_textbox.get("1.0", "end-1c").strip(),
            "priority": "" if priority == "None" else priority,
            "tags": list(self._tags),
            "column": self._column_values.get(column_label),
        }

    def _render_tags(self) -> None:
        for child in self.tags_frame.winfo_children():
            child.destroy()
        if not self._tags:
            ctk.CTkLabel(
                self.tags_frame,
                text="No tags added",
                anchor="w",
                text_color=self.theme["muted_text_color"],
                font=ctk.CTkFont(size=11),
            ).grid(row=0, column=0, sticky="w")
            return
        for index, tag in enumerate(self._tags):
            ctk.CTkButton(
                self.tags_frame,
                text=f"#{tag}  ×",
                width=max(58, 28 + len(tag) * 7),
                height=26,
                corner_radius=8,
                fg_color=self.theme["tag_pill_colors"][index % len(self.theme["tag_pill_colors"])],
                hover_color=self.theme["danger_color"],
                text_color=self.theme["pill_text_color"],
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda value=tag: self._remove_tag(value),
            ).grid(row=index // 3, column=index % 3, padx=(0, 6), pady=(0, 6), sticky="w")

    def _commit_tags(self) -> None:
        draft = self._tag_var.get()
        additions = self._normalise_tags(draft)
        known = {tag.casefold() for tag in self._tags}
        for tag in additions:
            if tag.casefold() not in known:
                self._tags.append(tag)
                known.add(tag.casefold())
        self._tag_var.set("")
        self._render_tags()
        self._update_dirty_state()

    def _remove_tag(self, value: str) -> None:
        self._tags = [tag for tag in self._tags if tag != value]
        self._render_tags()
        self._update_dirty_state()

    def _tag_return(self, _event: Any) -> str:
        self._commit_tags()
        return "break"

    @staticmethod
    def _normalise_tags(value: Any) -> list[str]:
        if value is None:
            return []
        values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
        return [str(item).strip().lstrip("#") for item in values if str(item).strip().lstrip("#")]

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
        self,
        columns: Sequence[Mapping[str, Any]],
        initial_id: Any,
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
        self.title_entry.focus_set()
        self.title_entry.icursor("end")

    def _slide_open(self) -> None:
        self._slide_after_id = None
        if not self.winfo_exists():
            return
        target = -self.winfo_reqwidth()
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
        self._commit_tags()
        title = self.title_entry.get().strip()
        if not title:
            self._show_error("Title is required.")
            self.title_entry.focus_set()
            return
        if not self._column_values:
            self._show_error("A column is required.")
            return

        data = self._snapshot_values()
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
