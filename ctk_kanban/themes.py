"""Theme values derived from the active CustomTkinter color theme."""

from __future__ import annotations

from typing import Any, Mapping

import customtkinter as ctk


def _color(value: Any) -> Any:
    """Detach list-based CustomTkinter colors from its global theme mapping."""

    return tuple(value) if isinstance(value, list) else value


def _customtkinter_defaults() -> dict[str, Any]:
    theme = ctk.ThemeManager.theme
    frame = theme["CTkFrame"]
    button = theme["CTkButton"]
    label = theme["CTkLabel"]
    entry = theme["CTkEntry"]
    scrollbar = theme["CTkScrollbar"]
    dropdown = theme["DropdownMenu"]
    return {
        "board_fg_color": _color(frame["fg_color"]),
        "toolbar_fg_color": _color(frame["top_fg_color"]),
        "column_fg_color": _color(frame["top_fg_color"]),
        "column_header_fg_color": "transparent",
        "column_border_color": _color(frame["border_color"]),
        "column_accent_colors": (
            ("#2563EB", "#60A5FA"),
            ("#B45309", "#F59E0B"),
            ("#15803D", "#4ADE80"),
            ("#7C3AED", "#A78BFA"),
            ("#0F766E", "#2DD4BF"),
        ),
        "card_fg_color": _color(frame["fg_color"]),
        "card_hover_color": _color(frame["top_fg_color"]),
        "dragging_card_fg_color": _color(frame["top_fg_color"]),
        "card_border_color": _color(frame["border_color"]),
        "selected_border_color": _color(button["fg_color"]),
        "drop_indicator_color": _color(button["fg_color"]),
        "text_color": _color(label["text_color"]),
        "muted_text_color": _color(entry["placeholder_text_color"]),
        "accent_color": _color(button["fg_color"]),
        "control_hover_color": _color(dropdown["hover_color"]),
        "count_fg_color": _color(frame["fg_color"]),
        "empty_icon_fg_color": _color(frame["fg_color"]),
        "editor_fg_color": _color(frame["top_fg_color"]),
        "editor_section_fg_color": _color(frame["fg_color"]),
        "divider_color": _color(frame["border_color"]),
        "input_border_color": _color(entry["border_color"]),
        "scrollbar_color": _color(scrollbar["button_color"]),
        "scrollbar_hover_color": _color(scrollbar["button_hover_color"]),
        "danger_color": ("#B42318", "#F97066"),
        "pill_text_color": _color(button["text_color"]),
        "priority_low_color": ("#2E7D32", "#2E7D32"),
        "priority_medium_color": ("#9A6700", "#9A6700"),
        "priority_high_color": ("#B54708", "#B54708"),
        "priority_critical_color": ("#B42318", "#B42318"),
        "tag_pill_colors": (
            ("#475467", "#475467"),
            ("#067647", "#067647"),
            ("#6941C6", "#6941C6"),
            ("#B54708", "#B54708"),
            ("#C11574", "#C11574"),
        ),
    }


# Public snapshot for discovery. ``merge_theme`` starts from a fresh snapshot
# so a color theme selected after import is still respected by new boards.
DEFAULT_THEME: dict[str, Any] = _customtkinter_defaults()


def merge_theme(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    theme = _customtkinter_defaults()
    if overrides:
        unknown = set(overrides) - set(DEFAULT_THEME)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown theme keys: {names}")
        theme.update(overrides)
    return theme


__all__ = ["DEFAULT_THEME", "merge_theme"]
