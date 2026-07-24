"""Regression coverage for durable mutation and offline replay guarantees."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from typing import Callable

from ctk_kanban import (
    CardQuery,
    EventMetadata,
    MutationEvent,
    SQLiteKanbanDataSource,
)
from ctk_kanban.contracts import ConflictDetails, MutationResult
from ctk_kanban.datasource import PersistenceCoordinator, RetryPolicy
from ctk_kanban.exceptions import KanbanValidationError
from ctk_kanban.query import sort_cards


class _FailFirstMutation:
    def __init__(self, source: SQLiteKanbanDataSource) -> None:
        self.source = source
        self.failed = False

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        if not self.failed:
            self.failed = True
            raise ConnectionError("offline for test")
        return self.source.apply_mutation(event)

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        return self.source.apply_batch(events)

    def load_board(self, board_id: str, query: CardQuery | None = None):
        return self.source.load_board(board_id, query)

    def query_cards(self, board_id: str, query: CardQuery):
        return self.source.query_cards(board_id, query)

    def get_changes(self, board_id: str, since_revision: int | str | None):
        return self.source.get_changes(board_id, since_revision)


class _RejectFirstQueuedMutation:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | str | None]] = []
        self.rejected = False

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        name = str(event.payload["name"])
        self.calls.append((name, event.metadata.expected_revision))
        if name == "a" and not self.rejected:
            self.rejected = True
            return MutationResult(accepted=False, reason="stale queued write")
        return MutationResult(board_revision=len(self.calls))

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        result = MutationResult()
        for event in events:
            result = self.apply_mutation(event)
            if not result.accepted:
                return result
        return result

    def load_board(self, board_id: str, query: CardQuery | None = None):
        raise NotImplementedError

    def query_cards(self, board_id: str, query: CardQuery):
        raise NotImplementedError

    def get_changes(self, board_id: str, since_revision: int | str | None):
        raise NotImplementedError


class _ConflictAfterTemporaryCreate:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, int | str | None]] = []
        self.conflicted = False

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        card_data = event.payload["card_data"]
        identifier = card_data["id"]
        self.calls.append((event.type, identifier, event.metadata.expected_revision))
        if event.type == "card_created":
            canonical = dict(card_data)
            canonical["id"] = "canonical-id"
            return MutationResult(
                card=canonical,
                id_map={identifier: "canonical-id"},
                board_revision=1,
            )
        if not self.conflicted:
            self.conflicted = True
            return MutationResult(
                accepted=False,
                reason="Revision conflict",
                conflict=ConflictDetails(
                    event.metadata.expected_revision,
                    7,
                    {"columns": [], "cards": []},
                ),
                board_revision=7,
            )
        return MutationResult(card=dict(card_data), board_revision=8)

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        raise NotImplementedError

    def load_board(self, board_id: str, query: CardQuery | None = None):
        raise NotImplementedError

    def query_cards(self, board_id: str, query: CardQuery):
        raise NotImplementedError

    def get_changes(self, board_id: str, since_revision: int | str | None):
        raise NotImplementedError


class PersistenceCorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "kanban.db"
        self.source = SQLiteKanbanDataSource(self.path)
        self.source.seed_board(
            "board",
            [{"id": "todo", "title": "To Do"}, {"id": "done", "title": "Done"}],
            [{"id": "existing", "column": "todo", "title": "Existing", "sort_order": 1}],
            replace=True,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _event(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        expected_revision: int = 0,
        event_id: str | None = None,
    ) -> MutationEvent:
        metadata_options: dict[str, object] = {
            "board_id": "board",
            "expected_revision": expected_revision,
        }
        if event_id is not None:
            metadata_options["event_id"] = event_id
        return MutationEvent(event_type, payload, EventMetadata(**metadata_options))

    @staticmethod
    def _wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("Timed out waiting for persistence work")

    def test_event_replay_returns_original_canonical_result_without_a_second_write(self) -> None:
        event = self._event(
            "card_created",
            {
                "card_data": {
                    "id": "__tmp__:one",
                    "column": "todo",
                    "title": "Created once",
                    "sort_order": 2,
                },
                "temporary_id": True,
            },
            event_id="stable-event-id",
        )

        first = self.source.apply_mutation(event)
        later = self._event(
            "column_created",
            {"column_data": {"id": "later", "title": "Later"}, "index": 2},
            expected_revision=1,
        )

        self.assertTrue(self.source.apply_mutation(later).accepted)
        replay = self.source.apply_mutation(event)

        self.assertTrue(first.accepted)
        self.assertTrue(replay.accepted)
        self.assertEqual(replay.card, first.card)
        self.assertEqual(replay.id_map, first.id_map)
        self.assertEqual(replay.board_revision, 2)
        loaded = self.source.load_board("board", CardQuery(limit=20))
        self.assertEqual(loaded.board_revision, 2)
        self.assertEqual(sum(card["title"] == "Created once" for card in loaded.cards), 1)

    def test_reusing_an_event_id_for_different_payload_is_rejected(self) -> None:
        first = self._event(
            "card_created",
            {"card_data": {"id": "one", "column": "todo", "title": "One"}},
            event_id="collision",
        )
        second = self._event(
            "card_created",
            {"card_data": {"id": "two", "column": "todo", "title": "Two"}},
            event_id="collision",
            expected_revision=1,
        )

        self.assertTrue(self.source.apply_mutation(first).accepted)
        result = self.source.apply_mutation(second)

        self.assertFalse(result.accepted)
        self.assertIn("already used", result.reason or "")
        loaded = self.source.load_board("board", CardQuery(limit=20))
        self.assertNotIn("two", {card["id"] for card in loaded.cards})
        self.assertEqual(loaded.board_revision, 1)

    def test_missing_rows_and_unknown_relations_do_not_advance_revision(self) -> None:
        missing_delete = self._event("card_deleted", {"card_id": "missing"})
        missing_move = self._event(
            "card_moved",
            {
                "card_id": "missing",
                "card_data": {
                    "id": "missing",
                    "column": "done",
                    "title": "Missing",
                    "sort_order": 1,
                },
            },
        )
        unknown_column = self._event(
            "card_created",
            {"card_data": {"id": "orphan", "column": "unknown", "title": "Orphan"}},
        )
        nonempty_column = self._event("column_deleted", {"column_id": "todo"})

        for event in (missing_delete, missing_move, unknown_column, nonempty_column):
            result = self.source.apply_mutation(event)
            self.assertFalse(result.accepted, event.type)
            self.assertEqual(result.board_revision, 0)

        loaded = self.source.load_board("board", CardQuery(limit=20))
        self.assertEqual(loaded.board_revision, 0)
        self.assertEqual([card["id"] for card in loaded.cards], ["existing"])
        self.assertEqual([column["id"] for column in loaded.columns], ["todo", "done"])

    def test_failed_batch_rolls_back_and_never_mutates_caller_events(self) -> None:
        create = self._event(
            "card_created",
            {"card_data": {"id": "new", "column": "todo", "title": "New"}},
        )
        missing_delete = self._event(
            "card_deleted", {"card_id": "missing"}, expected_revision=42
        )

        result = self.source.apply_batch([create, missing_delete])

        self.assertFalse(result.accepted)
        self.assertEqual(create.metadata.expected_revision, 0)
        self.assertEqual(missing_delete.metadata.expected_revision, 42)
        loaded = self.source.load_board("board", CardQuery(limit=20))
        self.assertEqual(loaded.board_revision, 0)
        self.assertNotIn("new", {card["id"] for card in loaded.cards})

    def test_batch_rebases_dependent_temporary_card_operations(self) -> None:
        temporary_id = "__tmp__:batch"
        create = self._event(
            "card_created",
            {
                "card_data": {
                    "id": temporary_id,
                    "column": "todo",
                    "title": "Draft",
                    "sort_order": 2,
                },
                "temporary_id": True,
            },
        )
        update = self._event(
            "card_updated",
            {
                "old_card_id": temporary_id,
                "card_data": {
                    "id": temporary_id,
                    "column": "todo",
                    "title": "Edited",
                    "sort_order": 2,
                },
            },
        )

        result = self.source.apply_batch([create, update])

        self.assertTrue(result.accepted)
        canonical_id = result.id_map[temporary_id]
        loaded = self.source.load_board("board", CardQuery(limit=20))
        saved = next(card for card in loaded.cards if card["title"] == "Edited")
        self.assertEqual(saved["id"], canonical_id)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(len(result.changed_cards), 1)
        self.assertEqual(result.changed_cards[0]["title"], "Edited")
        self.assertNotIn(temporary_id, {card["id"] for card in loaded.cards})
        self.assertEqual(create.payload["card_data"]["id"], temporary_id)
        self.assertEqual(update.payload["card_data"]["id"], temporary_id)

    def test_offline_replay_rebases_create_then_update_without_mutating_inputs(self) -> None:
        flaky = _FailFirstMutation(self.source)
        coordinator = PersistenceCoordinator(
            flaky,
            schedule=lambda callback: callback(),
            retry_policy=RetryPolicy(attempts=1, initial_delay=0),
        )
        temporary_id = "__tmp__:offline"
        create = self._event(
            "card_created",
            {
                "card_data": {
                    "id": temporary_id,
                    "column": "todo",
                    "title": "Draft",
                    "sort_order": 2,
                },
                "temporary_id": True,
            },
        )
        update = self._event(
            "card_updated",
            {
                "old_card_id": temporary_id,
                "card_data": {
                    "id": temporary_id,
                    "column": "todo",
                    "title": "Edited offline",
                    "sort_order": 2,
                },
            },
        )
        successes: list[MutationResult] = []
        failures: list[Exception | MutationResult] = []
        completed = threading.Event()

        try:
            coordinator.submit(create, on_success=successes.append, on_failure=failures.append)
            self._wait_until(lambda: not coordinator.online and coordinator.queued_count == 1)
            coordinator.submit(
                update,
                on_success=lambda result: (successes.append(result), completed.set()),
                on_failure=failures.append,
            )

            coordinator.set_online(True)
            self.assertTrue(completed.wait(3))
            self._wait_until(lambda: coordinator.queued_count == 0)

            loaded = self.source.load_board("board", CardQuery(limit=20))
            saved = next(card for card in loaded.cards if card["title"] == "Edited offline")
            self.assertFalse(str(saved["id"]).startswith("__tmp__:"))
            self.assertEqual(saved["version"], 2)
            self.assertNotIn(temporary_id, {card["id"] for card in loaded.cards})
            self.assertEqual(create.payload["card_data"]["id"], temporary_id)
            self.assertEqual(update.payload["old_card_id"], temporary_id)
            self.assertEqual(create.metadata.expected_revision, 0)
            self.assertEqual(update.metadata.expected_revision, 0)
            self.assertEqual(len(successes), 2)
            self.assertEqual(len(failures), 1)
            self.assertIsInstance(failures[0], ConnectionError)
        finally:
            coordinator.close()

    def test_failed_offline_replay_blocks_new_work_and_same_event_resolution_runs_first(
        self,
    ) -> None:
        source = _RejectFirstQueuedMutation()
        coordinator = PersistenceCoordinator(
            source,
            schedule=lambda callback: callback(),
            retry_policy=RetryPolicy(attempts=1, initial_delay=0),
        )
        failed = threading.Event()
        completed = threading.Event()
        impostor_completed = threading.Event()

        def queued_event(name: str, *, revision: int = 0) -> MutationEvent:
            return MutationEvent(
                "test",
                {"name": name},
                EventMetadata(
                    board_id="board",
                    event_id=f"event-{name}",
                    expected_revision=revision,
                ),
            )

        try:
            coordinator.set_online(False)
            coordinator.submit(
                queued_event("a"),
                on_success=lambda _result: None,
                on_failure=lambda _error: failed.set(),
            )
            coordinator.submit(
                queued_event("b"),
                on_success=lambda _result: None,
                on_failure=lambda _error: None,
            )
            coordinator.set_online(True)
            self.assertTrue(failed.wait(3))
            self.assertEqual(source.calls, [("a", 0)])

            coordinator.submit(
                queued_event("c"),
                on_success=lambda _result: completed.set(),
                on_failure=lambda _error: None,
            )
            self.assertEqual(source.calls, [("a", 0)])
            self.assertEqual(coordinator.queued_count, 2)

            coordinator.submit(
                MutationEvent(
                    "test",
                    {"name": "impostor"},
                    EventMetadata(
                        board_id="board",
                        event_id="event-a",
                        expected_revision=9,
                    ),
                ),
                on_success=lambda _result: impostor_completed.set(),
                on_failure=lambda _error: None,
            )
            self.assertEqual(source.calls, [("a", 0)])
            self.assertEqual(coordinator.queued_count, 3)

            coordinator.submit(
                queued_event("a", revision=9),
                on_success=lambda _result: None,
                on_failure=lambda _error: None,
            )
            self.assertTrue(completed.wait(3))
            self.assertTrue(impostor_completed.wait(3))
            self._wait_until(lambda: coordinator.queued_count == 0)

            self.assertEqual(
                [name for name, _revision in source.calls],
                ["a", "a", "b", "c", "impostor"],
            )
            self.assertEqual(source.calls[1], ("a", 9))
        finally:
            coordinator.close()

    def test_local_wins_retry_matches_original_identity_then_rebases_temporary_id(self) -> None:
        source = _ConflictAfterTemporaryCreate()
        coordinator = PersistenceCoordinator(
            source,
            schedule=lambda callback: callback(),
            retry_policy=RetryPolicy(attempts=1, initial_delay=0),
        )
        temporary_id = "__tmp__:dependent"
        create = self._event(
            "card_created",
            {
                "card_data": {
                    "id": temporary_id,
                    "column": "todo",
                    "title": "Draft",
                },
                "temporary_id": True,
            },
            event_id="create-temp",
        )
        update = self._event(
            "card_updated",
            {
                "old_card_id": temporary_id,
                "card_data": {
                    "id": temporary_id,
                    "column": "todo",
                    "title": "Edited",
                },
            },
            event_id="dependent-update",
        )
        conflicted = threading.Event()
        resolved = threading.Event()

        try:
            coordinator.set_online(False)
            coordinator.submit(
                create,
                on_success=lambda _result: None,
                on_failure=lambda _error: None,
            )
            coordinator.submit(
                update,
                on_success=lambda _result: None,
                on_failure=lambda _error: conflicted.set(),
            )
            coordinator.set_online(True)
            self.assertTrue(conflicted.wait(3))

            retry = self._event(
                "card_updated",
                update.payload,
                expected_revision=7,
                event_id="dependent-update",
            )
            coordinator.submit(
                retry,
                on_success=lambda _result: resolved.set(),
                on_failure=lambda _error: None,
            )
            self.assertTrue(resolved.wait(3))

            self.assertEqual(
                source.calls,
                [
                    ("card_created", temporary_id, 0),
                    ("card_updated", "canonical-id", 1),
                    ("card_updated", "canonical-id", 7),
                ],
            )
            self.assertEqual(update.payload["card_data"]["id"], temporary_id)
        finally:
            coordinator.close()

    def test_seed_replace_resets_revision_and_event_history(self) -> None:
        event = self._event(
            "card_created",
            {"card_data": {"id": "before", "column": "todo", "title": "Before"}},
            event_id="reusable-after-reseed",
        )
        self.assertEqual(self.source.apply_mutation(event).board_revision, 1)
        self.assertEqual(len(self.source.get_changes("board", 0).events), 1)

        self.source.seed_board(
            "board",
            [{"id": "todo", "title": "To Do"}],
            [{"id": "replacement", "column": "todo", "title": "Replacement"}],
            replace=True,
        )

        loaded = self.source.load_board("board", CardQuery(limit=20))
        self.assertEqual(loaded.board_revision, 0)
        self.assertEqual(self.source.get_changes("board", 0).events, [])
        replayed_as_new = self.source.apply_mutation(event)
        self.assertTrue(replayed_as_new.accepted)
        self.assertEqual(replayed_as_new.board_revision, 1)

    def test_timestamp_sort_aliases_support_canonical_and_legacy_records(self) -> None:
        cards = [
            {
                "id": "legacy",
                "created_date": "2026-01-01T00:00:00+00:00",
                "updated_date": "2026-01-03T00:00:00+00:00",
            },
            {
                "id": "canonical",
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-02T00:00:00+00:00",
            },
        ]

        self.assertEqual(
            [card["id"] for card in sort_cards(cards, "created_date")],
            ["legacy", "canonical"],
        )
        self.assertEqual(
            [card["id"] for card in sort_cards(cards, "updated_date")],
            ["canonical", "legacy"],
        )

    def test_callbacks_scheduled_before_close_are_guarded(self) -> None:
        scheduled: list[Callable[[], None]] = []
        callback_scheduled = threading.Event()

        def schedule(callback: Callable[[], None]) -> None:
            scheduled.append(callback)
            callback_scheduled.set()

        coordinator = PersistenceCoordinator(self.source, schedule=schedule)
        delivered: list[object] = []
        future = coordinator.load(
            "board",
            CardQuery(limit=20),
            on_success=delivered.append,
            on_failure=delivered.append,
        )
        future.result(timeout=3)
        self.assertTrue(callback_scheduled.wait(3))
        coordinator.close()

        for callback in scheduled:
            callback()

        self.assertEqual(delivered, [])

    def test_conflict_snapshot_contains_every_card_not_only_the_default_page(self) -> None:
        cards = [
            {"id": index, "column": "todo", "title": f"Card {index}", "sort_order": index}
            for index in range(150)
        ]
        self.source.seed_board(
            "large",
            [{"id": "todo", "title": "To Do"}],
            cards,
            replace=True,
        )
        stale = MutationEvent(
            "card_created",
            {"card_data": {"id": "stale", "column": "todo", "title": "Stale"}},
            EventMetadata(board_id="large", expected_revision=99),
        )

        result = self.source.apply_mutation(stale)

        self.assertFalse(result.accepted)
        self.assertIsNotNone(result.conflict)
        self.assertEqual(len(result.conflict.server_data["cards"]), 150)

    def test_sqlite_rejects_non_round_trippable_identifiers(self) -> None:
        with self.assertRaises(KanbanValidationError):
            self.source.seed_board(
                "unsafe",
                [{"id": ("tuple", 1), "title": "Unsafe"}],
                [],
                replace=True,
            )

        event = self._event(
            "card_created",
            {"card_data": {"id": ("tuple", 1), "column": "todo", "title": "Unsafe"}},
        )
        result = self.source.apply_mutation(event)
        self.assertFalse(result.accepted)
        self.assertIn("SQLite storage", result.reason or "")

    def test_version_one_database_is_migrated_without_overwriting_future_versions(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE kanban_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO kanban_meta(key, value) VALUES('schema_version', '1');
                CREATE TABLE kanban_events (
                    event_id TEXT PRIMARY KEY,
                    board_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

        SQLiteKanbanDataSource(legacy_path)

        with closing(sqlite3.connect(legacy_path)) as connection:
            version = connection.execute(
                "SELECT value FROM kanban_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            event_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(kanban_events)").fetchall()
            }
        self.assertEqual(version, "2")
        self.assertIn("result_data", event_columns)

        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute(
                "UPDATE kanban_meta SET value = '999' WHERE key = 'schema_version'"
            )
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, "newer than supported"):
            SQLiteKanbanDataSource(legacy_path)
        with closing(sqlite3.connect(legacy_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM kanban_meta WHERE key = 'schema_version'"
                ).fetchone()[0],
                "999",
            )


if __name__ == "__main__":
    unittest.main()
