"""Regression checks for incremental card movement and drag geometry caches."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from ctk_kanban import CTkKanbanBoard
from gui_test_app import TEST_APP


class DragOptimizationTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.board = CTkKanbanBoard(
            self.app,
            columns=[
                {"id": "todo", "title": "To Do"},
                {"id": "doing", "title": "Doing"},
            ],
            cards=[
                {"id": 1, "column": "todo", "title": "One", "sort_order": 1},
                {"id": 2, "column": "todo", "title": "Two", "sort_order": 2},
                {"id": 3, "column": "doing", "title": "Three", "sort_order": 1},
            ],
            show_toolbar=False,
            column_height=400,
        )
        self.board.pack(fill="both", expand=True)
        self.app.update_idletasks()

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()

    def test_cross_column_move_recreates_only_moved_widget(self) -> None:
        original_widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("move_card performed a full refresh")  # type: ignore[method-assign]

        self.assertTrue(self.board.move_card(1, "doing", 0, source="test"))
        self.app.update_idletasks()

        self.assertIsNot(self.board._card_widgets[1], original_widgets[1])
        self.assertIs(self.board._card_widgets[2], original_widgets[2])
        self.assertIs(self.board._card_widgets[3], original_widgets[3])
        self.assertEqual(self.board.get_card(1)["column"], "doing")

    def test_same_column_reorder_reuses_every_widget(self) -> None:
        original_widgets = dict(self.board._card_widgets)
        self.board.refresh = lambda: self.fail("reorder_card performed a full refresh")  # type: ignore[method-assign]

        self.assertTrue(self.board.reorder_card(2, 0, source="test"))
        self.app.update_idletasks()

        for card_id, widget in original_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)
        self.assertEqual([card["id"] for card in self.board.get_cards_by_column("todo")], [2, 1])

    def test_cancelled_move_does_not_redraw_or_mutate(self) -> None:
        original_widgets = dict(self.board._card_widgets)
        self.board._callbacks["on_card_moved"] = lambda _event: {"cancel": True, "reason": "test"}
        self.board.refresh = lambda: self.fail("cancelled move performed a full refresh")  # type: ignore[method-assign]

        self.assertFalse(self.board.move_card(1, "doing", source="test"))

        self.assertEqual(self.board.get_card(1)["column"], "todo")
        for card_id, widget in original_widgets.items():
            self.assertIs(self.board._card_widgets[card_id], widget)

    def test_column_filter_updates_only_moved_card_visibility(self) -> None:
        self.board.apply_filters({"column": "doing"})
        self.assertEqual(set(self.board._card_widgets), {3})
        doing_widget = self.board._card_widgets[3]
        self.board.refresh = lambda: self.fail("filtered move performed a full refresh")  # type: ignore[method-assign]

        self.assertTrue(self.board.move_card(1, "doing", source="test"))

        self.assertEqual(set(self.board._card_widgets), {1, 3})
        self.assertIs(self.board._card_widgets[3], doing_widget)

    def test_cached_card_lookup_matches_uncached_lookup(self) -> None:
        column = self.board._column_widgets["todo"]
        sample_y = column.card_widgets[1].winfo_rooty()
        uncached = column.card_index_at(sample_y, excluding_id=1)
        column.prepare_drag_geometry(excluding_id=1)
        cached = column.card_index_at(sample_y, excluding_id=1)

        self.assertEqual(cached, uncached)

    def test_raw_motion_events_are_coalesced(self) -> None:
        card = self.board._card_widgets[1]
        self.board.enable_drag_preview = False
        self.board.drag_update_interval_ms = 100
        processed = 0
        original = self.board._process_card_drag_update

        def counted(card_id: object, root_x: int, root_y: int) -> None:
            nonlocal processed
            processed += 1
            original(card_id, root_x, root_y)

        self.board._process_card_drag_update = counted  # type: ignore[method-assign]
        x = card.winfo_rootx() + 10
        y = card.winfo_rooty() + 10
        self.board._on_card_press(card, SimpleNamespace(x_root=x, y_root=y))
        for offset in range(50):
            self.board._on_card_motion(
                card,
                SimpleNamespace(x_root=x + 10 + offset % 2, y_root=y + offset % 3),
            )

        self.assertEqual(processed, 1)
        self.assertIsNotNone(self.board._drag_state["motion_after_id"])
        self.board._on_card_release(card, SimpleNamespace(x_root=x + 11, y_root=y + 1))
        self.assertEqual(processed, 2)


if __name__ == "__main__":
    unittest.main()
