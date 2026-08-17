"""Scrollable frame with explicit cleanup for CustomTkinter global bindings."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk


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

    def destroy(self) -> None:
        if self._managed_destroyed:
            return
        self._managed_destroyed = True
        root = self._root()
        for sequence, func_id in self._managed_global_bindings:
            try:
                root._unbind(("bind", "all", sequence), func_id)
            except tk.TclError:
                pass
        self._managed_global_bindings.clear()
        try:
            super().destroy()
        except tk.TclError:
            pass


__all__ = ["ManagedScrollableFrame"]
