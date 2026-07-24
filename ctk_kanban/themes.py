"""Default light/dark theme values for the Kanban widgets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

DEFAULT_THEME: dict[str, Any] = {
    "board_fg_color": ("#F3F6FA", "#0A0F1C"),
    "board_corner_radius": 0,
    "toolbar_fg_color": ("#FFFFFF", "#111827"),
    "toolbar_border_color": ("#E2E8F0", "#263247"),
    "toolbar_border_width": 1,
    "toolbar_corner_radius": 14,
    "toolbar_text_color": ("#334155", "#D7E0EC"),
    "toolbar_button_text_color": ("#334155", "#D7E0EC"),
    "toolbar_primary_button_text_color": ("#FFFFFF", "#FFFFFF"),
    "toolbar_summary_text_color": ("#64748B", "#93A4BA"),
    "toolbar_count_fg_color": ("#EEF2F7", "#1B273A"),
    "toolbar_context_fg_color": ("#F8FAFC", "#0E1726"),
    "toolbar_context_border_color": ("#E8EDF3", "#243147"),
    "toolbar_action_border_color": ("#E2E8F0", "#2A3950"),
    "toolbar_height": 64,
    "toolbar_search_width": 400,
    "column_fg_color": ("#E9EEF5", "#111827"),
    "column_header_fg_color": "transparent",
    "column_border_color": ("#DCE3EC", "#243147"),
    "column_border_width": 1,
    "column_corner_radius": 14,
    "column_header_corner_radius": 10,
    "column_title_text_color": ("#172033", "#F1F5F9"),
    "column_count_fg_color": ("#DDE5EF", "#243147"),
    "column_count_text_color": ("#475569", "#C5D1DF"),
    "column_count_full_fg_color": ("#FEE2E2", "#4C1D25"),
    "column_count_full_text_color": ("#B91C1C", "#FCA5A5"),
    "column_control_fg_color": ("#F8FAFC", "#182235"),
    "column_control_hover_color": ("#E2E8F0", "#26354D"),
    "column_lock_fg_color": ("#FEF3C7", "#493518"),
    "column_lock_text_color": ("#92400E", "#FCD34D"),
    "column_no_results_text_color": ("#64748B", "#8292A8"),
    "column_empty_fg_color": ("#F5F8FB", "#141E2F"),
    "column_empty_border_color": ("#D8E0EA", "#2A3950"),
    "column_accent_height": 3,
    "column_header_height": 46,
    "card_fg_color": ("#FFFFFF", "#182235"),
    "card_hover_color": ("#F8FAFC", "#1D2A40"),
    "card_hover_border_color": ("#CBD5E1", "#3A4B65"),
    "card_selected_color": ("#EFF6FF", "#172F52"),
    "card_border_color": ("#DFE6EE", "#2A3950"),
    "card_selected_border_color": ("#3B82F6", "#60A5FA"),
    "card_search_border_color": ("#F59E0B", "#FBBF24"),
    "card_border_width": 1,
    "card_corner_radius": 12,
    "card_title_text_color": ("#172033", "#F1F5F9"),
    "card_body_text_color": ("#475569", "#B6C2D2"),
    "card_metadata_text_color": ("#475569", "#B6C2D2"),
    "card_metadata_label_text_color": ("#64748B", "#93A4BA"),
    "card_metadata_fg_color": ("#F5F7FA", "#121B2A"),
    "card_priority_fg_color": ("#F1F5F9", "#263247"),
    "card_drag_handle_color": ("#A3AFBF", "#66778F"),
    "card_accent_default_color": ("#CBD5E1", "#475569"),
    "card_separator_color": ("#EDF1F5", "#263247"),
    "card_accent_width": 4,
    "card_description_max_chars": 128,
    "button_fg_color": ("#2563EB", "#3B82F6"),
    "button_hover_color": ("#1D4ED8", "#2563EB"),
    "button_text_color": ("#FFFFFF", "#FFFFFF"),
    "button_text_color_disabled": ("#94A3B8", "#64748B"),
    "button_corner_radius": 10,
    "button_border_width": 0,
    "secondary_button_fg_color": ("#F1F5F9", "#1B273A"),
    "secondary_button_hover_color": ("#E2E8F0", "#26354D"),
    "secondary_button_text_color": ("#334155", "#D7E0EC"),
    "secondary_button_text_color_disabled": ("#94A3B8", "#64748B"),
    "secondary_button_corner_radius": 10,
    "secondary_button_border_width": 0,
    "filter_chip_fg_color": ("#E8F0FE", "#1C3152"),
    "filter_chip_text_color": ("#1D4ED8", "#93C5FD"),
    "search_fg_color": ("#F8FAFC", "#0E1726"),
    "search_border_color": ("#D7E0EA", "#2A3950"),
    "search_focus_border_color": ("#3B82F6", "#60A5FA"),
    "search_text_color": ("#172033", "#F1F5F9"),
    "search_placeholder_text_color": ("#94A3B8", "#64748B"),
    "input_fg_color": ("#FFFFFF", "#111B2A"),
    "input_border_color": ("#D7E0EA", "#2A3950"),
    "input_text_color": ("#172033", "#F1F5F9"),
    "input_placeholder_text_color": ("#94A3B8", "#64748B"),
    "input_corner_radius": 9,
    "input_border_width": 1,
    "textbox_fg_color": ("#FFFFFF", "#111B2A"),
    "textbox_border_color": ("#D7E0EA", "#2A3950"),
    "textbox_text_color": ("#172033", "#F1F5F9"),
    "textbox_corner_radius": 9,
    "textbox_border_width": 1,
    "checkbox_fg_color": ("#2563EB", "#3B82F6"),
    "checkbox_hover_color": ("#1D4ED8", "#2563EB"),
    "checkbox_border_color": ("#94A3B8", "#64748B"),
    "checkbox_checkmark_color": ("#FFFFFF", "#FFFFFF"),
    "checkbox_text_color": ("#334155", "#D7E0EC"),
    "checkbox_text_color_disabled": ("#94A3B8", "#64748B"),
    "checkbox_corner_radius": 6,
    "checkbox_border_width": 2,
    "optionmenu_fg_color": ("#FFFFFF", "#111B2A"),
    "optionmenu_button_color": ("#EEF2F7", "#1B273A"),
    "optionmenu_button_hover_color": ("#E2E8F0", "#26354D"),
    "optionmenu_text_color": ("#172033", "#F1F5F9"),
    "optionmenu_text_color_disabled": ("#94A3B8", "#64748B"),
    "optionmenu_dropdown_fg_color": ("#FFFFFF", "#182235"),
    "optionmenu_dropdown_hover_color": ("#EFF6FF", "#263B5C"),
    "optionmenu_dropdown_text_color": ("#172033", "#F1F5F9"),
    "optionmenu_corner_radius": 9,
    "dialog_fg_color": ("#FFFFFF", "#111827"),
    "dialog_border_color": ("#E2E8F0", "#263247"),
    "dialog_border_width": 1,
    "dialog_corner_radius": 14,
    "dialog_title_text_color": ("#172033", "#F1F5F9"),
    "dialog_text_color": ("#334155", "#D7E0EC"),
    "dialog_subtitle_text_color": ("#64748B", "#93A4BA"),
    "dialog_divider_color": ("#E8EDF3", "#243147"),
    "dialog_section_fg_color": ("#F8FAFC", "#0E1726"),
    "dialog_section_border_color": ("#E8EDF3", "#243147"),
    "panel_fg_color": ("#FFFFFF", "#111827"),
    "panel_border_color": ("#E2E8F0", "#263247"),
    "panel_border_width": 1,
    "panel_corner_radius": 14,
    "panel_title_text_color": ("#172033", "#F1F5F9"),
    "form_header_subtitle_text_color": ("#64748B", "#93A4BA"),
    "form_footer_fg_color": ("#F8FAFC", "#0E1726"),
    "form_divider_color": ("#E8EDF3", "#243147"),
    "menu_fg_color": ("#FFFFFF", "#182235"),
    "menu_hover_color": ("#EFF6FF", "#263B5C"),
    "menu_text_color": ("#172033", "#F1F5F9"),
    "menu_hover_text_color": ("#1D4ED8", "#BFDBFE"),
    "menu_disabled_text_color": ("#94A3B8", "#64748B"),
    "menu_border_width": 0,
    "scrollbar_button_color": ("#CBD5E1", "#334155"),
    "scrollbar_button_hover_color": ("#94A3B8", "#475569"),
    "tooltip_fg_color": ("#172033", "#E2E8F0"),
    "tooltip_text_color": ("#FFFFFF", "#172033"),
    "tooltip_border_color": ("#334155", "#CBD5E1"),
    "calendar_fg_color": ("#FFFFFF", "#111827"),
    "calendar_weekday_text_color": ("#64748B", "#93A4BA"),
    "calendar_day_hover_color": ("#EFF6FF", "#263B5C"),
    "calendar_selected_fg_color": ("#2563EB", "#3B82F6"),
    "calendar_selected_text_color": ("#FFFFFF", "#FFFFFF"),
    "calendar_today_fg_color": ("#E8F0FE", "#1C3152"),
    "calendar_today_text_color": ("#1D4ED8", "#93C5FD"),
    "drop_indicator_color": ("#2563EB", "#60A5FA"),
    "drag_preview_fg_color": ("#172033", "#E2E8F0"),
    "drag_preview_text_color": ("#FFFFFF", "#172033"),
    "tag_fg_color": ("#EEF2F7", "#263247"),
    "tag_text_color": ("#475569", "#CBD5E1"),
    "badge_text_color": ("#FFFFFF", "#FFFFFF"),
    "danger_color": ("#DC2626", "#F87171"),
    "danger_surface_color": ("#FEF2F2", "#471C24"),
    "success_color": ("#15803D", "#4ADE80"),
    "success_surface_color": ("#ECFDF3", "#153726"),
    "warning_color": ("#B45309", "#FBBF24"),
    "warning_surface_color": ("#FFFBEB", "#423016"),
    "muted_text_color": ("#64748B", "#93A4BA"),
    "text_color": ("#172033", "#F1F5F9"),
    "overlay_text_color": ("#8290A3", "#7F91A8"),
    "corner_radius": 10,
    "border_width": 0,
    "board_padding": 16,
    "responsive_preferred_min_column_width": 260,
    "card_gap": 12,
    "card_min_height": 68,
}

DEFAULT_STYLE = DEFAULT_THEME

DEFAULT_PRIORITY_COLORS: dict[str, str] = {
    "Critical": "#DC2626",
    "High": "#F97316",
    "Medium": "#EAB308",
    "Low": "#10B981",
}


def _copy_style_value(value: Any) -> Any:
    """Copy style containers while preserving Tk-backed resource objects.

    ``CTkFont`` and similar objects retain a reference to their Tcl interpreter
    and cannot be deep-copied.  Style mappings still need defensive copies for
    ordinary mutable containers, so copy those recursively and only preserve
    the identity of a leaf value when ``deepcopy`` is unsupported.
    """

    if isinstance(value, Mapping):
        return {key: _copy_style_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_style_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_style_value(item) for item in value)
    if isinstance(value, set):
        return {_copy_style_value(item) for item in value}
    try:
        return deepcopy(value)
    except Exception:  # Tk-backed resources cannot participate in Python deepcopy.
        return value


def merge_theme(theme: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a defensive copy of defaults updated by *theme*."""

    merged = _copy_style_value(DEFAULT_THEME)
    if theme:
        merged.update(_copy_style_value(theme))
    return merged


def merge_style(style: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Alias for :func:`merge_theme` for callers who prefer ``style`` naming."""

    return merge_theme(style)
