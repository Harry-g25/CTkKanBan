"""Regression checks for the board's public styling surface."""

from __future__ import annotations

import unittest

import customtkinter as ctk

from ctk_kanban import CTkKanbanBoard, DEFAULT_STYLE
from gui_test_app import TEST_APP


def normalized(value: object) -> object:
    if isinstance(value, list):
        return tuple(value)
    return value


class StyleCustomizationTests(unittest.TestCase):
    app = TEST_APP

    def tearDown(self) -> None:
        for child in list(self.app.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.app.update_idletasks()

    def test_default_style_matches_customtkinter_blue_palette(self) -> None:
        self.assertEqual(DEFAULT_STYLE["board_fg_color"], ("gray92", "gray14"))
        self.assertEqual(DEFAULT_STYLE["button_fg_color"], ("#3B8ED0", "#1F6AA5"))
        self.assertEqual(DEFAULT_STYLE["button_hover_color"], ("#36719F", "#144870"))
        self.assertEqual(DEFAULT_STYLE["input_fg_color"], ("#F9F9FA", "#343638"))
        self.assertEqual(DEFAULT_STYLE["optionmenu_dropdown_fg_color"], ("gray90", "gray20"))
        self.assertEqual(DEFAULT_STYLE["corner_radius"], 6)

    def test_style_alias_merges_nested_maps_and_overrides_theme(self) -> None:
        toolbar_font = ctk.CTkFont(size=17)
        board = CTkKanbanBoard(
            self.app,
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[],
            show_toolbar=False,
            theme={"board_fg_color": "pink"},
            style={
                "board_fg_color": "gold",
                "priority_colors": {"Urgent": "#123456"},
                "tag_colors": {"API": "#654321"},
                "font_config": {"toolbar": toolbar_font},
            },
        )
        board.pack(fill="both", expand=True)
        self.app.update_idletasks()

        self.assertEqual(normalized(board.cget("fg_color")), "gold")
        self.assertEqual(board.priority_colors["Urgent"], "#123456")
        self.assertEqual(board.tag_colors["API"], "#654321")
        self.assertIs(board.font_config["toolbar"], toolbar_font)

        style_snapshot = board.get_style()
        self.assertEqual(style_snapshot["board_fg_color"], "gold")
        self.assertEqual(style_snapshot["priority_colors"]["Urgent"], "#123456")
        self.assertEqual(style_snapshot["tag_colors"]["API"], "#654321")
        self.assertIsInstance(style_snapshot["font_config"]["toolbar"], ctk.CTkFont)

    def test_toolbar_and_menus_read_style_keys(self) -> None:
        board = CTkKanbanBoard(
            self.app,
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[],
            style={
                "search_fg_color": "ivory",
                "search_border_color": "tomato",
                "search_text_color": "navy",
                "button_fg_color": "#123456",
                "button_hover_color": "#234567",
                "toolbar_primary_button_text_color": "khaki",
                "menu_fg_color": "black",
                "menu_text_color": "white",
                "menu_hover_color": "#222244",
                "menu_hover_text_color": "khaki",
                "menu_disabled_text_color": "#666666",
            },
        )
        board.pack(fill="both", expand=True)
        self.app.update_idletasks()

        self.assertEqual(normalized(board.toolbar.search_entry.cget("fg_color")), "ivory")
        self.assertEqual(normalized(board.toolbar.search_entry.cget("border_color")), "tomato")
        self.assertEqual(normalized(board.toolbar.search_entry.cget("text_color")), "navy")
        self.assertEqual(normalized(board.toolbar.add_button.cget("fg_color")), "#123456")
        self.assertEqual(normalized(board.toolbar.add_button.cget("text_color")), "khaki")

        menu = board._create_menu()
        self.assertEqual(str(menu.cget("background")), "black")
        self.assertEqual(str(menu.cget("foreground")), "white")
        self.assertEqual(str(menu.cget("activebackground")), "#222244")
        self.assertEqual(str(menu.cget("activeforeground")), "khaki")
        self.assertEqual(str(menu.cget("disabledforeground")), "#666666")
        menu.destroy()

    def test_form_controls_read_single_style_object(self) -> None:
        fields = [
            {"key": "title", "label": "Title", "type": "text", "required": True, "show_in_form": True},
            {"key": "details", "label": "Details", "type": "textarea", "show_in_form": True},
            {
                "key": "state",
                "label": "State",
                "type": "select",
                "options": ["Todo", "Done"],
                "show_in_form": True,
            },
            {"key": "flag", "label": "Flag", "type": "checkbox", "show_in_form": True},
        ]
        board = CTkKanbanBoard(
            self.app,
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[],
            fields=fields,
            card_form_mode="sidepanel",
            show_toolbar=False,
            style={
                "panel_fg_color": "beige",
                "panel_border_color": "brown",
                "input_fg_color": "mintcream",
                "input_border_color": "darkgreen",
                "input_text_color": "purple",
                "textbox_fg_color": "lavender",
                "textbox_text_color": "navy",
                "optionmenu_fg_color": "#112233",
                "checkbox_fg_color": "#445566",
                "button_fg_color": "#123456",
                "secondary_button_fg_color": "#654321",
            },
        )
        board.pack(fill="both", expand=True)
        board.open_add_card_form("todo")
        self.app.update_idletasks()

        panel = board._card_form_panel
        self.assertIsNotNone(panel)
        self.assertEqual(normalized(panel.cget("fg_color")), "beige")
        self.assertEqual(normalized(panel.cget("border_color")), "brown")
        self.assertEqual(normalized(panel.controls["title"].cget("fg_color")), "mintcream")
        self.assertEqual(normalized(panel.controls["title"].cget("border_color")), "darkgreen")
        self.assertEqual(normalized(panel.controls["title"].cget("text_color")), "purple")
        self.assertEqual(normalized(panel.controls["details"].cget("fg_color")), "lavender")
        self.assertEqual(normalized(panel.controls["details"].cget("text_color")), "navy")
        self.assertEqual(normalized(panel.controls["state"].cget("fg_color")), "#112233")
        self.assertEqual(normalized(panel.controls["flag"].cget("fg_color")), "#445566")
        self.assertEqual(normalized(panel.save_button.cget("fg_color")), "#123456")
        self.assertEqual(normalized(panel.cancel_button.cget("fg_color")), "#654321")


if __name__ == "__main__":
    unittest.main()
