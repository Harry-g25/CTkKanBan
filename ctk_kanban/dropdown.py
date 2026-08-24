"""Compact CustomTkinter dropdown control with a widget-based popup."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from math import ceil
from typing import Any, Callable, Mapping, Sequence

import customtkinter as ctk

from .context_menu import CTkContextMenu
from .themes import merge_theme


class CTkDropdown(ctk.CTkFrame):
    """A modern option control that avoids CustomTkinter's native Tk menu."""

    POPUP_PADDING_Y = 9

    def __init__(
        self,
        master: Any,
        *,
        values: Sequence[str],
        variable: tk.Variable | None = None,
        command: Callable[[str], Any] | None = None,
        label_prefix: str = "",
        state: str = "normal",
        width: int = 140,
        height: int = 36,
        corner_radius: int | None = None,
        font: Any | None = None,
        theme: Mapping[str, Any] | None = None,
        _normalized_theme: bool = False,
        **kwargs: Any,
    ) -> None:
        self.theme = theme if _normalized_theme and theme is not None else merge_theme(theme)
        entry_theme = ctk.ThemeManager.theme["CTkEntry"]
        normal_fg = entry_theme["fg_color"]
        self._normal_fg = tuple(normal_fg) if isinstance(normal_fg, list) else normal_fg
        self._values = [str(value) for value in values]
        self._variable = variable
        self._command = command
        self._label_prefix = str(label_prefix)
        self._font = font
        self._state = str(state)
        self._minimum_width = int(width)
        self._current_value = (
            str(variable.get())
            if variable is not None
            else (self._values[0] if self._values else "")
        )
        self._variable_callback_name: str | None = None
        self._popup: CTkContextMenu | None = None
        self._hover_after_id: str | None = None
        self._destroyed = False

        kwargs.setdefault("fg_color", self._normal_fg)
        kwargs.setdefault("border_color", self.theme["input_border_color"])
        kwargs.setdefault("border_width", self.theme["input_border_width"])
        super().__init__(
            master,
            width=width,
            height=height,
            corner_radius=(
                self.theme["input_corner_radius"]
                if corner_radius is None
                else corner_radius
            ),
            **kwargs,
        )
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._value_label = ctk.CTkLabel(
            self,
            text=self._display_text(),
            anchor="w",
            fg_color="transparent",
            text_color=self.theme["text_color"],
            font=font,
        )
        content_inset = max(4, int(self.theme["input_border_width"]))
        self._value_label.grid(
            row=0,
            column=0,
            padx=(13, 6),
            pady=content_inset,
            sticky="nsew",
        )
        self._arrow_label = ctk.CTkLabel(
            self,
            text="\u25be",
            width=28,
            fg_color="transparent",
            text_color=self.theme["muted_text_color"],
        )
        self._arrow_label.grid(
            row=0,
            column=1,
            padx=(0, 4),
            pady=content_inset,
            sticky="ns",
        )
        self._font = self._value_label.cget("font")

        for widget in (self, self._value_label, self._arrow_label):
            widget.bind("<Button-1>", self._clicked, add="+")
            widget.bind("<Enter>", self._hover_enter, add="+")
            widget.bind("<Leave>", self._hover_leave, add="+")
            try:
                widget.configure(cursor="hand2")
            except (AttributeError, tk.TclError):
                pass

        if self._variable is not None:
            self._variable_callback_name = self._variable.trace_add(
                "write", self._variable_changed
            )
        self._fit_to_values()
        self._sync_state()

    def get(self) -> str:
        return self._current_value

    def set(self, value: Any) -> None:
        text = str(value)
        if self._variable is not None:
            self._variable.set(text)
        else:
            self._current_value = text
            self._value_label.configure(text=self._display_text())
            self._fit_to_values()

    def configure(self, require_redraw: bool = False, **kwargs: Any) -> Any:
        refit = False
        if "values" in kwargs:
            self._values = [str(value) for value in kwargs.pop("values")]
            refit = True
        if "width" in kwargs:
            self._minimum_width = int(kwargs.pop("width"))
            refit = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "font" in kwargs:
            self._font = kwargs.pop("font")
            if hasattr(self, "_value_label"):
                self._value_label.configure(font=self._font)
                refit = True
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
            if hasattr(self, "_value_label"):
                self._sync_state()
        result = super().configure(require_redraw=require_redraw, **kwargs)
        if refit and hasattr(self, "_value_label"):
            self._fit_to_values()
        return result

    config = configure

    def cget(self, attribute_name: str) -> Any:
        if attribute_name == "values":
            return list(self._values)
        if attribute_name == "variable":
            return self._variable
        if attribute_name == "command":
            return self._command
        if attribute_name == "font":
            return self._font
        if attribute_name == "state":
            return self._state
        if attribute_name == "text":
            return self._display_text()
        return super().cget(attribute_name)

    def _variable_changed(self, *_args: Any) -> None:
        if self._destroyed or self._variable is None:
            return
        self._current_value = str(self._variable.get())
        self._value_label.configure(text=self._display_text())
        self._fit_to_values()

    def _display_text(self) -> str:
        return f"{self._label_prefix}{self._current_value}"

    def _fit_to_values(self) -> None:
        """Keep every configured value readable without making fields oversized."""

        labels = [f"{self._label_prefix}{value}" for value in self._values]
        labels.append(self._display_text())
        font = self._value_label._font
        text_width = max((font.measure(label) for label in labels), default=0)
        # Text inset, CTkLabel breathing room, and the fixed arrow cell.
        natural_width = ceil(text_width) + 13 + 6 + 5 + 28 + 4
        super().configure(width=max(self._minimum_width, natural_width))

    def _clicked(self, _event: tk.Event[Any] | None = None) -> str:
        if self._state == "disabled":
            return "break"
        if self._popup is not None:
            popup = self._popup
            self._popup = None
            popup.destroy()
            return "break"
        popup = CTkContextMenu(
            self,
            theme=self.theme,
            on_close=self._popup_closed,
            vertical_padding=self.POPUP_PADDING_Y,
            _normalized_theme=True,
        )
        for value in self._values:
            popup.add_command(
                label=value or "None",
                selected=value == self._current_value,
                command=partial(self._selected, value),
            )
        self._popup = popup
        popup.popup_at_widget(self, match_width=True, vertical_gap=4)
        return "break"

    def _selected(self, value: str) -> None:
        self.set(value)
        if self._command is not None:
            self._command(value)

    def _popup_closed(self, popup: CTkContextMenu) -> None:
        if self._popup is popup:
            self._popup = None

    def _hover_enter(self, _event: Any = None) -> None:
        if self._hover_after_id is not None:
            try:
                self.after_cancel(self._hover_after_id)
            except tk.TclError:
                pass
            self._hover_after_id = None
        if self._state != "disabled":
            super().configure(fg_color=self.theme["control_hover_color"])

    def _hover_leave(self, _event: Any = None) -> None:
        if self._hover_after_id is None:
            try:
                self._hover_after_id = self.after_idle(self._settle_hover)
            except tk.TclError:
                self._hover_after_id = None

    def _settle_hover(self) -> None:
        self._hover_after_id = None
        try:
            widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        except tk.TclError:
            return
        current = widget
        while current is not None:
            if current is self:
                return
            current = getattr(current, "master", None)
        super().configure(fg_color=self._normal_fg)

    def _sync_state(self) -> None:
        disabled = self._state == "disabled"
        color = self.theme["muted_text_color"] if disabled else self.theme["text_color"]
        self._value_label.configure(text_color=color)
        self._arrow_label.configure(text_color=self.theme["muted_text_color"])
        if disabled:
            super().configure(fg_color=self._normal_fg)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._popup is not None:
            popup = self._popup
            self._popup = None
            popup.destroy()
        if self._hover_after_id is not None:
            try:
                self.after_cancel(self._hover_after_id)
            except tk.TclError:
                pass
            self._hover_after_id = None
        if self._variable is not None and self._variable_callback_name is not None:
            try:
                self._variable.trace_remove("write", self._variable_callback_name)
            except tk.TclError:
                pass
            self._variable_callback_name = None
        super().destroy()


__all__ = ["CTkDropdown"]
