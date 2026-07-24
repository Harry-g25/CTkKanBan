"""Coverage for the database-agnostic CRUD callback bridge."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Iterator

from ctk_kanban import (
    CardQuery,
    CRUDContext,
    CRUDKanbanDataSource,
    EventMetadata,
    KanbanDataSource,
    MutationEvent,
    MutationResult,
)


class MemoryCRUD:
    def __init__(self) -> None:
        self.columns = [
            {"id": "todo", "title": "To Do"},
            {"id": "done", "title": "Done"},
        ]
        self.cards = [
            {"id": 1, "column": "todo", "title": "Alpha", "sort_order": 1},
            {"id": 2, "column": "done", "title": "Bravo", "sort_order": 2},
        ]
        self.revision = 0
        self.calls: list[tuple[str, str, Any]] = []
        self.transaction_tokens: list[object] = []

    def read(self, _board_id: str) -> dict[str, Any]:
        return {
            "columns": deepcopy(self.columns),
            "cards": deepcopy(self.cards),
            "revision": self.revision,
        }

    def create(
        self,
        resource: str,
        _board_id: str,
        record: dict[str, Any],
        context: CRUDContext,
    ) -> dict[str, Any]:
        self.calls.append(("create", resource, context))
        canonical = deepcopy(record)
        if resource == "card" and str(record["id"]).startswith("__tmp__:"):
            canonical["id"] = 100
        target = self.cards if resource == "card" else self.columns
        if resource == "column" and context.position is not None:
            target.insert(context.position, canonical)
        else:
            target.append(canonical)
        self.revision += 1
        return canonical

    def update(
        self,
        resource: str,
        _board_id: str,
        old_id: Any,
        record: dict[str, Any],
        context: CRUDContext,
    ) -> dict[str, Any] | bool:
        self.calls.append(("update", resource, context))
        target = self.cards if resource == "card" else self.columns
        index = next(
            (position for position, item in enumerate(target) if item["id"] == old_id),
            None,
        )
        if index is None:
            return False
        target.pop(index)
        position = context.position if context.position is not None else index
        target.insert(position, deepcopy(record))
        self.revision += 1
        return record

    def delete(
        self,
        resource: str,
        _board_id: str,
        record_id: Any,
        context: CRUDContext,
    ) -> bool | None:
        self.calls.append(("delete", resource, context))
        target = self.cards if resource == "card" else self.columns
        index = next(
            (position for position, item in enumerate(target) if item["id"] == record_id),
            None,
        )
        if index is None:
            return False
        target.pop(index)
        self.revision += 1
        return None

    @contextmanager
    def transaction(self, _events: list[MutationEvent]) -> Iterator[object]:
        columns = deepcopy(self.columns)
        cards = deepcopy(self.cards)
        revision = self.revision
        token = object()
        self.transaction_tokens.append(token)
        try:
            yield token
        except Exception:
            self.columns = columns
            self.cards = cards
            self.revision = revision
            raise


class CRUDDataSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MemoryCRUD()
        self.source = CRUDKanbanDataSource(
            read=self.backend.read,
            create=self.backend.create,
            update=self.backend.update,
            delete=self.backend.delete,
            transaction=self.backend.transaction,
        )

    @staticmethod
    def event(event_type: str, **payload: Any) -> MutationEvent:
        return MutationEvent(
            event_type,
            payload,
            EventMetadata(board_id="work", actor_id="test-user"),
        )

    def test_bridge_satisfies_the_full_data_source_protocol(self) -> None:
        self.assertIsInstance(self.source, KanbanDataSource)

    def test_load_and_query_are_implemented_from_one_read_callback(self) -> None:
        loaded = self.source.load_board("work", CardQuery(search="bravo", limit=10))
        page = self.source.query_cards(
            "work",
            CardQuery(column_id="todo", filters={"title": {"op": "contains", "value": "ph"}}),
        )

        self.assertEqual([card["id"] for card in loaded.cards], [2])
        self.assertEqual(loaded.column_totals, {"todo": 1, "done": 1})
        self.assertEqual([card["id"] for card in page.cards], [1])

    def test_create_returns_canonical_id_and_callback_context(self) -> None:
        event = self.event(
            "card_created",
            card_data={
                "id": "__tmp__:1",
                "column": "todo",
                "title": "Created",
                "sort_order": 3,
            },
            temporary_id=True,
        )

        result = self.source.apply_mutation(event)

        self.assertTrue(result.accepted)
        self.assertEqual(result.card["id"], 100)
        self.assertEqual(result.id_map, {"__tmp__:1": 100})
        context = self.backend.calls[-1][2]
        self.assertIsInstance(context, CRUDContext)
        self.assertEqual(context.metadata.actor_id, "test-user")
        self.assertIs(context.transaction, self.backend.transaction_tokens[-1])

    def test_moves_and_deletes_dispatch_to_ordinary_crud_callbacks(self) -> None:
        moved = {**self.backend.cards[0], "column": "done", "sort_order": 5}
        move_result = self.source.apply_mutation(
            self.event(
                "card_moved",
                card_id=1,
                card_data=moved,
                changed_cards=[moved],
            )
        )
        delete_result = self.source.apply_mutation(
            self.event("card_deleted", card_id=2)
        )

        self.assertTrue(move_result.accepted)
        self.assertEqual(move_result.card["column"], "done")
        self.assertTrue(delete_result.accepted)
        self.assertEqual([card["id"] for card in self.backend.cards], [1])
        self.assertEqual(
            [(operation, resource) for operation, resource, _context in self.backend.calls],
            [("update", "card"), ("delete", "card")],
        )

    def test_delete_callback_may_return_deleted_database_row(self) -> None:
        source = CRUDKanbanDataSource(
            read=self.backend.read,
            create=self.backend.create,
            update=self.backend.update,
            delete=lambda _resource, _board_id, record_id, _context: {"id": record_id},
        )

        result = source.apply_mutation(self.event("card_deleted", card_id=1))

        self.assertTrue(result.accepted)
        self.assertIsNone(result.card)

    def test_column_rename_updates_affected_card_records(self) -> None:
        renamed = {"id": "ready", "title": "Ready"}
        affected = [{**self.backend.cards[0], "column": "ready"}]

        result = self.source.apply_mutation(
            self.event(
                "column_updated",
                old_column_id="todo",
                column_data=renamed,
                affected_cards=affected,
            )
        )

        self.assertTrue(result.accepted)
        self.assertEqual(self.backend.columns[0]["id"], "ready")
        self.assertEqual(self.backend.cards[0]["column"], "ready")
        self.assertEqual(result.changed_cards[0]["id"], 1)

    def test_column_order_is_exposed_as_context_position(self) -> None:
        reordered = [self.backend.columns[1], self.backend.columns[0]]

        result = self.source.apply_mutation(
            self.event(
                "column_reordered",
                column_id="done",
                columns=reordered,
            )
        )

        self.assertTrue(result.accepted)
        self.assertEqual([column["id"] for column in self.backend.columns], ["done", "todo"])
        positions = [
            context.position
            for operation, resource, context in self.backend.calls
            if operation == "update" and resource == "column"
        ]
        self.assertEqual(positions, [0, 1])

    def test_batch_rebases_a_generated_card_id_for_later_updates(self) -> None:
        created = {
            "id": "__tmp__:batch",
            "column": "todo",
            "title": "Initial",
            "sort_order": 4,
        }
        updated = {**created, "title": "Updated"}

        result = self.source.apply_batch(
            [
                self.event(
                    "card_created",
                    card_data=created,
                    temporary_id=True,
                ),
                self.event(
                    "card_updated",
                    old_card_id="__tmp__:batch",
                    card_data=updated,
                ),
            ]
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.id_map, {"__tmp__:batch": 100})
        self.assertEqual(self.backend.cards[-1]["id"], 100)
        self.assertEqual(self.backend.cards[-1]["title"], "Updated")
        self.assertEqual(result.changed_cards[-1]["title"], "Updated")

    def test_rejected_batch_rolls_back_through_transaction_callback(self) -> None:
        result = self.source.apply_batch(
            [
                self.event(
                    "card_created",
                    card_data={
                        "id": 3,
                        "column": "todo",
                        "title": "Rollback",
                    },
                ),
                self.event("card_deleted", card_id="missing"),
            ]
        )

        self.assertFalse(result.accepted)
        self.assertEqual([card["id"] for card in self.backend.cards], [1, 2])
        self.assertEqual(self.backend.revision, 0)

    def test_batch_rebases_expected_revision_after_each_write(self) -> None:
        expected_revisions: list[int | str | None] = []

        def create(
            _resource: str,
            _board_id: str,
            record: dict[str, Any],
            context: CRUDContext,
        ) -> MutationResult:
            expected_revisions.append(context.metadata.expected_revision)
            return MutationResult(card=record, board_revision=6)

        def update(
            _resource: str,
            _board_id: str,
            _record_id: Any,
            record: dict[str, Any],
            context: CRUDContext,
        ) -> MutationResult:
            expected_revisions.append(context.metadata.expected_revision)
            return MutationResult(card=record, board_revision=7)

        source = CRUDKanbanDataSource(
            read=self.backend.read,
            create=create,
            update=update,
            delete=self.backend.delete,
        )
        metadata = EventMetadata(board_id="work", expected_revision=5)

        result = source.apply_batch(
            [
                MutationEvent(
                    "card_created",
                    {
                        "card_data": {
                            "id": 3,
                            "column": "todo",
                            "title": "Created",
                        }
                    },
                    deepcopy(metadata),
                ),
                MutationEvent(
                    "card_updated",
                    {
                        "old_card_id": 3,
                        "card_data": {
                            "id": 3,
                            "column": "todo",
                            "title": "Updated",
                        },
                    },
                    deepcopy(metadata),
                ),
            ]
        )

        self.assertTrue(result.accepted)
        self.assertEqual(expected_revisions, [5, 6])
        self.assertEqual(result.board_revision, 7)

    def test_revision_polling_works_without_a_custom_changes_callback(self) -> None:
        unchanged = self.source.get_changes("work", 0)
        self.backend.revision = 2
        changed = self.source.get_changes("work", 0)

        self.assertEqual(unchanged.events, [])
        self.assertEqual([event.type for event in changed.events], ["board_changed"])
        self.assertEqual(changed.board_revision, 2)


if __name__ == "__main__":
    unittest.main()
