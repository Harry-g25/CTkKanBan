"""Visual tokens derived from the active CustomTkinter color theme."""

from __future__ import annotations

from copy import deepcopy
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
        # Board and toolbar geometry/typography.
        "board_padding_x": 18,
        "board_padding_y": (12, 16),
        "toolbar_height": 66,
        "toolbar_corner_radius": 12,
        "toolbar_padding_x": 18,
        "toolbar_padding_y": (16, 0),
        "toolbar_content_padding_y": 12,
        "toolbar_title_font": {"size": 17, "weight": "bold"},
        "toolbar_summary_font": {"size": 10},
        "search_width": 220,
        "button_height": 36,
        "control_corner_radius": 8,
        "small_control_size": 32,
        # Column geometry/typography.
        "column_corner_radius": 12,
        "column_border_width": 1,
        "column_gap": 7,
        "column_accent_height": 3,
        "column_header_padding_x": 12,
        "column_title_font": {"size": 15, "weight": "bold"},
        "column_count_font": {"size": 11, "weight": "bold"},
        "column_empty_title_font": {"size": 13, "weight": "bold"},
        "column_empty_body_font": {"size": 11},
        "card_gap": 6,
        # Card geometry/typography and compact-value limits.
        "card_corner_radius": 10,
        "card_border_width": 1,
        "card_selected_border_width": 2,
        "card_accent_width": 4,
        "card_title_font": {"size": 14, "weight": "bold"},
        "card_body_font": {"size": 11},
        "card_metadata_font": {"size": 10},
        "card_description_max_chars": 150,
        "card_max_visible_tags": 4,
        "pill_height": 21,
        "pill_corner_radius": 7,
        "pill_font": {"size": 10, "weight": "bold"},
        # Editor geometry/typography.
        "editor_border_width": 1,
        "editor_header_padding_x": 20,
        "editor_header_padding_y": (17, 15),
        "editor_form_padding_x": (18, 10),
        "editor_form_padding_y": (16, 8),
        "editor_field_padding_x": 14,
        "editor_field_gap": 13,
        "editor_section_gap": 12,
        "editor_section_corner_radius": 10,
        "editor_section_border_width": 1,
        "editor_section_title_padding_y": (14, 12),
        "editor_slide_step": 70,
        "editor_slide_interval_ms": 12,
        "editor_eyebrow_font": {"size": 10, "weight": "bold"},
        "editor_title_font": {"size": 21, "weight": "bold"},
        "editor_status_font": {"size": 9, "weight": "bold"},
        "section_title_font": {"size": 14, "weight": "bold"},
        "field_label_font": {"size": 11, "weight": "bold"},
        "help_text_font": {"size": 11},
        "status_text_font": {"size": 11},
        "input_height": 36,
        "compact_input_height": 34,
        "input_corner_radius": 9,
        "input_border_width": 1,
        "textbox_height": 105,
        "scrollbar_width": 7,
        "error_text_color": ("#B91C1C", "#FCA5A5"),
        # Native Tk context-menu colors.
        "menu_fg_color": _color(frame["fg_color"]),
        "menu_text_color": _color(label["text_color"]),
        "menu_hover_color": _color(dropdown["hover_color"]),
        "menu_disabled_text_color": _color(entry["placeholder_text_color"]),
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
        for key, value in overrides.items():
            try:
                theme[key] = deepcopy(value)
            except Exception:
                theme[key] = value
    return theme


__all__ = ["DEFAULT_THEME", "merge_theme"]
