"""Scrollable frame with explicit cleanup for CustomTkinter global bindings."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk


def _unbind_global_callback(root: tk.Misc, sequence: str, func_id: str) -> None:
    """Remove one ``bind_all`` callback without clearing sibling bindings.

    Tkinter only gained its equivalent ``Misc._unbind(..., func_id)`` helper
    after Python 3.10.  Calling that private helper directly made board cleanup
    fail on the oldest supported Python release.  Keep the small Tcl operation
    local so cleanup behaves consistently across Python 3.10 and newer.
    """

    lines = str(root.tk.call("bind", "all", sequence) or "").splitlines()
    prefix = f'if {{"[{func_id} '
    remaining = "\n".join(line for line in lines if not line.startswith(prefix))
    root.tk.call("bind", "all", sequence, remaining if remaining.strip() else "")
    root.deletecommand(func_id)


class ManagedScrollableFrame(ctk.CTkScrollableFrame):
    """Remove the ``bind_all`` callbacks installed by CTkScrollableFrame.

    CustomTkinter installs wheel and Shift-key callbacks for every scrollable
    frame but does not unregister them when a nested frame is destroyed.  The
    board deliberately rebuilds its small visual tree, so retaining those
    callbacks would make scrolling slower after every edit.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._managed_global_bindings: list[tuple[str, str]] = []
        self._managed_destroyed = False
        super().__init__(*args, **kwargs)

    def bind_all(
        self,
        sequence: str | None = None,
        func: Callable[..., Any] | None = None,
        add: str | bool | None = None,
    ) -> str | None:
        func_id = super().bind_all(sequence, func, add)
        if sequence is not None and func is not None and func_id is not None:
            self._managed_global_bindings.append((sequence, func_id))
        return func_id

    def _fit_frame_dimensions_to_canvas(self, _event: tk.Event[Any] | None = None) -> None:
        """Fill the viewport without giving up scrolling for oversized content.

        CustomTkinter's horizontal scroll frame only matches the canvas height.
        That leaves narrow content anchored to the left of a wide viewport.  The
        board benefits from a full-width inner frame so its column track can be
        centred, while still allowing the frame to grow when columns overflow.
        """

        if self._orientation == "horizontal":
            canvas_width = self._parent_canvas.winfo_width()
            content_width = self.winfo_reqwidth()
            self._parent_canvas.itemconfigure(
                self._create_window_id,
                width=max(canvas_width, content_width),
                height=self._parent_canvas.winfo_height(),
            )
        else:
            self._parent_canvas.itemconfigure(
                self._create_window_id,
                width=self._parent_canvas.winfo_width(),
            )
        self._parent_canvas.configure(scrollregion=self._parent_canvas.bbox("all"))

    def fit_content_to_canvas(self) -> None:
        """Recalculate the inner window after children are added or removed."""

        try:
            self.update_idletasks()
            self._fit_frame_dimensions_to_canvas()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        if self._managed_destroyed:
            return
        self._managed_destroyed = True
        root = self._root()
        for sequence, func_id in self._managed_global_bindings:
            try:
                _unbind_global_callback(root, sequence, func_id)
            except tk.TclError:
                pass
        self._managed_global_bindings.clear()
        try:
            super().destroy()
        except tk.TclError:
            pass


__all__ = ["ManagedScrollableFrame"]
