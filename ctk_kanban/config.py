"""Typed behavior, layout, and text configuration for CTkKanban."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, TypeVar


@dataclass(frozen=True, slots=True)
class ActionConfig:
    """Enable or disable user-visible and public board mutations."""

    add_cards: bool = True
    edit_cards: bool = True
    move_cards: bool = True
    delete_cards: bool = True
    add_columns: bool = True
    edit_columns: bool = True
    move_columns: bool = True
    delete_columns: bool = True


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    """Board sizing and major visibility choices."""

    show_toolbar: bool = True
    enable_drag: bool = True
    use_builtin_editor: bool = True
    fill_columns: bool = False
    card_size: str = "normal"
    column_width: int = 320
    column_height: int = 500
    editor_width: int = 420


@dataclass(frozen=True, slots=True)
class TextConfig:
    """User-facing labels that applications commonly need to customize."""

    board_title: str = "Board"
    search_placeholder: str = "Search cards…"
    add_card: str = "+  Add card"
    add_column: str = "Add column"
    no_columns: str = "No columns yet"
    no_columns_help: str = "Create a column to start planning"
    no_cards: str = "No cards yet"
    no_cards_help: str = "Add a card to get started"
    no_results: str = "No results"
    no_results_help: str = "Try another search"


@dataclass(frozen=True, slots=True)
class BoardConfig:
    """Structured configuration that avoids a large constructor flag list."""

    actions: ActionConfig = field(default_factory=ActionConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    text: TextConfig = field(default_factory=TextConfig)
    confirm_delete: bool = True


_ConfigType = TypeVar("_ConfigType", ActionConfig, LayoutConfig, TextConfig)


def _from_mapping(cls: type[_ConfigType], value: Mapping[str, Any], name: str) -> _ConfigType:
    allowed = set(cls.__dataclass_fields__)
    unknown = set(value) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown {name} configuration option(s): {names}")
    return cls(**dict(value))


def merge_config(config: BoardConfig | Mapping[str, Any] | None = None) -> BoardConfig:
    """Validate a board configuration object or nested mapping."""

    if config is None:
        result = BoardConfig()
    elif isinstance(config, BoardConfig):
        result = config
    elif isinstance(config, Mapping):
        unknown = set(config) - {"actions", "layout", "text", "confirm_delete"}
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown board configuration option(s): {names}")
        actions = config.get("actions", {})
        layout = config.get("layout", {})
        text = config.get("text", {})
        result = BoardConfig(
            actions=(
                actions
                if isinstance(actions, ActionConfig)
                else _from_mapping(ActionConfig, actions, "action")
            ),
            layout=(
                layout
                if isinstance(layout, LayoutConfig)
                else _from_mapping(LayoutConfig, layout, "layout")
            ),
            text=(text if isinstance(text, TextConfig) else _from_mapping(TextConfig, text, "text")),
            confirm_delete=config.get("confirm_delete", True),
        )
    else:
        raise TypeError("config must be a BoardConfig, mapping, or None")

    for name, value in asdict(result.actions).items():
        if not isinstance(value, bool):
            raise TypeError(f"actions.{name} must be a bool")
    for name in ("show_toolbar", "enable_drag", "use_builtin_editor", "fill_columns"):
        if not isinstance(getattr(result.layout, name), bool):
            raise TypeError(f"layout.{name} must be a bool")
    if not isinstance(result.layout.card_size, str):
        raise TypeError("layout.card_size must be a string")
    if result.layout.card_size not in {"compact", "normal", "large"}:
        raise ValueError("layout.card_size must be 'compact', 'normal', or 'large'")
    limits = {
        "column_width": (result.layout.column_width, 220),
        "column_height": (result.layout.column_height, 240),
        "editor_width": (result.layout.editor_width, 320),
    }
    for name, (value, minimum) in limits.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"layout.{name} must be an integer of at least {minimum}")
    for name, value in asdict(result.text).items():
        if not isinstance(value, str):
            raise TypeError(f"text.{name} must be a string")
    if not isinstance(result.confirm_delete, bool):
        raise TypeError("confirm_delete must be a bool")
    return result


__all__ = ["ActionConfig", "BoardConfig", "LayoutConfig", "TextConfig", "merge_config"]
