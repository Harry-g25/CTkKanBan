"""Small reusable widgets that do not belong to the board controller."""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from typing import Any

import customtkinter as ctk


class Tooltip:
    """Lightweight hover tooltip for compact icon controls."""

    def __init__(
        self,
        widget: Any,
        text: str,
        *,
        delay_ms: int = 450,
        theme: dict[str, Any] | None = None,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.theme = theme or {}
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
        dark_mode = ctk.get_appearance_mode().casefold() == "dark"

        def resolved(key: str, fallback: str) -> str:
            value = self.theme.get(key, fallback)
            if isinstance(value, (tuple, list)) and len(value) >= 2:
                return str(value[1 if dark_mode else 0])
            return str(value)

        label = tk.Label(
            window,
            text=self.text,
            background=resolved("tooltip_fg_color", "#202124"),
            foreground=resolved("tooltip_text_color", "#FFFFFF"),
            relief="flat",
            borderwidth=0,
            highlightbackground=resolved("tooltip_border_color", "#334155"),
            highlightcolor=resolved("tooltip_border_color", "#334155"),
            highlightthickness=1,
            padx=9,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack()
        window.update_idletasks()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        width = window.winfo_reqwidth()
        x = max(4, min(x, self.widget.winfo_screenwidth() - width - 4))
        window.geometry(f"+{x}+{y}")
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

    def __init__(
        self,
        master: Any,
        *,
        value: Any = None,
        theme: dict[str, Any] | None = None,
        **entry_options: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.theme = theme or {}
        self._entry_options = dict(entry_options)
        self._surface_color = (
            self.theme.get("calendar_fg_color")
            or self.theme.get("dialog_fg_color")
            or entry_options.get("fg_color")
            or ("#FFFFFF", "#111827")
        )
        self._border_color = (
            self.theme.get("dialog_border_color")
            or entry_options.get("border_color")
            or ("#D7E0EA", "#2A3950")
        )
        self._text_color = (
            self.theme.get("dialog_text_color")
            or self.theme.get("text_color")
            or entry_options.get("text_color")
            or ("#172033", "#F1F5F9")
        )
        self._muted_text_color = (
            self.theme.get("dialog_subtitle_text_color")
            or self.theme.get("muted_text_color")
            or ("#64748B", "#93A4BA")
        )
        self._secondary_fg_color = (
            self.theme.get("secondary_button_fg_color")
            or entry_options.get("fg_color")
            or ("#F1F5F9", "#1B273A")
        )
        self._secondary_hover_color = (
            self.theme.get("secondary_button_hover_color")
            or entry_options.get("border_color")
            or ("#E2E8F0", "#26354D")
        )
        self._secondary_text_color = (
            self.theme.get("secondary_button_text_color")
            or entry_options.get("text_color")
            or self._text_color
        )
        self._primary_fg_color = self.theme.get("button_fg_color") or ("#2563EB", "#3B82F6")
        self._primary_text_color = self.theme.get("button_text_color") or ("#FFFFFF", "#FFFFFF")
        self.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(self, **entry_options)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.button = ctk.CTkButton(
            self,
            text="▦",
            width=38,
            height=int(entry_options.get("height", 38)),
            fg_color=self._secondary_fg_color,
            hover_color=self._secondary_hover_color,
            text_color=self._secondary_text_color,
            corner_radius=self.theme.get(
                "secondary_button_corner_radius",
                entry_options.get("corner_radius", 8),
            ),
            border_width=0,
            font=ctk.CTkFont(size=17, weight="bold"),
            command=self._open_picker,
        )
        self.button.grid(row=0, column=1, padx=(6, 0))
        Tooltip(self.button, "Choose date", theme=self.theme)
        if value not in (None, ""):
            self.entry.insert(0, str(value)[:10])
        self._picker: ctk.CTkToplevel | None = None
        self._calendar: ctk.CTkFrame | None = None
        self._selected_date: date | None = None
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
        self._selected_date = selected
        self._year, self._month = selected.year, selected.month
        self._picker = ctk.CTkToplevel(self)
        self._picker.title("Choose date")
        self._picker.transient(self.winfo_toplevel())
        self._picker.resizable(False, False)
        self._picker.configure(fg_color=self._surface_color)
        self._picker.protocol("WM_DELETE_WINDOW", self._close_picker)
        self._picker.bind("<Escape>", self._on_picker_escape)

        shell = ctk.CTkFrame(
            self._picker,
            fg_color=self._surface_color,
            border_color=self._border_color,
            border_width=int(self.theme.get("dialog_border_width", 1)),
            corner_radius=int(self.theme.get("dialog_corner_radius", 12)),
        )
        shell.pack(fill="both", expand=True)

        header = ctk.CTkFrame(shell, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Choose date",
            anchor="w",
            text_color=self.theme.get("dialog_title_text_color", self._text_color),
            font=self.theme.get("filter_title_font") or ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text="Select a day from the calendar.",
            anchor="w",
            text_color=self._muted_text_color,
            font=self.theme.get("card_metadata_font") or ctk.CTkFont(size=10),
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ctk.CTkButton(
            header,
            text="×",
            width=30,
            height=30,
            fg_color="transparent",
            hover_color=self._secondary_hover_color,
            text_color=self._text_color,
            corner_radius=8,
            border_width=0,
            font=ctk.CTkFont(size=18),
            command=self._close_picker,
        ).grid(row=0, column=1, rowspan=2, padx=(10, 0))

        ctk.CTkFrame(
            shell,
            height=1,
            corner_radius=0,
            fg_color=self.theme.get("dialog_divider_color", self._border_color),
        ).pack(fill="x")
        self._calendar = ctk.CTkFrame(shell, fg_color="transparent")
        self._calendar.pack(fill="both", expand=True, padx=14, pady=10)

        ctk.CTkFrame(
            shell,
            height=1,
            corner_radius=0,
            fg_color=self.theme.get("dialog_divider_color", self._border_color),
        ).pack(fill="x")
        footer = ctk.CTkFrame(shell, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(9, 13))
        ctk.CTkButton(
            footer,
            text="Today",
            width=78,
            height=34,
            fg_color=self._secondary_fg_color,
            hover_color=self._secondary_hover_color,
            text_color=self._secondary_text_color,
            corner_radius=self.theme.get("secondary_button_corner_radius", 8),
            border_width=0,
            font=self.theme.get("secondary_button_font"),
            command=lambda: self._select_date(date.today()),
        ).pack(side="right")
        self._render_month()
        self._picker.after_idle(self._position_picker)

    def _render_month(self) -> None:
        if self._calendar is None:
            return
        for child in self._calendar.winfo_children():
            child.destroy()
        navigation_options = {
            "width": 32,
            "height": 32,
            "fg_color": "transparent",
            "hover_color": self._secondary_hover_color,
            "text_color": self._text_color,
            "corner_radius": 8,
            "border_width": 0,
            "font": ctk.CTkFont(size=20),
        }
        ctk.CTkButton(
            self._calendar,
            text="‹",
            command=lambda: self._change_month(-1),
            **navigation_options,
        ).grid(row=0, column=0, pady=(0, 7))
        ctk.CTkLabel(
            self._calendar,
            text=f"{calendar.month_name[self._month]} {self._year}",
            width=190,
            text_color=self.theme.get("dialog_title_text_color", self._text_color),
            font=self.theme.get("column_title_font") or ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=1, columnspan=5, pady=(0, 7))
        ctk.CTkButton(
            self._calendar,
            text="›",
            command=lambda: self._change_month(1),
            **navigation_options,
        ).grid(row=0, column=6, pady=(0, 7))
        for column, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            ctk.CTkLabel(
                self._calendar,
                text=name,
                width=38,
                height=24,
                text_color=self.theme.get(
                    "calendar_weekday_text_color",
                    self._muted_text_color,
                ),
                font=self.theme.get("card_metadata_font") or ctk.CTkFont(size=9, weight="bold"),
            ).grid(row=1, column=column, padx=2, pady=(0, 4))

        weeks = calendar.monthcalendar(self._year, self._month)
        weeks.extend([[0] * 7 for _ in range(6 - len(weeks))])
        today = date.today()
        for row, week in enumerate(weeks, start=2):
            for column, day in enumerate(week):
                if day:
                    shown_date = date(self._year, self._month, day)
                    selected = shown_date == self._selected_date
                    is_today = shown_date == today
                    day_button = ctk.CTkButton(
                        self._calendar,
                        text=str(day),
                        width=38,
                        height=32,
                        fg_color=(
                            self.theme.get(
                                "calendar_selected_fg_color",
                                self._primary_fg_color,
                            )
                            if selected
                            else (
                                self.theme.get(
                                    "calendar_today_fg_color",
                                    self.theme.get("filter_chip_fg_color", "transparent"),
                                )
                                if is_today
                                else "transparent"
                            )
                        ),
                        hover_color=self.theme.get(
                            "calendar_day_hover_color",
                            self._secondary_hover_color,
                        ),
                        text_color=(
                            self.theme.get(
                                "calendar_selected_text_color",
                                self._primary_text_color,
                            )
                            if selected
                            else (
                                self.theme.get(
                                    "calendar_today_text_color",
                                    self.theme.get(
                                        "filter_chip_text_color",
                                        self._text_color,
                                    ),
                                )
                                if is_today
                                else self._text_color
                            )
                        ),
                        corner_radius=8,
                        border_width=0,
                        font=self.theme.get("input_font"),
                        command=lambda selected_date=shown_date: self._select_date(selected_date),
                    )
                    day_button.grid(row=row, column=column, padx=2, pady=2)
                else:
                    ctk.CTkLabel(self._calendar, text="", width=38, height=32).grid(
                        row=row,
                        column=column,
                        padx=2,
                        pady=2,
                    )

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
        self._select_date(date(self._year, self._month, day))

    def _select_date(self, selected: date) -> None:
        value = selected.isoformat()
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        self._selected_date = selected
        self._close_picker()

    def _position_picker(self) -> None:
        if self._picker is None or not self._picker.winfo_exists():
            return
        self._picker.update_idletasks()
        scaling = self._picker._get_window_scaling()
        width = max(round(328 * scaling), self._picker.winfo_reqwidth())
        height = self._picker.winfo_reqheight()
        x = self.winfo_rootx() + self.winfo_width() - width
        y = self.winfo_rooty() + self.winfo_height() + 6
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(8, min(x, screen_width - width - 8))
        if y + height > screen_height - 8:
            y = max(8, self.winfo_rooty() - height - 6)
        logical_width = round(width / scaling)
        logical_height = round(height / scaling)
        self._picker.geometry(f"{logical_width}x{logical_height}+{x}+{y}")
        self._picker.focus_force()

    def _on_picker_escape(self, _event: Any) -> str:
        self._close_picker()
        return "break"

    def _close_picker(self) -> None:
        picker = self._picker
        self._picker = None
        self._calendar = None
        if picker is not None:
            try:
                if picker.winfo_exists():
                    picker.destroy()
            except tk.TclError:
                pass

    def destroy(self) -> None:
        self._close_picker()
        super().destroy()
