"""Broad performance gates for database-sized board operations."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from ctk_kanban import CardQuery, SQLiteKanbanDataSource


class PerformanceRegressionTests(unittest.TestCase):
    def test_querying_five_thousand_cards_stays_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = SQLiteKanbanDataSource(Path(directory) / "large.db")
            columns = [{"id": f"column-{index}", "title": f"Column {index}"} for index in range(5)]
            cards = [
                {
                    "id": index,
                    "column": f"column-{index % 5}",
                    "title": f"Card {index}",
                    "priority": "High" if index % 3 == 0 else "Low",
                    "sort_order": index,
                }
                for index in range(5000)
            ]
            source.seed_board("large", columns, cards, replace=True)

            started = time.perf_counter()
            page = source.query_cards(
                "large",
                CardQuery(search="Card 49", filters={"priority": "High"}, limit=100),
            )
            elapsed = time.perf_counter() - started

            self.assertLess(elapsed, 2.0)
            self.assertLessEqual(len(page.cards), 100)
            self.assertEqual(sum(page.column_totals.values()), 5000)


if __name__ == "__main__":
    unittest.main()
