"""The v2 package deliberately exposes a small public surface."""

import customtkinter as ctk
import pytest

import ctk_kanban


def test_public_api_is_intentionally_small() -> None:
    assert set(ctk_kanban.__all__) == {
        "CTkKanbanBoard",
        "BoardModel",
        "BoardModelError",
        "Card",
        "Column",
        "DEFAULT_THEME",
        "merge_theme",
        "__version__",
    }


def test_unknown_theme_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown theme keys"):
        ctk_kanban.merge_theme({"mystery": "red"})


def test_default_theme_follows_customtkinter() -> None:
    theme = ctk_kanban.merge_theme()
    native = ctk.ThemeManager.theme

    assert theme["card_fg_color"] == tuple(native["CTkFrame"]["fg_color"])
    assert theme["text_color"] == tuple(native["CTkLabel"]["text_color"])
    assert theme["selected_border_color"] == tuple(native["CTkButton"]["fg_color"])
