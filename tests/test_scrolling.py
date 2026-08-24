"""Compatibility checks for managed CustomTkinter scroll bindings."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ctk_kanban._scrolling import ManagedScrollableFrame, _unbind_global_callback


class _FakeInterpreter:
    def __init__(self, script: str) -> None:
        self.script = script

    def call(self, *arguments: Any) -> str:
        assert arguments[:3] == ("bind", "all", "<MouseWheel>")
        if len(arguments) == 3:
            return self.script
        self.script = str(arguments[3])
        return ""


class _FakeRoot:
    def __init__(self, script: str) -> None:
        self.tk = _FakeInterpreter(script)
        self.deleted_commands: list[str] = []

    def deletecommand(self, func_id: str) -> None:
        self.deleted_commands.append(func_id)


def test_unbind_global_callback_does_not_require_misc_private_helper() -> None:
    owned = "owned-command"
    sibling = "sibling-command"
    root = _FakeRoot(
        f'if {{"[{owned} %# %b]" == "break"}} break\n'
        f'if {{"[{sibling} %# %b]" == "break"}} break\n'
    )

    _unbind_global_callback(root, "<MouseWheel>", owned)  # type: ignore[arg-type]

    assert owned not in root.tk.script
    assert sibling in root.tk.script
    assert root.deleted_commands == [owned]


def test_scroll_containment_does_not_depend_on_customtkinter_private_helpers() -> None:
    canvas = SimpleNamespace(master=None)
    nested = SimpleNamespace(master=canvas)
    child = SimpleNamespace(master=nested)
    unrelated = SimpleNamespace(master=None)
    frame = object.__new__(ManagedScrollableFrame)
    frame._parent_canvas = canvas

    assert frame._contains_widget(canvas)
    assert frame._contains_widget(child)
    assert not frame._contains_widget(unrelated)
