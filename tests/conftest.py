"""Shared fixtures for the small GUI test surface."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator

import customtkinter as ctk
import pytest


@pytest.fixture(scope="session")
def _tk_session() -> Iterator[ctk.CTk]:
    """Create Tk lazily, so missing GUI support never breaks collection."""

    try:
        root = ctk.CTk()
    except (tk.TclError, RuntimeError) as exc:
        pytest.skip(f"Tk is unavailable: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.update_idletasks()
            root.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def tk_root(_tk_session: ctk.CTk) -> Iterator[ctk.CTk]:
    """Reuse CustomTkinter's root but isolate each test's child widgets."""

    yield _tk_session
    for child in _tk_session.winfo_children():
        try:
            child.destroy()
        except (AttributeError, tk.TclError):
            pass
    _tk_session.update_idletasks()
    _tk_session.withdraw()
