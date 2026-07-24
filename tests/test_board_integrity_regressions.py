"""Regressions for paged-board, batch, form, style, and sort integrity."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk
from gui_test_app import TEST_APP

from ctk_kanban import CardQuery, CTkKanbanBoard, KanbanValidationError, SQLiteKanbanDataSource
from ctk_kanban.query import sort_cards as sort_card_records
from ctk_kanban.themes import merge_style


class BoardIntegrityRegressionTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.boards: list[CTkKanbanBoard] = []

    def tearDown(self) -> None:
        for board in reversed(self.boards):
            board.destroy()
        self.app.update_idletasks()

    def make_board(self, **options: object) -> CTkKanbanBoard:
        board = CTkKanbanBoard(self.app, show_toolbar=False, column_height=360, **options)
        board.pack(fill="both", expand=True)
        self.boards.append(board)
        self.app.update_idletasks()
        return board

    def wait_until(self, predicate: object, timeout: float = 4.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():  # type: ignore[operator]
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous board work")

    def test_partial_page_undo_and_redo_persist_only_the_changed_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = SQLiteKanbanDataSource(Path(temp_dir) / "paged.db")
            source.seed_board(
                "paged",
                [{"id": "todo", "title": "To Do"}],
                [
                    {"id": index, "column": "todo", "title": f"Card {index}", "sort_order": index}
                    for index in range(15)
                ],
                replace=True,
            )
            board = self.make_board(
                data_source=source,
                board_id="paged",
                auto_load=True,
                page_size=5,
            )
            self.wait_until(lambda: len(board.get_all_cards()) == 5)

            board.add_card({"column": "todo", "title": "Undo me"})
            self.wait_until(lambda: board.can_undo())
            self.assertTrue(board.undo())
            self.wait_until(lambda: source.query_cards("paged", CardQuery(limit=50)).total == 15)
            self.wait_until(lambda: board.get_persistence_status()["state"] == "saved")
            self.assertEqual(source.load_board("paged", CardQuery(limit=50)).has_more, False)
            self.assertNotEqual(source.get_changes("paged", 0).events[-1].type, "board_replaced")

            self.assertTrue(board.redo())
            self.wait_until(lambda: source.query_cards("paged", CardQuery(limit=50)).total == 16)
            self.assertNotEqual(source.get_changes("paged", 0).events[-1].type, "board_replaced")

    def test_unloaded_cards_block_column_delete_and_wip_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = SQLiteKanbanDataSource(Path(temp_dir) / "totals.db")
            source.seed_board(
                "totals",
                [
                    {"id": "source", "title": "Source"},
                    {"id": "full", "title": "Full", "max_cards": 1},
                ],
                [
                    {"id": "visible", "column": "source", "title": "Visible", "sort_order": 1},
                    {"id": "unseen", "column": "full", "title": "Unseen", "sort_order": 2},
                ],
                replace=True,
            )
            board = self.make_board(
                data_source=source,
                board_id="totals",
                auto_load=True,
                page_size=1,
            )
            self.wait_until(lambda: board.get_card("visible") is not None)
            self.assertIsNone(board.get_card("unseen"))

            with self.assertRaisesRegex(KanbanValidationError, "still contains cards"):
                board.delete_column("full")
            with self.assertRaisesRegex(KanbanValidationError, "card limit"):
                board.move_card("visible", "full")

    def test_load_next_page_uses_loaded_column_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = SQLiteKanbanDataSource(Path(temp_dir) / "offset.db")
            source.seed_board(
                "offset",
                [{"id": "todo", "title": "To Do"}],
                [
                    {"id": index, "column": "todo", "title": str(index), "sort_order": index}
                    for index in range(12)
                ],
                replace=True,
            )
            board = self.make_board(
                data_source=source,
                board_id="offset",
                auto_load=True,
                page_size=5,
            )
            self.wait_until(lambda: len(board.get_all_cards()) == 5)
            self.assertEqual(board._loaded_offsets["todo"], 5)

            self.assertTrue(board.load_next_page("todo"))
            self.wait_until(lambda: len(board.get_all_cards()) == 10)
            self.assertEqual(board._loaded_offsets["todo"], 10)
            self.assertTrue(board.load_next_page("todo"))
            self.wait_until(lambda: len(board.get_all_cards()) == 12)
            self.assertEqual(board._loaded_offsets["todo"], 12)

    def test_rejected_operation_rolls_back_the_entire_batch(self) -> None:
        events: list[dict[str, object]] = []
        board = self.make_board(
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[{"id": 1, "column": "todo", "title": "Original"}],
            on_card_updated=lambda _event: {"cancel": True, "reason": "Rejected"},
            on_data_changed=events.append,
        )

        accepted = board.apply_batch(
            [
                {"operation": "add_card", "card_data": {"id": 2, "column": "todo", "title": "Added"}},
                {"operation": "update_card", "card_id": 1, "new_data": {"title": "Changed"}},
            ]
        )

        self.assertFalse(accepted)
        self.assertIsNone(board.get_card(2))
        self.assertEqual(board.get_card(1)["title"], "Original")
        self.assertEqual(events, [])

    def test_dirty_sidepanel_can_cancel_replacement(self) -> None:
        board = self.make_board(
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[{"id": 1, "column": "todo", "title": "Original"}],
            card_form_mode="sidepanel",
        )
        board.open_add_card_form("todo")
        first = board._card_form_panel
        first.controls["title"].insert(0, "Unsaved")

        with patch("ctk_kanban.dialogs.messagebox.askyesno", return_value=False) as confirm:
            board.open_edit_card_form(1)
        confirm.assert_called_once()
        self.assertIs(board._card_form_panel, first)

        with patch("ctk_kanban.dialogs.messagebox.askyesno", return_value=True):
            board.open_edit_card_form(1)
        self.assertIsNot(board._card_form_panel, first)
        self.assertEqual(board._card_form_panel.controls["title"].get(), "Original")

    def test_tk_font_style_snapshot_round_trips(self) -> None:
        button_font = ctk.CTkFont(size=15, weight="bold")
        merged = merge_style({"button_font": button_font, "custom": {"values": [1, 2]}})
        self.assertIs(merged["button_font"], button_font)

        board = self.make_board(
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[],
            style=merged,
        )
        snapshot = board.get_style()
        self.assertIs(snapshot["button_font"], button_font)
        second = self.make_board(
            columns=[{"id": "todo", "title": "To Do"}],
            cards=[],
            style=snapshot,
        )
        self.assertIs(second.get_style()["button_font"], button_font)

    def test_timestamp_sort_aliases_use_canonical_fields(self) -> None:
        cards = [
            {"id": 1, "column": "todo", "title": "Later", "created_at": "2026-02-01"},
            {"id": 2, "column": "todo", "title": "Earlier", "created_at": "2026-01-01"},
        ]
        board = self.make_board(columns=[{"id": "todo", "title": "To Do"}], cards=cards)

        self.assertTrue(board.sort_cards("created_date"))
        self.assertEqual(board._global_sort, ("created_at", False))
        self.assertEqual([card["id"] for card in board.get_cards_by_column("todo")], [2, 1])
        self.assertEqual(
            [card["id"] for card in sort_card_records(cards, "created_date")],
            [2, 1],
        )


if __name__ == "__main__":
    unittest.main()
