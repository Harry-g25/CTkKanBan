"""Regression checks for popup and embedded card form modes."""

from __future__ import annotations

import unittest

import customtkinter as ctk
from gui_test_app import TEST_APP

from ctk_kanban import CTkKanbanBoard
from ctk_kanban.dialogs import CardFormDialog, CardFormFrame


def descendants(widget: object) -> list[object]:
    result: list[object] = []
    for child in widget.winfo_children():  # type: ignore[attr-defined]
        result.append(child)
        result.extend(descendants(child))
    return result


class CardFormModeTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.board = CTkKanbanBoard(
            self.app,
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[{"id": 1, "column": "todo", "title": "Original"}],
            card_form_mode="sidepanel",
            show_toolbar=False,
            column_height=400,
        )
        self.board.pack(fill="both", expand=True)
        self.app.update_idletasks()

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()

    def test_sidepanel_add_creates_card_without_toplevel(self) -> None:
        existing_toplevels = {
            widget for widget in descendants(self.app) if isinstance(widget, ctk.CTkToplevel)
        }

        self.board.open_add_card_form("todo")
        self.app.update_idletasks()

        panel = self.board._card_form_panel
        self.assertIsInstance(panel, CardFormFrame)
        current_toplevels = {
            widget for widget in descendants(self.app) if isinstance(widget, ctk.CTkToplevel)
        }
        self.assertEqual(current_toplevels, existing_toplevels)

        title = panel.controls["title"]
        title.delete(0, "end")
        title.insert(0, "Embedded card")
        panel._submit()

        self.assertIsNone(self.board._card_form_panel)
        self.assertEqual(self.board.get_card(2)["title"], "Embedded card")

    def test_sidepanel_edit_updates_card_and_closes(self) -> None:
        self.board.open_edit_card_form(1)
        panel = self.board._card_form_panel
        self.assertIsNotNone(panel)

        title = panel.controls["title"]
        title.delete(0, "end")
        title.insert(0, "Updated")
        panel._submit()

        self.assertEqual(self.board.get_card(1)["title"], "Updated")
        self.assertIsNone(self.board._card_form_panel)

    def test_cancelled_save_keeps_sidepanel_open(self) -> None:
        self.board._callbacks["on_card_created"] = lambda _event: {"cancel": True}
        self.board.open_add_card_form("todo")
        panel = self.board._card_form_panel
        self.assertIsNotNone(panel)

        panel.controls["title"].insert(0, "Rejected")
        panel._submit()

        self.assertIs(self.board._card_form_panel, panel)
        self.assertEqual(panel.error_label.cget("text"), "The action was cancelled")
        self.assertIsNone(self.board.get_card(2))

    def test_opening_another_sidepanel_replaces_the_previous_form(self) -> None:
        self.board.open_add_card_form("todo")
        first = self.board._card_form_panel

        self.board.open_edit_card_form(1)

        self.assertIsNot(self.board._card_form_panel, first)
        self.assertEqual(self.board._card_form_panel.controls["title"].get(), "Original")

    def test_popup_mode_still_uses_dialog_wrapper(self) -> None:
        self.board.card_form_mode = "popup"
        self.board.open_add_card_form("todo")
        self.app.update_idletasks()

        dialogs = [
            widget for widget in descendants(self.app) if isinstance(widget, CardFormDialog)
        ]
        self.assertEqual(len(dialogs), 1)
        self.assertIsInstance(dialogs[0].form_frame, CardFormFrame)
        self.assertIsNone(self.board._card_form_panel)
        dialogs[0]._close()


if __name__ == "__main__":
    unittest.main()
