"""Small reusable widgets that do not belong to the board controller."""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from typing import Any

import customtkinter as ctk


class Tooltip:
    """Lightweight hover tooltip for compact icon controls."""

    def __init__(self, widget: Any, text: str, *, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._queue, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _queue(self, _event: Any = None) -> None:
        self.hide()
        self._after_id = self.widget.after(self.delay_ms, self.show)

    def show(self) -> None:
        self._after_id = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        label = tk.Label(
            window,
            text=self.text,
            background="#202124",
            foreground="#FFFFFF",
            relief="solid",
            borderwidth=1,
            padx=7,
            pady=4,
        )
        label.pack()
        window.geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 4}")
        self._window = window

    def hide(self, _event: Any = None) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except (ValueError, tk.TclError):
                pass
            self._after_id = None
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


class DateEntry(ctk.CTkFrame):
    """ISO date entry with a dependency-free calendar picker."""

    def __init__(self, master: Any, *, value: Any = None, **entry_options: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(self, **entry_options)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.button = ctk.CTkButton(self, text="Pick date", width=76, command=self._open_picker)
        self.button.grid(row=0, column=1, padx=(6, 0))
        if value not in (None, ""):
            self.entry.insert(0, str(value)[:10])
        self._picker: ctk.CTkToplevel | None = None
        self._year = date.today().year
        self._month = date.today().month

    def get(self) -> str:
        return self.entry.get()

    def insert(self, index: Any, value: Any) -> None:
        self.entry.insert(index, value)

    def delete(self, first: Any, last: Any = None) -> None:
        self.entry.delete(first, last)

    def focus_set(self) -> None:
        self.entry.focus_set()

    def configure(self, **kwargs: Any) -> None:
        state = kwargs.pop("state", None)
        if state is not None and hasattr(self, "entry"):
            self.entry.configure(state=state)
            self.button.configure(state=state)
        if kwargs:
            super().configure(**kwargs)

    def _open_picker(self) -> None:
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.focus_force()
            return
        try:
            selected = date.fromisoformat(self.get().strip())
        except ValueError:
            selected = date.today()
        self._year, self._month = selected.year, selected.month
        self._picker = ctk.CTkToplevel(self)
        self._picker.title("Choose date")
        self._picker.transient(self.winfo_toplevel())
        self._picker.resizable(False, False)
        self._calendar = ctk.CTkFrame(self._picker)
        self._calendar.pack(padx=10, pady=10)
        self._render_month()

    def _render_month(self) -> None:
        for child in self._calendar.winfo_children():
            child.destroy()
        ctk.CTkButton(self._calendar, text="<", width=34, command=lambda: self._change_month(-1)).grid(row=0, column=0)
        ctk.CTkLabel(
            self._calendar,
            text=f"{calendar.month_name[self._month]} {self._year}",
            width=190,
        ).grid(row=0, column=1, columnspan=5)
        ctk.CTkButton(self._calendar, text=">", width=34, command=lambda: self._change_month(1)).grid(row=0, column=6)
        for column, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            ctk.CTkLabel(self._calendar, text=name, width=34).grid(row=1, column=column, pady=3)
        for row, week in enumerate(calendar.monthcalendar(self._year, self._month), start=2):
            for column, day in enumerate(week):
                if day:
                    ctk.CTkButton(
                        self._calendar,
                        text=str(day),
                        width=34,
                        height=30,
                        command=lambda selected_day=day: self._select(selected_day),
                    ).grid(row=row, column=column, padx=2, pady=2)

    def _change_month(self, offset: int) -> None:
        month = self._month + offset
        if month < 1:
            self._year -= 1
            month = 12
        elif month > 12:
            self._year += 1
            month = 1
        self._month = month
        self._render_month()

    def _select(self, day: int) -> None:
        value = date(self._year, self._month, day).isoformat()
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        if self._picker is not None:
            self._picker.destroy()
            self._picker = None
