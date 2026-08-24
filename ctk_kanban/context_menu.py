"""CustomTkinter-native popup menus used by the board and host applications."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import customtkinter as ctk

from .themes import merge_theme


@dataclass(slots=True)
class _MenuEntry:
    kind: str
    label: str = ""
    command: Callable[[], Any] | None = None
    state: str = "normal"
    menu: CTkContextMenu | None = None
    danger: bool = False
    selected: bool = False


class CTkContextMenu(tk.Toplevel):
    """A rounded, appearance-aware popup menu built from CustomTkinter widgets.

    The ``add_command``, ``add_separator``, and ``add_cascade`` methods mirror
    the small portion of ``tk.Menu`` most applications need.  Menus may be
    anchored to a widget or opened at an explicit screen position.
    """

    _TRANSPARENT_KEY = "#010203"

    def __init__(
        self,
        master: Any,
        *,
        theme: Mapping[str, Any] | None = None,
        on_close: Callable[[CTkContextMenu], None] | None = None,
        vertical_padding: int = 0,
        _normalized_theme: bool = False,
    ) -> None:
        parent_menu = master if isinstance(master, CTkContextMenu) else None
        owner = parent_menu._owner if parent_menu is not None else master.winfo_toplevel()
        self.theme = theme if _normalized_theme and theme is not None else merge_theme(theme)
        self._owner: Any = owner
        self._parent_menu: CTkContextMenu | None = parent_menu
        self._root_menu: CTkContextMenu = (
            self if parent_menu is None else parent_menu._root_menu
        )
        self._on_close = on_close if parent_menu is None else None
        if isinstance(vertical_padding, bool) or not isinstance(vertical_padding, int):
            raise TypeError("vertical_padding must be an integer")
        if vertical_padding < 0:
            raise ValueError("vertical_padding cannot be negative")
        self._vertical_padding = vertical_padding
        self._entries: list[_MenuEntry] = []
        self._entry_widgets: dict[int, ctk.CTkButton] = {}
        self._child_menus: list[CTkContextMenu] = []
        self._active_submenu: CTkContextMenu | None = None
        self._built = False
        self._closed = False
        self._owner_bindings: list[tuple[str, str]] = []

        super().__init__(owner)
        if parent_menu is not None:
            parent_menu._child_menus.append(self)
        self.withdraw()
        self.overrideredirect(True)
        self.resizable(False, False)
        try:
            self.transient(owner)
        except tk.TclError:
            pass
        popup_background = self._resolve_color(self.theme["menu_border_color"])
        if self.tk.call("tk", "windowingsystem") == "win32":
            try:
                self.configure(background=self._TRANSPARENT_KEY)
                self.wm_attributes("-transparentcolor", self._TRANSPARENT_KEY)
                popup_background = self._TRANSPARENT_KEY
            except tk.TclError:
                self.configure(background=popup_background)
        else:
            self.configure(background=popup_background)
        self._surface = ctk.CTkFrame(
            self,
            bg_color=popup_background,
            fg_color=self.theme["menu_fg_color"],
            border_color=self.theme["menu_border_color"],
            border_width=self.theme["menu_border_width"],
            corner_radius=self.theme["menu_corner_radius"],
        )
        self._surface.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda _event: self.close(), add="+")

    def add_command(
        self,
        *,
        label: str,
        command: Callable[[], Any] | None = None,
        state: str = "normal",
        danger: bool = False,
        selected: bool = False,
        **_kwargs: Any,
    ) -> None:
        """Append a clickable command row."""

        self._require_unbuilt()
        self._entries.append(
            _MenuEntry(
                "command",
                label=str(label),
                command=command,
                state=str(state),
                danger=bool(danger),
                selected=bool(selected),
            )
        )

    def add_separator(self, **_kwargs: Any) -> None:
        """Append a visual separator."""

        self._require_unbuilt()
        self._entries.append(_MenuEntry("separator"))

    def add_cascade(
        self,
        *,
        label: str,
        menu: CTkContextMenu,
        state: str = "normal",
        **_kwargs: Any,
    ) -> None:
        """Append a row that opens another :class:`CTkContextMenu`."""

        self._require_unbuilt()
        if not isinstance(menu, CTkContextMenu):
            raise TypeError("menu must be a CTkContextMenu")
        if menu._root_menu is not self._root_menu:
            raise ValueError("submenu must be created from this menu hierarchy")
        self._entries.append(
            _MenuEntry(
                "cascade",
                label=str(label),
                state=str(state),
                menu=menu,
            )
        )

    def popup(self, x: int, y: int, *, minimum_width: int = 0) -> None:
        """Display the menu at screen coordinates, clamped to the display."""

        if self._closed:
            return
        self._build()
        self.update_idletasks()
        width = max(int(minimum_width), self._surface.winfo_reqwidth())
        height = self._surface.winfo_reqheight()
        screen_left = self.winfo_vrootx()
        screen_top = self.winfo_vrooty()
        screen_right = screen_left + self.winfo_screenwidth()
        screen_bottom = screen_top + self.winfo_screenheight()
        popup_x = min(max(screen_left + 4, int(x)), max(screen_left + 4, screen_right - width - 4))
        popup_y = min(max(screen_top + 4, int(y)), max(screen_top + 4, screen_bottom - height - 4))
        self.geometry(f"{width}x{height}+{popup_x}+{popup_y}")
        self.deiconify()
        self.lift()
        if self is self._root_menu:
            self._bind_owner()

    def popup_at_widget(
        self,
        widget: Any,
        *,
        match_width: bool = False,
        vertical_gap: int = 0,
    ) -> None:
        """Open immediately below a widget."""

        self.popup(
            widget.winfo_rootx(),
            widget.winfo_rooty() + widget.winfo_height() + int(vertical_gap),
            minimum_width=widget.winfo_width() if match_width else 0,
        )

    @staticmethod
    def _resolve_color(color: Any) -> Any:
        if isinstance(color, (tuple, list)):
            return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
        return color

    def close(self) -> None:
        """Close this complete menu hierarchy."""

        self._root_menu._destroy_tree()

    def index(self, index: Any) -> int | None:
        """Return a numeric entry index; provided for ``tk.Menu`` familiarity."""

        if index == "end":
            return len(self._entries) - 1 if self._entries else None
        return int(index)

    def entrycget(self, index: Any, option: str) -> Any:
        """Read an entry option using the familiar ``tk.Menu`` spelling."""

        entry = self._entries[self._entry_index(index)]
        key = str(option).lstrip("-")
        if key == "label":
            return entry.label
        if key == "state":
            return entry.state
        if key == "menu":
            return entry.menu
        if key == "command":
            return entry.command
        raise tk.TclError(f"unknown option '-{key}'")

    def invoke(self, index: Any) -> Any:
        """Invoke a command entry, ignoring separators and disabled rows."""

        position = self._entry_index(index)
        entry = self._entries[position]
        if entry.state == "disabled":
            return None
        if entry.kind == "cascade":
            self._open_submenu(position)
            return None
        if entry.kind != "command":
            return None
        command = entry.command
        self.close()
        return command() if command is not None else None

    def nametowidget(self, name: Any) -> Any:
        """Accept submenu objects returned by :meth:`entrycget`."""

        if isinstance(name, CTkContextMenu):
            return name
        return super().nametowidget(name)

    def cget(self, key: str) -> Any:
        if key == "fg_color":
            return self.theme["menu_border_color"]
        return super().cget(key)

    def _require_unbuilt(self) -> None:
        if self._built:
            raise RuntimeError("menu entries cannot be changed after the menu is shown")

    def _entry_index(self, index: Any) -> int:
        value = self.index(index)
        if value is None or value < 0 or value >= len(self._entries):
            raise tk.TclError("bad menu entry index")
        return value

    def _build(self) -> None:
        if self._built:
            return
        self._built = True
        padding = int(self.theme["menu_padding"])
        font = ctk.CTkFont(**self.theme["menu_font"])
        labels = [
            f"{entry.label}   \u203a" if entry.kind == "cascade" else entry.label
            for entry in self._entries
            if entry.kind != "separator"
        ]
        measured_width = max(
            (
                int(round(float(self._surface._reverse_widget_scaling(font.measure(text)))))
                for text in labels
            ),
            default=0,
        )
        row_width = max(
            int(self.theme["menu_min_width"]) - padding * 2,
            measured_width + 24,
        )
        self._add_vertical_spacer()
        for index, entry in enumerate(self._entries):
            if entry.kind == "separator":
                ctk.CTkFrame(
                    self._surface,
                    height=1,
                    corner_radius=0,
                    fg_color=self.theme["menu_border_color"],
                ).pack(
                    fill="x",
                    padx=padding + int(self.theme["menu_separator_margin"]),
                    pady=4,
                )
                continue
            text = entry.label
            if entry.kind == "cascade":
                text = f"{text}   \u203a"
            text_color = (
                self.theme["danger_color"] if entry.danger else self.theme["menu_text_color"]
            )
            button = ctk.CTkButton(
                self._surface,
                text=text,
                anchor="w",
                width=row_width,
                height=self.theme["menu_item_height"],
                corner_radius=self.theme["menu_item_corner_radius"],
                border_width=0,
                fg_color=self.theme["menu_hover_color"] if entry.selected else "transparent",
                hover_color=self.theme["menu_hover_color"],
                text_color=text_color,
                text_color_disabled=self.theme["menu_disabled_text_color"],
                font=font,
                state="disabled" if entry.state == "disabled" else "normal",
                command=lambda item=index: self.invoke(item),
            )
            button.pack(fill="x", padx=padding, pady=1)
            button.bind("<Enter>", lambda _event, item=index: self._entry_entered(item), add="+")
            self._entry_widgets[index] = button
        self._add_vertical_spacer()

    def _add_vertical_spacer(self) -> None:
        if self._vertical_padding <= 0:
            return
        spacer = ctk.CTkFrame(
            self._surface,
            width=1,
            height=self._vertical_padding,
            corner_radius=0,
            fg_color="transparent",
        )
        spacer.pack()

    def _entry_entered(self, index: int) -> None:
        entry = self._entries[index]
        if entry.kind == "cascade" and entry.state != "disabled":
            self._open_submenu(index)
        else:
            self._hide_active_submenu()

    def _open_submenu(self, index: int) -> None:
        entry = self._entries[index]
        submenu = entry.menu
        row = self._entry_widgets.get(index)
        if submenu is None or row is None or entry.state == "disabled":
            return
        if self._active_submenu is not submenu:
            self._hide_active_submenu()
            self._active_submenu = submenu
        submenu._build()
        submenu.update_idletasks()
        submenu_width = submenu._surface.winfo_reqwidth()
        right_x = self.winfo_rootx() + self.winfo_width() - 2
        if right_x + submenu_width > self.winfo_vrootx() + self.winfo_screenwidth() - 4:
            right_x = self.winfo_rootx() - submenu_width + 2
        submenu.popup(right_x, row.winfo_rooty() - int(self.theme["menu_padding"]))

    def _hide_active_submenu(self) -> None:
        submenu = self._active_submenu
        if submenu is None:
            return
        submenu._hide_tree()
        self._active_submenu = None

    def _hide_tree(self) -> None:
        self._hide_active_submenu()
        try:
            self.withdraw()
        except tk.TclError:
            pass

    def _bind_owner(self) -> None:
        if self._owner_bindings:
            return
        for sequence, callback in (
            ("<ButtonPress-1>", self._outside_pressed),
            ("<ButtonPress-3>", self._outside_pressed),
            ("<Escape>", self._outside_pressed),
            ("<Unmap>", self._owner_unmapped),
        ):
            func_id = self._owner.bind(sequence, callback, add="+")
            if func_id:
                self._owner_bindings.append((sequence, func_id))

    def _outside_pressed(self, _event: tk.Event[Any]) -> None:
        self.close()

    def _owner_unmapped(self, _event: tk.Event[Any]) -> None:
        self.close()

    def _destroy_tree(self) -> None:
        if self._closed:
            return
        self._closed = True
        for sequence, func_id in self._owner_bindings:
            try:
                self._owner.unbind(sequence, func_id)
            except tk.TclError:
                pass
        self._owner_bindings.clear()
        menus: list[CTkContextMenu] = []

        def collect(menu: CTkContextMenu) -> None:
            for child in menu._child_menus:
                collect(child)
            menus.append(menu)

        collect(self)
        for menu in menus:
            menu._closed = True
            try:
                tk.Toplevel.destroy(menu)
            except tk.TclError:
                pass
        if self._on_close is not None:
            self._on_close(self)

    def destroy(self) -> None:
        """Destroy the hierarchy safely even when called more than once."""

        if self is self._root_menu:
            self._destroy_tree()
            return
        if self._closed:
            return
        self._closed = True
        for child in tuple(self._child_menus):
            child.destroy()
        try:
            tk.Toplevel.destroy(self)
        except tk.TclError:
            pass


__all__ = ["CTkContextMenu"]
