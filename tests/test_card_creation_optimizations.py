"""Regression checks for incremental add and duplicate rendering."""

from __future__ import annotations

import unittest

from ctk_kanban import CTkKanbanBoard
from gui_test_app import TEST_APP


class CardCreationOptimizationTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.board = CTkKanbanBoard(
            self.app,
            columns=[
                {"id": "todo", "title": "To Do"},
                {"id": "doing", "title": "Doing"},
            ],
            cards=[
                {"id": 1, "column": "todo", "title": "Bravo", "sort_order": 1},
                {"id": 2, "column": "todo", "title": "Charlie", "sort_order": 2},
                {"id": 3, "column": "doing", "title": "Delta", "sort_order": 1},
            ],
            show_toolbar=False,
            column_height=400,
        )
        self.board.pack(fill="both", expand=True)
        self.app.update_idletasks()

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()

    def test_add_creates_only_one_widget(self) -> None:
        original_widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("add_card performed a full refresh")  # type: ignore[method-assign]

        created = self.board.add_card({"id": 4, "column": "todo", "title": "Echo"}, source="test")
        self.app.update_idletasks()

        self.assertIsNotNone(created)
        self.assertEqual(set(self.board._card_widgets), {1, 2, 3, 4})
        for card_id, widget in original_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)
        self.assertEqual(created["sort_order"], 3)

    def test_add_places_card_in_current_sort_order(self) -> None:
        self.board.sort_cards("title")
        original_widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("sorted add performed a full refresh")  # type: ignore[method-assign]

        self.board.add_card({"id": 4, "column": "todo", "title": "Alpha"}, source="test")

        visible_ids = [widget.card_id for widget in self.board._column_widgets["todo"].card_widgets]
        self.assertEqual(visible_ids, [4, 1, 2])
        for card_id, widget in original_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_filtered_out_add_updates_count_without_widget(self) -> None:
        self.board.apply_filters({"column": "doing"})
        doing_widget = self.board._card_widgets[3]
        self.board.refresh = lambda: self.fail("filtered add performed a full refresh")  # type: ignore[method-assign]

        self.board.add_card({"id": 4, "column": "todo", "title": "Hidden"}, source="test")

        self.assertNotIn(4, self.board._card_widgets)
        self.assertIs(self.board._card_widgets[3], doing_widget)
        self.assertEqual(self.board._column_widgets["todo"].count_label.cget("text"), "3")

    def test_dim_filter_adds_dimmed_widget(self) -> None:
        self.board.filter_mode = "dim"
        self.board.apply_filters({"column": "doing"})
        original_widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("dimmed add performed a full refresh")  # type: ignore[method-assign]

        self.board.add_card({"id": 4, "column": "todo", "title": "Dimmed"}, source="test")

        self.assertTrue(self.board._card_widgets[4].dimmed)
        for card_id, widget in original_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_cancelled_add_does_not_render_or_refresh(self) -> None:
        original_widgets = dict(self.board._card_widgets)
        self.board._callbacks["on_card_created"] = lambda _event: {"cancel": True, "reason": "test"}
        self.board.refresh = lambda: self.fail("cancelled add performed a full refresh")  # type: ignore[method-assign]

        result = self.board.add_card({"id": 4, "column": "todo", "title": "Rejected"}, source="test")

        self.assertIsNone(result)
        self.assertIsNone(self.board.get_card(4))
        self.assertEqual(self.board._card_widgets, original_widgets)

    def test_duplicate_uses_incremental_add_path(self) -> None:
        original_widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("duplicate_card performed a full refresh")  # type: ignore[method-assign]

        duplicate = self.board.duplicate_card(1, source="test")
        self.app.update_idletasks()

        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate["id"], 4)
        self.assertEqual(duplicate["title"], "Bravo (copy)")
        self.assertIn(4, self.board._card_widgets)
        for card_id, widget in original_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_sparse_sort_orders_append_after_highest(self) -> None:
        self.board.update_card(2, {"sort_order": 20}, source="test")
        self.board.refresh = lambda: self.fail("sparse-order add performed a full refresh")  # type: ignore[method-assign]

        created = self.board.add_card({"id": 4, "column": "todo", "title": "Echo"}, source="test")

        self.assertEqual(created["sort_order"], 21)

    def test_reverse_manual_order_inserts_new_card_first(self) -> None:
        self.board.sort_cards("manual", reverse=True)
        self.board.refresh = lambda: self.fail("reverse-manual add performed a full refresh")  # type: ignore[method-assign]

        self.board.add_card({"id": 4, "column": "todo", "title": "Echo"}, source="test")

        visible_ids = [widget.card_id for widget in self.board._column_widgets["todo"].card_widgets]
        self.assertEqual(visible_ids, [4, 2, 1])


if __name__ == "__main__":
    unittest.main()
