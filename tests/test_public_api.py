"""The v2 package deliberately exposes a small public surface."""

import customtkinter as ctk
import pytest

import ctk_kanban


def test_public_api_is_intentionally_small() -> None:
    assert set(ctk_kanban.__all__) == {
        "CTkKanbanBoard",
        "ActionConfig",
        "BoardConfig",
        "BoardModel",
        "BoardModelError",
        "BoardSnapshot",
        "Card",
        "CardField",
        "CardRecord",
        "Column",
        "ColumnRecord",
        "DEFAULT_FIELDS",
        "DEFAULT_THEME",
        "Field",
        "FieldDefinition",
        "FieldInput",
        "FieldType",
        "LayoutConfig",
        "TextConfig",
        "merge_config",
        "merge_theme",
        "normalize_row",
        "normalize_rows",
        "rows_from_cursor",
        "snapshot_from_cursors",
        "snapshot_from_rows",
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


def test_structured_config_is_partial_and_strict() -> None:
    config = ctk_kanban.merge_config(
        {
            "actions": {"delete_cards": False},
            "layout": {
                "editor_width": 500,
                "fill_columns": True,
                "use_builtin_editor": False,
            },
            "text": {"board_title": "Roadmap"},
        }
    )

    assert not config.actions.delete_cards
    assert config.actions.add_cards
    assert config.layout.editor_width == 500
    assert config.layout.fill_columns
    assert not config.layout.use_builtin_editor
    assert config.text.board_title == "Roadmap"
    with pytest.raises(ValueError, match="unknown action"):
        ctk_kanban.merge_config({"actions": {"explode_cards": True}})
    with pytest.raises(TypeError, match="layout.fill_columns"):
        ctk_kanban.merge_config({"layout": {"fill_columns": 1}})
