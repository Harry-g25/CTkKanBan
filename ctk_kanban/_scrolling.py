"""Scrollable frame with explicit cleanup for CustomTkinter global bindings."""

from __future__ import annotations

import sys
import tkinter as tk
import weakref
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, cast

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


@dataclass(slots=True)
class _ScrollRouterState:
    root: tk.Misc
    frames: weakref.WeakSet[ManagedScrollableFrame] = field(default_factory=weakref.WeakSet)
    bindings: list[tuple[str, str]] = field(default_factory=list)


class _GlobalScrollRouter:
    """Share one set of global wheel bindings across every managed frame."""

    _states: dict[int, _ScrollRouterState] = {}

    @classmethod
    def register(cls, frame: ManagedScrollableFrame) -> tk.Misc:
        root = frame._root()
        key = id(root)
        state = cls._states.get(key)
        if state is None:
            state = _ScrollRouterState(root)
            cls._states[key] = state
            callbacks: tuple[tuple[str, Callable[[tk.Event[Any]], Any]], ...] = (
                ("<MouseWheel>", partial(cls._mouse_wheel, state)),
                ("<KeyPress-Shift_L>", partial(cls._shift_event, state, True)),
                ("<KeyPress-Shift_R>", partial(cls._shift_event, state, True)),
                ("<KeyRelease-Shift_L>", partial(cls._shift_event, state, False)),
                ("<KeyRelease-Shift_R>", partial(cls._shift_event, state, False)),
            )
            for sequence, callback in callbacks:
                func_id = root.bind_all(sequence, callback, add="+")
                if func_id is not None:
                    state.bindings.append((sequence, func_id))
        state.frames.add(frame)
        return root

    @classmethod
    def unregister(cls, frame: ManagedScrollableFrame, root: tk.Misc | None) -> None:
        if root is None:
            return
        key = id(root)
        state = cls._states.get(key)
        if state is None:
            return
        state.frames.discard(frame)
        if state.frames:
            return
        for sequence, func_id in state.bindings:
            try:
                _unbind_global_callback(root, sequence, func_id)
            except tk.TclError:
                pass
        cls._states.pop(key, None)

    @staticmethod
    def _set_shift(state: _ScrollRouterState, pressed: bool) -> None:
        for frame in tuple(state.frames):
            frame._shift_pressed = pressed

    @classmethod
    def _shift_event(
        cls,
        state: _ScrollRouterState,
        pressed: bool,
        _event: tk.Event[Any],
    ) -> None:
        cls._set_shift(state, pressed)

    @classmethod
    def _mouse_wheel(cls, state: _ScrollRouterState, event: tk.Event[Any]) -> None:
        nearest = ManagedScrollableFrame._nearest_managed_scrollable(event.widget)
        if nearest is None or nearest not in state.frames:
            nearest = next(
                (
                    frame
                    for frame in state.frames
                    if event.widget is getattr(frame, "_parent_canvas", None)
                ),
                None,
            )
        if nearest is None:
            return

        if nearest._shift_pressed:
            target = cls._horizontal_ancestor(nearest)
            if target is not None:
                target._scroll_canvas(event, horizontal=True)
            return

        if nearest._orientation == "vertical":
            try:
                if nearest._parent_canvas.yview() != (0.0, 1.0):
                    nearest._scroll_canvas(event, horizontal=False)
                    return
            except tk.TclError:
                return
        target = cls._horizontal_ancestor(nearest)
        if target is not None:
            target._scroll_canvas(event, horizontal=True)

    @staticmethod
    def _horizontal_ancestor(
        frame: ManagedScrollableFrame,
    ) -> ManagedScrollableFrame | None:
        current: Any = frame
        while current is not None:
            if isinstance(current, ManagedScrollableFrame) and current._orientation == "horizontal":
                return current
            current = getattr(current, "master", None)
        return None


class ManagedScrollableFrame(ctk.CTkScrollableFrame):
    """Remove the ``bind_all`` callbacks installed by CTkScrollableFrame.

    CustomTkinter installs wheel and Shift-key callbacks for every scrollable
    frame but does not unregister them when a nested frame is destroyed.  The
    board deliberately rebuilds its small visual tree, so retaining those
    callbacks would make scrolling slower after every edit.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        defer_initial_flush = bool(kwargs.pop("_defer_initial_scrollbar_flush", False))
        self._managed_global_bindings: list[tuple[str, str]] = []
        self._managed_destroyed = False
        self._suppress_ctk_global_bindings = True
        self._managed_root: tk.Misc | None = None
        self._scrollregion_after_id: str | None = None
        self._scrollbar_draw_after_id: str | None = None
        self._last_scrollbar_view: tuple[float, float] | None = None
        # CTkScrollbar._draw() flushes every pending idle task. During a
        # scrollable frame's constructor that settles the entire partially
        # built board once per scrollbar. Suppress only that eager flush and
        # allow Tk to settle the completed widget tree normally.
        original_class_draw = ctk.CTkScrollbar._draw

        def initial_draw(scrollbar: Any, no_color_updates: bool = False) -> None:
            canvas = getattr(scrollbar, "_canvas", None)
            if canvas is None:
                original_class_draw(scrollbar, no_color_updates)
                return
            flush = canvas.update_idletasks
            canvas.update_idletasks = lambda: None
            try:
                original_class_draw(scrollbar, no_color_updates)
            finally:
                canvas.update_idletasks = flush

        if defer_initial_flush:
            ctk.CTkScrollbar._draw = initial_draw
        try:
            super().__init__(*args, **kwargs)
        finally:
            if defer_initial_flush:
                ctk.CTkScrollbar._draw = original_class_draw
        self._scrollbar_original_draw: Callable[..., Any] = self._scrollbar._draw
        self._scrollbar._draw = self._draw_scrollbar_without_idle_flush
        self._suppress_ctk_global_bindings = False
        self._managed_root = _GlobalScrollRouter.register(self)
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
        if self._suppress_ctk_global_bindings:
            return None
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
        """Coalesce expensive compound-scrollbar redraws until Tk is idle."""

        view = (float(first), float(last))
        if view == self._last_scrollbar_view:
            return
        self._last_scrollbar_view = view
        self._scrollbar._start_value, self._scrollbar._end_value = view
        if self._scrollbar_draw_after_id is not None:
            return
        try:
            self._scrollbar_draw_after_id = self.after_idle(self._draw_scrollbar)
        except tk.TclError:
            pass

    def _draw_scrollbar(self) -> None:
        self._scrollbar_draw_after_id = None
        if self._managed_destroyed:
            return
        try:
            self._scrollbar._draw(no_color_updates=True)
        except (AttributeError, tk.TclError):
            try:
                self._scrollbar.set(*cast(tuple[float, float], self._last_scrollbar_view))
            except (AttributeError, tk.TclError, TypeError):
                pass

    def _draw_scrollbar_without_idle_flush(self, no_color_updates: bool = False) -> None:
        self._without_scrollbar_idle_flush(
            self._scrollbar_original_draw,
            no_color_updates=no_color_updates,
        )

    def _without_scrollbar_idle_flush(
        self,
        callback: Callable[..., Any],
        **kwargs: Any,
    ) -> None:
        """Run a CTk scrollbar draw without recursively flushing the whole UI."""

        canvas = self._scrollbar._canvas
        flush = canvas.update_idletasks
        canvas.update_idletasks = lambda: None
        try:
            callback(**kwargs)
        finally:
            canvas.update_idletasks = flush

    def set_scrollbar_thickness(self, thickness: int) -> None:
        """Size the compound scrollbar without forcing an eager Tk layout pass."""

        dimension = "height" if self._orientation == "horizontal" else "width"
        try:
            self._without_scrollbar_idle_flush(
                self._scrollbar.configure,
                **{dimension: thickness},
            )
        except (AttributeError, tk.TclError):
            self._scrollbar.configure(**{dimension: thickness})

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
            self._fit_frame_dimensions_to_canvas()
        except tk.TclError:
            pass

    def refresh_scrollregion(self) -> None:
        """Synchronously measure settled content without flushing all Tk idle work."""

        if self._scrollregion_after_id is not None:
            try:
                self.after_cancel(self._scrollregion_after_id)
            except tk.TclError:
                pass
            self._scrollregion_after_id = None
        self._refresh_scrollregion()

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
        if self._scrollbar_draw_after_id is not None:
            try:
                self.after_cancel(self._scrollbar_draw_after_id)
            except tk.TclError:
                pass
            self._scrollbar_draw_after_id = None
        root = self._managed_root or self._root()
        _GlobalScrollRouter.unregister(self, self._managed_root)
        self._managed_root = None
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
