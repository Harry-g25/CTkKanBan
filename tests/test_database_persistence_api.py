"""Regression checks for the unified database persistence API."""

from __future__ import annotations

import unittest

from gui_test_app import TEST_APP

from ctk_kanban import CTkKanbanBoard


class DatabasePersistenceApiTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.events: list[dict[str, object]] = []
        self.board = CTkKanbanBoard(
            self.app,
            columns=[
                {"id": "todo", "title": "To Do"},
                {"id": "doing", "title": "Doing"},
            ],
            cards=[
                {"id": 1, "column": "todo", "title": "Alpha", "sort_order": 1},
                {"id": 2, "column": "doing", "title": "Bravo", "sort_order": 1},
            ],
            on_data_changed=self.events.append,
            show_toolbar=False,
            column_height=400,
        )
        self.board.pack(fill="both", expand=True)
        self.app.update_idletasks()

    def tearDown(self) -> None:
        self.board.destroy()
        self.app.update_idletasks()

    def test_add_emits_single_snapshot_event(self) -> None:
        self.board.add_card({"id": 3, "column": "todo", "title": "Charlie"}, source="test")

        self.assertEqual(len(self.events), 1)
        event = self.events[0]
        self.assertEqual(event["type"], "data_changed")
        self.assertEqual(event["action_type"], "card_created")
        action_event = event["action_event"]
        self.assertIsInstance(action_event, dict)
        self.assertEqual(action_event["type"], "card_created")
        cards = event["cards"]
        self.assertIsInstance(cards, list)
        self.assertEqual({card["id"] for card in cards}, {1, 2, 3})

    def test_cancelled_data_callback_restores_move(self) -> None:
        self.board._callbacks["on_data_changed"] = lambda _event: {"cancel": True, "reason": "db unavailable"}

        moved = self.board.move_card(1, "doing", source="test")

        self.assertFalse(moved)
        self.assertEqual(self.board.get_card(1)["column"], "todo")
        self.assertEqual([card["id"] for card in self.board.get_cards_by_column("todo")], [1])
        self.assertEqual([card["id"] for card in self.board.get_cards_by_column("doing")], [2])

    def test_set_data_reloads_without_emitting_persistence(self) -> None:
        self.board.set_data(
            {
                "columns": [
                    {"id": "ready", "title": "Ready"},
                    {"id": "done", "title": "Done"},
                ],
                "cards": [
                    {"id": 10, "column": "ready", "title": "Delta", "sort_order": 1},
                ],
            }
        )

        self.assertEqual(self.events, [])
        snapshot = self.board.get_data()
        self.assertEqual([column["id"] for column in snapshot["columns"]], ["ready", "done"])
        self.assertEqual([card["id"] for card in snapshot["cards"]], [10])

    def test_legacy_persistence_callback_can_return_canonical_record(self) -> None:
        self.board._callbacks["on_data_changed"] = lambda event: {
            "card": {
                **event["action_event"]["card_data"],
                "id": 30,
                "version": 4,
                "updated_at": "2026-06-14T12:00:00+00:00",
            }
        }

        created = self.board.add_card({"id": 3, "column": "todo", "title": "Canonical"})

        self.assertEqual(created["id"], 30)
        self.assertIsNone(self.board.get_card(3))
        self.assertEqual(self.board.get_card(30)["version"], 4)


if __name__ == "__main__":
    unittest.main()
