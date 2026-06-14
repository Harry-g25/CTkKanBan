"""Smoke-test an installed package without importing from the checkout."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path = [entry for entry in sys.path if entry and Path(entry).resolve() != ROOT]


def main() -> None:
    import ctk_kanban
    from ctk_kanban import CardQuery, SQLiteKanbanDataSource

    package_path = Path(ctk_kanban.__file__).resolve()
    if Path.cwd().resolve() in package_path.parents:
        raise RuntimeError(f"Smoke test imported the source checkout: {package_path}")
    with tempfile.TemporaryDirectory() as directory:
        source = SQLiteKanbanDataSource(Path(directory) / "smoke.db")
        source.seed_board(
            "smoke",
            [{"id": "todo", "title": "To Do"}],
            [{"id": 1, "column": "todo", "title": "Installed wheel", "sort_order": 1024}],
        )
        loaded = source.load_board("smoke")
        page = source.query_cards("smoke", CardQuery(search="wheel"))
        assert loaded.cards[0]["id"] == 1
        assert page.total == 1
    print(f"Smoke-tested ctk-kanban {ctk_kanban.__version__} from {package_path}")


if __name__ == "__main__":
    main()
