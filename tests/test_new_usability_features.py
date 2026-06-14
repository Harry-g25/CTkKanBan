"""Behavior checks for the v0.2 usability and data-integrity features."""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import timedelta, timezone
from pathlib import Path

from gui_test_app import TEST_APP

from ctk_kanban import (
    CTkKanbanBoard,
    KanbanPersistenceError,
    KanbanValidationError,
    RetryPolicy,
    SQLiteKanbanDataSource,
)
from ctk_kanban.dialogs import CardFormFrame
from ctk_kanban.utils import format_temporal
from ctk_kanban.widgets import DateEntry


class FlakySQLiteSource(SQLiteKanbanDataSource):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.fail_writes = True

    def apply_mutation(self, event: object):  # type: ignore[override]
        if self.fail_writes:
            raise ConnectionError("database unavailable")
        return super().apply_mutation(event)  # type: ignore[arg-type]


class SlowSQLiteSource(SQLiteKanbanDataSource):
    def apply_mutation(self, event: object):  # type: ignore[override]
        time.sleep(0.2)
        return super().apply_mutation(event)  # type: ignore[arg-type]


class NewUsabilityFeatureTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.board = CTkKanbanBoard(
            self.app,
            columns=[
                {"id": "todo", "title": "To Do", "max_cards": 2},
                {"id": "done", "title": "Done", "locked": True},
            ],
            cards=[{"id": 1, "column": "todo", "title": "One", "sort_order": 1024}],
            fields=[
                {"key": "title", "label": "Title", "required": True},
                {"key": "due_date", "label": "Due date", "type": "date", "filterable": True},
                {"key": "active", "label": "Active account", "type": "checkbox", "checkbox_text": "Account is active"},
                {"key": "estimate", "label": "Estimate", "type": "number", "filterable": True},
            ],
            completed_columns=["done"],
            show_toolbar=True,
            column_height=360,
        )
        self.board.pack(fill="both", expand=True)
        self.app.update_idletasks()

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()

    def test_ids_are_immutable_by_default(self) -> None:
        with self.assertRaises(KanbanValidationError):
            self.board.update_card(1, {"id": 2})
        with self.assertRaises(KanbanValidationError):
            self.board.update_column("todo", {"id": "ready"})

    def test_completed_column_suppresses_overdue_status(self) -> None:
        self.assertFalse(self.board._is_overdue({"column": "done", "due_date": "2000-01-01"}))
        self.assertTrue(self.board._is_overdue({"column": "todo", "due_date": "2000-01-01"}))

    def test_advanced_range_and_empty_filters(self) -> None:
        self.board.add_card({"id": 2, "column": "todo", "title": "Two", "estimate": 5})
        self.assertTrue(self.board.apply_filters({"estimate": {"op": "between", "value": [4, 8]}}))
        self.assertEqual(set(self.board._card_widgets), {2})
        self.assertTrue(self.board.apply_filters({"estimate": {"op": "empty", "value": None}}))
        self.assertEqual(set(self.board._card_widgets), {1})

    def test_undo_and_redo_restore_data(self) -> None:
        self.board.add_card({"id": 2, "column": "todo", "title": "Two"})
        self.assertTrue(self.board.can_undo())
        self.assertTrue(self.board.undo())
        self.assertIsNone(self.board.get_card(2))
        self.assertTrue(self.board.redo())
        self.assertEqual(self.board.get_card(2)["title"], "Two")

    def test_column_header_exposes_limit_lock_and_adjustable_width(self) -> None:
        todo = self.board._column_widgets["todo"]
        done = self.board._column_widgets["done"]
        self.assertEqual(todo.count_label.cget("text"), "1 / 2")
        self.assertTrue(done.lock_label.winfo_ismapped())
        self.board.set_column_width(240, "todo")
        self.assertEqual(todo.cget("width"), 240)

    def test_form_uses_date_picker_and_meaningful_checkbox_text(self) -> None:
        frame = CardFormFrame(
            self.app,
            self.board.fields,
            self.board.theme,
            title="Test",
            on_submit=lambda _data: True,
            confirm_discard=False,
        )
        try:
            self.assertIsInstance(frame.controls["due_date"], DateEntry)
            self.assertEqual(frame.controls["active"].cget("text"), "Account is active")
        finally:
            frame.destroy()

    def test_database_timestamps_have_locale_aware_display_formatting(self) -> None:
        shown = format_temporal(
            "2026-06-14T18:30:00+00:00",
            field_type="datetime",
            timezone_info=timezone(timedelta(hours=-4), "EDT"),
            locale_name="en_US",
        )
        self.assertTrue(shown.startswith("6/14/2026 02:30 PM"))
        self.assertEqual(
            format_temporal("2026-06-14", field_type="date", locale_name="en_GB"),
            "14/06/2026",
        )
        regional_board = CTkKanbanBoard(
            self.app,
            columns=[],
            timezone_name="Europe/London",
            locale_name="en_GB",
        )
        try:
            self.assertEqual(regional_board.timezone.key, "Europe/London")
        finally:
            regional_board.destroy()


class OfflineQueueTests(unittest.TestCase):
    app = TEST_APP

    def test_failed_write_remains_visible_and_flushes_on_reconnect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = FlakySQLiteSource(Path(directory) / "offline.db")
            source.seed_board("offline", [{"id": "todo", "title": "To Do"}], [], replace=True)
            board = CTkKanbanBoard(
                self.app,
                columns=[{"id": "todo", "title": "To Do"}],
                data_source=source,
                board_id="offline",
                retry_policy=RetryPolicy(attempts=1),
                show_toolbar=True,
                column_height=320,
            )
            board.pack(fill="both", expand=True)
            try:
                created = board.add_card({"column": "todo", "title": "Offline work"})
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and board.get_persistence_status()["state"] != "offline":
                    self.app.update()
                    time.sleep(0.01)
                self.assertIsNotNone(board.get_card(created["id"]))
                self.assertEqual(board.get_persistence_status()["queued_count"], 1)

                source.fail_writes = False
                board.set_online(True)
                while time.monotonic() < deadline and board.get_persistence_status()["state"] != "saved":
                    self.app.update()
                    time.sleep(0.01)
                self.assertEqual(source.load_board("offline").cards[0]["title"], "Offline work")
            finally:
                board.destroy()
                self.app.update_idletasks()

    def test_slow_write_does_not_block_tk_and_duplicate_submit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = SlowSQLiteSource(Path(directory) / "slow.db")
            source.seed_board("slow", [{"id": "todo", "title": "To Do"}], [], replace=True)
            board = CTkKanbanBoard(
                self.app,
                columns=[{"id": "todo", "title": "To Do"}],
                data_source=source,
                board_id="slow",
                show_toolbar=True,
                column_height=320,
            )
            board.pack(fill="both", expand=True)
            try:
                started = time.perf_counter()
                board.add_card({"column": "todo", "title": "First"})
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, 0.1)
                with self.assertRaises(KanbanPersistenceError):
                    board.add_card({"column": "todo", "title": "Duplicate click"})
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and board.get_persistence_status()["state"] != "saved":
                    self.app.update()
                    time.sleep(0.01)
                self.assertEqual(board.get_persistence_status()["state"], "saved")
            finally:
                board.destroy()
                self.app.update_idletasks()


if __name__ == "__main__":
    unittest.main()
