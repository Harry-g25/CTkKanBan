"""Efficiency and identity regressions across the board's public mutation API."""

from __future__ import annotations

import unittest

import customtkinter as ctk
from gui_test_app import TEST_APP

from ctk_kanban import CTkKanbanBoard


class FullEfficiencyAuditTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.board = CTkKanbanBoard(
            self.app,
            columns=[
                {"id": "todo", "title": "To Do"},
                {"id": "doing", "title": "Doing"},
            ],
            cards=[
                {"id": 1, "column": "todo", "title": "Alpha", "priority": "High", "sort_order": 1},
                {"id": 2, "column": "todo", "title": "Bravo", "priority": "Low", "sort_order": 2},
                {"id": 3, "column": "doing", "title": "Charlie", "priority": "High", "sort_order": 1},
            ],
            show_toolbar=False,
            column_height=400,
        )
        self.board.pack(fill="both", expand=True)
        self.app.update_idletasks()

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()

    def test_delete_destroys_only_deleted_card(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("delete_card performed a full refresh")  # type: ignore[method-assign]

        self.assertTrue(self.board.delete_card(1, source="test"))

        self.assertNotIn(1, self.board._card_widgets)
        self.assertIs(self.board._card_widgets[2], widgets[2])
        self.assertIs(self.board._card_widgets[3], widgets[3])
        self.assertEqual(self.board.get_card(2)["sort_order"], 2)

    def test_cancelled_delete_never_touches_widgets(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board._callbacks["on_card_deleted"] = lambda _event: {"cancel": True, "reason": "test"}
        self.board.refresh = lambda: self.fail("cancelled delete performed a refresh")  # type: ignore[method-assign]

        self.assertFalse(self.board.delete_card(1, source="test"))

        self.assertIsNotNone(self.board.get_card(1))
        self.assertEqual(self.board.get_card(2)["sort_order"], 2)
        self.assertEqual(self.board._card_widgets, widgets)

    def test_update_replaces_only_updated_card(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("update_card performed a full refresh")  # type: ignore[method-assign]

        updated = self.board.update_card(1, {"title": "Updated"}, source="test")

        self.assertEqual(updated["title"], "Updated")
        self.assertIsNot(self.board._card_widgets[1], widgets[1])
        self.assertIs(self.board._card_widgets[2], widgets[2])
        self.assertIs(self.board._card_widgets[3], widgets[3])

    def test_cancelled_update_never_touches_widgets(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board._callbacks["on_card_updated"] = lambda _event: {"cancel": True, "reason": "test"}
        self.board.refresh = lambda: self.fail("cancelled update performed a refresh")  # type: ignore[method-assign]

        self.assertIsNone(self.board.update_card(1, {"title": "Rejected"}, source="test"))

        self.assertEqual(self.board.get_card(1)["title"], "Alpha")
        self.assertEqual(self.board._card_widgets, widgets)

    def test_search_and_filter_restore_cached_widgets(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("view synchronization performed a full refresh")  # type: ignore[method-assign]

        self.board.search("Alpha")
        self.assertEqual(set(self.board._card_widgets), {1})
        self.assertEqual(set(self.board._hidden_card_widgets), {2, 3})
        self.board.clear_search()
        self.board.apply_filters({"priority": "High"})
        self.board.clear_filters()

        self.assertFalse(self.board._hidden_card_widgets)
        for card_id, widget in widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_sort_repacks_without_recreating_cards(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("sort performed a full refresh")  # type: ignore[method-assign]

        self.board.sort_cards("title", reverse=True)

        self.assertEqual([widget.card_id for widget in self.board._column_widgets["todo"].card_widgets], [2, 1])
        for card_id, widget in widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_clear_board_detaches_immediately_and_defers_cleanup(self) -> None:
        self.board.refresh = lambda: self.fail("clear_board performed a full refresh")  # type: ignore[method-assign]

        self.board.clear_board()

        self.assertFalse(self.board._cards)
        self.assertFalse(self.board._card_widgets)
        self.assertFalse(self.board._hidden_card_widgets)
        self.assertEqual(len(self.board._retired_card_widgets), 3)
        self.assertTrue(all(not column.card_widgets for column in self.board._column_widgets.values()))

    def test_set_cards_preserves_equal_widgets_and_replaces_changed_only(self) -> None:
        widgets = dict(self.board._card_widgets)
        replacement = self.board.get_all_cards()
        replacement[0]["title"] = "Changed"
        replacement = [card for card in replacement if card["id"] != 2]
        replacement.append({"id": 4, "column": "todo", "title": "Delta", "sort_order": 2})
        self.board.refresh = lambda: self.fail("set_cards performed a full refresh")  # type: ignore[method-assign]

        self.board.set_cards(replacement)

        self.assertIsNot(self.board._card_widgets[1], widgets[1])
        self.assertNotIn(2, self.board._card_widgets)
        self.assertIs(self.board._card_widgets[3], widgets[3])
        self.assertIn(4, self.board._card_widgets)

    def test_set_state_preserves_unchanged_widgets(self) -> None:
        widgets = dict(self.board._card_widgets)
        state = self.board.get_state()
        state["cards"][0]["title"] = "Changed"
        self.board.refresh = lambda: self.fail("set_state performed a full refresh")  # type: ignore[method-assign]

        self.board.set_state(state)

        self.assertIsNot(self.board._card_widgets[1], widgets[1])
        self.assertIs(self.board._card_widgets[2], widgets[2])
        self.assertIs(self.board._card_widgets[3], widgets[3])

    def test_set_columns_reorders_and_updates_in_place(self) -> None:
        card_widgets = dict(self.board._card_widgets)
        column_widgets = dict(self.board._column_widgets)
        self.board.refresh = lambda: self.fail("set_columns performed a full refresh")  # type: ignore[method-assign]

        self.board.set_columns(
            [
                {"id": "doing", "title": "In Progress"},
                {"id": "todo", "title": "Ready"},
            ]
        )

        self.assertIs(self.board._column_widgets["doing"], column_widgets["doing"])
        self.assertIs(self.board._column_widgets["todo"], column_widgets["todo"])
        self.assertEqual(self.board._column_widgets["todo"].title_label.cget("text"), "Ready")
        for card_id, widget in card_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_column_add_move_delete_preserves_all_cards(self) -> None:
        widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("structural column action performed a full refresh")  # type: ignore[method-assign]

        self.board.add_column({"id": "done", "title": "Done"}, source="test")
        self.board.move_column("done", 0, source="test")
        self.board.delete_column("done", source="test")

        self.assertEqual([column["id"] for column in self.board.get_columns()], ["todo", "doing"])
        for card_id, widget in widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_column_update_preserves_column_and_card_widgets(self) -> None:
        widgets = dict(self.board._card_widgets)
        todo_column = self.board._column_widgets["todo"]
        doing_column = self.board._column_widgets["doing"]
        self.board.refresh = lambda: self.fail("column update performed a full refresh")  # type: ignore[method-assign]

        self.board.update_column("todo", {"title": "Ready"}, source="test")

        self.assertIs(self.board._column_widgets["todo"], todo_column)
        self.assertIs(self.board._column_widgets["doing"], doing_column)
        self.assertEqual(todo_column.title_label.cget("text"), "Ready")
        for card_id, widget in widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_column_id_rename_preserves_widgets_and_updates_cards(self) -> None:
        self.board.immutable_column_ids = False
        widgets = dict(self.board._card_widgets)
        todo_column = self.board._column_widgets["todo"]
        self.board.refresh = lambda: self.fail("column rename performed a full refresh")  # type: ignore[method-assign]

        self.board.update_column("todo", {"id": "ready", "title": "Ready"}, source="test")

        self.assertNotIn("todo", self.board._column_widgets)
        self.assertIs(self.board._column_widgets["ready"], todo_column)
        self.assertEqual({self.board.get_card(1)["column"], self.board.get_card(2)["column"]}, {"ready"})
        for card_id, widget in widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_column_rename_refreshes_custom_renderer_content(self) -> None:
        def renderer(frame: object, card_data: dict[str, object], _fields: object, _theme: object) -> None:
            ctk.CTkLabel(frame, text=str(card_data["column"])).pack()

        custom_board = CTkKanbanBoard(
            self.app,
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[{"id": 10, "column": "todo", "title": "Card"}],
            card_renderer=renderer,
            immutable_column_ids=False,
            show_toolbar=False,
            column_height=300,
        )
        custom_board.pack()
        self.app.update_idletasks()
        original = custom_board._card_widgets[10]

        custom_board.update_column("todo", {"id": "ready"}, source="test")

        updated = custom_board._card_widgets[10]
        self.assertIsNot(updated, original)
        labels = [child for child in updated.winfo_children() if isinstance(child, ctk.CTkLabel)]
        self.assertEqual(labels[0].cget("text"), "ready")
        custom_board.destroy()


if __name__ == "__main__":
    unittest.main()
