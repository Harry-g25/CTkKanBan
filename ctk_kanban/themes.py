"""Default light/dark theme values for the Kanban widgets.

The defaults intentionally follow CustomTkinter's standard ``blue`` theme so
the board looks native in an otherwise uncustomized CTk application.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


DEFAULT_THEME: dict[str, Any] = {
    "board_fg_color": ("gray92", "gray14"),
    "board_corner_radius": 0,
    "toolbar_fg_color": ("gray86", "gray17"),
    "toolbar_border_color": ("gray65", "gray28"),
    "toolbar_border_width": 0,
    "toolbar_corner_radius": 6,
    "toolbar_text_color": ("gray10", "#DCE4EE"),
    "toolbar_button_text_color": ("gray10", "#DCE4EE"),
    "toolbar_primary_button_text_color": ("#DCE4EE", "#DCE4EE"),
    "column_fg_color": ("gray86", "gray17"),
    "column_header_fg_color": ("gray81", "gray20"),
    "column_border_color": ("gray65", "gray28"),
    "column_border_width": 0,
    "column_corner_radius": 6,
    "column_header_corner_radius": 6,
    "column_title_text_color": ("gray10", "#DCE4EE"),
    "column_count_fg_color": ("gray78", "gray23"),
    "column_count_text_color": ("gray10", "#DCE4EE"),
    "column_control_hover_color": ("gray75", "gray28"),
    "column_no_results_text_color": ("gray52", "gray62"),
    "card_fg_color": ("#F9F9FA", "#343638"),
    "card_hover_color": ("#EDEFF2", "#3B3D40"),
    "card_selected_color": ("#DCEBFA", "#27496D"),
    "card_border_color": ("#979DA2", "#565B5E"),
    "card_selected_border_color": ("#3B8ED0", "#1F6AA5"),
    "card_border_width": 1,
    "card_corner_radius": 6,
    "card_title_text_color": ("gray10", "#DCE4EE"),
    "card_body_text_color": ("gray28", "gray78"),
    "card_metadata_text_color": ("gray38", "gray68"),
    "button_fg_color": ("#3B8ED0", "#1F6AA5"),
    "button_hover_color": ("#36719F", "#144870"),
    "button_text_color": ("#DCE4EE", "#DCE4EE"),
    "button_text_color_disabled": ("gray74", "gray60"),
    "button_corner_radius": 6,
    "button_border_width": 0,
    "secondary_button_fg_color": ("gray78", "gray23"),
    "secondary_button_hover_color": ("gray75", "gray28"),
    "secondary_button_text_color": ("gray10", "#DCE4EE"),
    "secondary_button_text_color_disabled": ("gray60", "gray45"),
    "secondary_button_corner_radius": 6,
    "secondary_button_border_width": 0,
    "search_fg_color": ("#F9F9FA", "#343638"),
    "search_border_color": ("#979DA2", "#565B5E"),
    "search_text_color": ("gray10", "#DCE4EE"),
    "search_placeholder_text_color": ("gray52", "gray62"),
    "input_fg_color": ("#F9F9FA", "#343638"),
    "input_border_color": ("#979DA2", "#565B5E"),
    "input_text_color": ("gray10", "#DCE4EE"),
    "input_placeholder_text_color": ("gray52", "gray62"),
    "input_corner_radius": 6,
    "input_border_width": 2,
    "textbox_fg_color": ("#F9F9FA", "#1D1E1E"),
    "textbox_border_color": ("#979DA2", "#565B5E"),
    "textbox_text_color": ("gray10", "#DCE4EE"),
    "textbox_corner_radius": 6,
    "textbox_border_width": 0,
    "checkbox_fg_color": ("#3B8ED0", "#1F6AA5"),
    "checkbox_hover_color": ("#36719F", "#144870"),
    "checkbox_border_color": ("#3E454A", "#949A9F"),
    "checkbox_checkmark_color": ("#DCE4EE", "gray90"),
    "checkbox_text_color": ("gray10", "#DCE4EE"),
    "checkbox_text_color_disabled": ("gray60", "gray45"),
    "checkbox_corner_radius": 6,
    "checkbox_border_width": 3,
    "optionmenu_fg_color": ("#3B8ED0", "#1F6AA5"),
    "optionmenu_button_color": ("#36719F", "#144870"),
    "optionmenu_button_hover_color": ("#27577D", "#203A4F"),
    "optionmenu_text_color": ("#DCE4EE", "#DCE4EE"),
    "optionmenu_text_color_disabled": ("gray74", "gray60"),
    "optionmenu_dropdown_fg_color": ("gray90", "gray20"),
    "optionmenu_dropdown_hover_color": ("gray75", "gray28"),
    "optionmenu_dropdown_text_color": ("gray10", "gray90"),
    "optionmenu_corner_radius": 6,
    "dialog_fg_color": ("gray92", "gray14"),
    "dialog_border_color": ("gray65", "gray28"),
    "dialog_border_width": 0,
    "dialog_corner_radius": 6,
    "dialog_title_text_color": ("gray10", "#DCE4EE"),
    "dialog_text_color": ("gray10", "#DCE4EE"),
    "panel_fg_color": ("gray86", "gray17"),
    "panel_border_color": ("gray65", "gray28"),
    "panel_border_width": 0,
    "panel_corner_radius": 6,
    "panel_title_text_color": ("gray10", "#DCE4EE"),
    "menu_fg_color": ("gray90", "gray20"),
    "menu_hover_color": ("gray75", "gray28"),
    "menu_text_color": ("gray10", "gray90"),
    "menu_hover_text_color": ("gray10", "gray90"),
    "menu_disabled_text_color": ("gray60", "gray50"),
    "menu_border_width": 0,
    "scrollbar_button_color": ("gray55", "gray41"),
    "scrollbar_button_hover_color": ("gray40", "gray53"),
    "drop_indicator_color": ("#3B8ED0", "#1F6AA5"),
    "drag_preview_fg_color": ("gray90", "gray20"),
    "drag_preview_text_color": ("gray10", "#DCE4EE"),
    "tag_fg_color": ("gray81", "gray29"),
    "tag_text_color": ("gray10", "#DCE4EE"),
    "badge_text_color": ("#DCE4EE", "#DCE4EE"),
    "danger_color": ("#C42B1C", "#FF6B6B"),
    "muted_text_color": ("gray38", "gray68"),
    "text_color": ("gray10", "#DCE4EE"),
    "overlay_text_color": ("gray52", "gray62"),
    "corner_radius": 6,
    "border_width": 0,
    "board_padding": 12,
    "card_gap": 8,
    "card_min_height": 64,
}

DEFAULT_STYLE = DEFAULT_THEME

DEFAULT_PRIORITY_COLORS: dict[str, str] = {
    "Critical": "#B91C1C",
    "High": "#EF4444",
    "Medium": "#F59E0B",
    "Low": "#10B981",
}


def merge_theme(theme: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a defensive copy of defaults updated by *theme*."""

    merged = deepcopy(DEFAULT_THEME)
    if theme:
        merged.update(deepcopy(dict(theme)))
    return merged


def merge_style(style: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Alias for :func:`merge_theme` for callers who prefer ``style`` naming."""

    return merge_theme(style)
