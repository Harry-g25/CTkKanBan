"""Integration coverage for threaded, transactional SQLite persistence."""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gui_test_app import TEST_APP

from ctk_kanban import (
    CardQuery,
    CTkKanbanBoard,
    EventMetadata,
    MutationEvent,
    SQLiteKanbanDataSource,
)


class SQLiteDataSourceTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source = SQLiteKanbanDataSource(Path(self.temp_dir.name) / "kanban.db")
        self.source.seed_board(
            "test-board",
            [{"id": "todo", "title": "To Do"}, {"id": "done", "title": "Done"}],
            [{"id": "existing", "column": "todo", "title": "Existing", "sort_order": 1024}],
            replace=True,
        )
        self.board = CTkKanbanBoard(
            self.app,
            data_source=self.source,
            board_id="test-board",
            auto_load=True,
            show_toolbar=True,
            column_height=360,
        )
        self.board.pack(fill="both", expand=True)
        self._wait_until(lambda: self.board.get_column("todo") is not None)

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()
        self.temp_dir.cleanup()

    def _wait_until(self, predicate: object, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():  # type: ignore[operator]
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous board work")

    def test_create_uses_temporary_then_canonical_database_id(self) -> None:
        created = self.board.add_card({"column": "todo", "title": "Persist me"}, source="test")
        self.assertTrue(str(created["id"]).startswith("__tmp__:"))

        self._wait_until(lambda: self.board.get_persistence_status()["state"] == "saved")
        cards = self.board.get_all_cards()
        canonical = next(card for card in cards if card["title"] == "Persist me")
        self.assertFalse(str(canonical["id"]).startswith("__tmp__:"))
        self.assertIn("created_at", canonical)
        self.assertIn("updated_at", canonical)
        self.assertEqual(canonical["version"], 1)

        loaded = self.source.load_board("test-board", CardQuery(limit=20))
        self.assertIn(canonical["id"], {card["id"] for card in loaded.cards})

    def test_stale_revision_returns_conflict_with_server_state(self) -> None:
        event = MutationEvent(
            "card_created",
            {"card_data": {"id": "stale", "column": "todo", "title": "Stale", "sort_order": 2048}},
            EventMetadata(board_id="test-board", expected_revision=99),
        )
        result = self.source.apply_mutation(event)

        self.assertFalse(result.accepted)
        self.assertIsNotNone(result.conflict)
        self.assertEqual(result.conflict.actual_revision, 0)
        self.assertEqual(len(result.conflict.server_data["cards"]), 1)

    def test_local_wins_conflict_retries_against_current_revision(self) -> None:
        self.board.conflict_strategy = "local_wins"
        remote_card = self.board.get_card("existing")
        remote_card["title"] = "Remote title"
        remote = MutationEvent(
            "card_updated",
            {"card_data": remote_card, "old_card_id": "existing"},
            EventMetadata(board_id="test-board", expected_revision=0),
        )
        self.assertTrue(self.source.apply_mutation(remote).accepted)

        self.board.update_card("existing", {"title": "Local title"}, source="test")
        self._wait_until(lambda: self.board.get_persistence_status()["state"] == "saved")

        loaded = self.source.load_board("test-board", CardQuery(limit=20))
        saved = next(card for card in loaded.cards if card["id"] == "existing")
        self.assertEqual(saved["title"], "Local title")
        self.assertEqual(self.board._board_revision, 2)

    def test_move_persists_only_the_changed_card_with_sparse_rank(self) -> None:
        self.board.move_card("existing", "done", source="test")
        self._wait_until(lambda: self.board.get_persistence_status()["state"] == "saved")

        loaded = self.source.load_board("test-board", CardQuery(limit=20))
        moved = next(card for card in loaded.cards if card["id"] == "existing")
        self.assertEqual(moved["column"], "done")
        changes = self.source.get_changes("test-board", 0)
        self.assertEqual(changes.events[-1].type, "card_moved")
        self.assertNotIn("columns", changes.events[-1].payload)

    def test_batch_edit_and_move_commit_as_one_requested_unit(self) -> None:
        self.assertTrue(
            self.board.apply_batch(
                [
                    {"operation": "update_card", "card_id": "existing", "new_data": {"title": "Updated"}},
                    {"operation": "move_card", "card_id": "existing", "target_column": "done"},
                    {"operation": "add_card", "card_data": {"column": "todo", "title": "Imported"}},
                ],
                source="test_batch",
            )
        )
        self._wait_until(lambda: self.board.get_persistence_status()["state"] == "saved")

        loaded = self.source.load_board("test-board", CardQuery(limit=20))
        existing = next(card for card in loaded.cards if card["id"] == "existing")
        self.assertEqual(existing["title"], "Updated")
        self.assertEqual(existing["column"], "done")
        self.assertIn("Imported", {card["title"] for card in loaded.cards})

    def test_polling_refreshes_changes_written_by_another_client(self) -> None:
        self.board.poll_interval_ms = 20
        self.board._schedule_poll()
        remote = MutationEvent(
            "card_created",
            {
                "card_data": {
                    "id": "remote",
                    "column": "todo",
                    "title": "Remote update",
                    "sort_order": 4096,
                }
            },
            EventMetadata(board_id="test-board", expected_revision=self.board._board_revision),
        )
        self.assertTrue(self.source.apply_mutation(remote).accepted)

        self._wait_until(lambda: self.board.get_card("remote") is not None)
        self.assertEqual(self.board.get_card("remote")["title"], "Remote update")

    def test_query_returns_page_and_full_column_totals(self) -> None:
        self.source.seed_board(
            "paged",
            [{"id": "todo", "title": "To Do"}],
            [
                {"id": index, "column": "todo", "title": f"Card {index}", "sort_order": index}
                for index in range(25)
            ],
            replace=True,
        )
        page = self.source.query_cards("paged", CardQuery(offset=10, limit=5))
        self.assertEqual(len(page.cards), 5)
        self.assertEqual(page.total, 25)
        self.assertEqual(page.column_totals["todo"], 25)
        self.assertTrue(page.has_more)

    def test_server_overdue_filter_respects_completed_columns(self) -> None:
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        self.source.seed_board(
            "overdue",
            [{"id": "todo", "title": "To Do"}, {"id": "done", "title": "Done"}],
            [
                {"id": 1, "column": "todo", "title": "Late", "due_date": yesterday},
                {"id": 2, "column": "done", "title": "Finished", "due_date": yesterday},
            ],
            replace=True,
        )
        page = self.source.query_cards(
            "overdue",
            CardQuery(filters={"overdue_only": True}, completed_columns=("done",)),
        )
        self.assertEqual([card["id"] for card in page.cards], [1])


if __name__ == "__main__":
    unittest.main()
