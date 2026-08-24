"""Scrollable frame with explicit cleanup for CustomTkinter global bindings."""

from __future__ import annotations

import sys
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
        self._scrollregion_after_id: str | None = None
        self._last_scrollbar_view: tuple[float, float] | None = None
        super().__init__(*args, **kwargs)
        self.bind("<Configure>", self._queue_scrollregion_update)
        self._parent_canvas.configure(xscrollincrement=16, yscrollincrement=16)
        if self._orientation == "horizontal":
            self._parent_canvas.configure(xscrollcommand=self._set_scrollbar_view)
        else:
            self._parent_canvas.configure(yscrollcommand=self._set_scrollbar_view)

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
        self._queue_scrollregion_update()

    def _queue_scrollregion_update(self, _event: tk.Event[Any] | None = None) -> None:
        """Coalesce geometry bursts and measure the final canvas-window size."""

        if self._managed_destroyed or self._scrollregion_after_id is not None:
            return
        try:
            self._scrollregion_after_id = self.after_idle(self._refresh_scrollregion)
        except tk.TclError:
            pass

    def _refresh_scrollregion(self) -> None:
        self._scrollregion_after_id = None
        if self._managed_destroyed:
            return
        try:
            self._parent_canvas.configure(scrollregion=self._parent_canvas.bbox("all"))
        except tk.TclError:
            pass

    def _set_scrollbar_view(self, first: str | float, last: str | float) -> None:
        """Avoid redrawing a compound CTkScrollbar for duplicate canvas views."""

        view = (float(first), float(last))
        if view == self._last_scrollbar_view:
            return
        self._last_scrollbar_view = view
        try:
            self._scrollbar.set(*view)
        except tk.TclError:
            pass

    def _mouse_wheel_all(self, event: tk.Event[Any]) -> None:
        """Route one wheel event to the useful axis with a practical step size."""

        if not self._contains_widget(event.widget):
            return

        if self._shift_pressed:
            if self._orientation == "horizontal":
                self._scroll_canvas(event, horizontal=True)
            return

        if self._orientation == "vertical":
            self._scroll_canvas(event, horizontal=False)
            return

        nearest = self._nearest_managed_scrollable(event.widget)
        if nearest is self or (
            nearest is not None
            and nearest._orientation == "vertical"
            and nearest._parent_canvas.yview() == (0.0, 1.0)
        ):
            self._scroll_canvas(event, horizontal=True)

    def _contains_widget(self, widget: Any) -> bool:
        """Return whether ``widget`` belongs to this scrollable frame.

        CustomTkinter 5 exposed ``check_if_master_is_canvas()`` for this walk,
        while 6 replaced it with a differently behaved private helper.  Keep
        the small containment check here so wheel routing is stable across the
        complete supported CustomTkinter range.
        """

        current = widget
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            if current is self._parent_canvas:
                return True
            visited.add(id(current))
            current = getattr(current, "master", None)
        return False

    @staticmethod
    def _nearest_managed_scrollable(widget: Any) -> ManagedScrollableFrame | None:
        current = widget
        while current is not None:
            if isinstance(current, ManagedScrollableFrame):
                return current
            current = getattr(current, "master", None)
        return None

    def _scroll_canvas(self, event: tk.Event[Any], *, horizontal: bool) -> None:
        canvas = self._parent_canvas
        view = canvas.xview() if horizontal else canvas.yview()
        if view == (0.0, 1.0):
            return

        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return
        if sys.platform == "darwin":
            units = -delta
        else:
            notches = max(1, abs(delta) // 120)
            units = (-1 if delta > 0 else 1) * notches * 3
        if horizontal:
            canvas.xview_scroll(units, "units")
        else:
            canvas.yview_scroll(units, "units")

    def fit_content_to_canvas(self) -> None:
        """Recalculate the inner window after children are added or removed."""

        try:
            self.update_idletasks()
            self._fit_frame_dimensions_to_canvas()
        except tk.TclError:
            pass

    def grid_configure(self, cnf: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Configure the scrollable frame's outer geometry container.

        ``CTkScrollableFrame.grid()`` manages a private parent frame, while its
        inherited ``grid_configure()`` accidentally manages the inner canvas
        window.  Delegate both operations to the same widget so changing board
        padding cannot detach the scrolling content from its canvas.
        """

        previous = getattr(self._parent_frame, "_last_geometry_manager_call", {})
        options = dict(previous.get("kwargs", {}))
        if cnf is not None:
            options.update(cnf)
        options.update(kwargs)
        self._parent_frame.grid(**options)

    def destroy(self) -> None:
        if self._managed_destroyed:
            return
        self._managed_destroyed = True
        if self._scrollregion_after_id is not None:
            try:
                self.after_cancel(self._scrollregion_after_id)
            except tk.TclError:
                pass
            self._scrollregion_after_id = None
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
