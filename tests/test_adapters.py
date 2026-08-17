"""Database and row-adapter behavior."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ctk_kanban import (
    BoardModelError,
    normalize_row,
    rows_from_cursor,
    snapshot_from_cursors,
    snapshot_from_rows,
)


class Cursor:
    def __init__(self, description: Any, rows: list[tuple[Any, ...]]) -> None:
        self.description = description
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class SqlAlchemyRow:
    def __init__(self, values: Mapping[str, Any]) -> None:
        self._mapping = values


class KeysRow:
    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = values

    def keys(self) -> list[str]:
        return list(self._values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]


def test_rows_from_cursor_uses_description_and_consumes_rows() -> None:
    cursor = Cursor(
        (("id", None), ("title", None)),
        [("todo", "To do"), ("done", "Done")],
    )

    assert rows_from_cursor(cursor) == [
        {"id": "todo", "title": "To do"},
        {"id": "done", "title": "Done"},
    ]


def test_rows_from_cursor_requires_named_unique_result_columns() -> None:
    with pytest.raises(ValueError, match="no result columns"):
        rows_from_cursor(Cursor(None, []))
    with pytest.raises(ValueError, match="must be unique"):
        rows_from_cursor(Cursor((("id", None), ("id", None)), [(1, 2)]))


def test_normalize_row_accepts_common_mapping_row_types() -> None:
    assert normalize_row({"id": 1}) == {"id": 1}
    assert normalize_row(SqlAlchemyRow({"id": 2})) == {"id": 2}
    assert normalize_row(KeysRow({"id": 3})) == {"id": 3}
    with pytest.raises(TypeError, match="Plain tuple rows"):
        normalize_row((4, "tuple"))


def test_snapshot_from_rows_normalizes_and_validates_atomically() -> None:
    snapshot = snapshot_from_rows(
        [SqlAlchemyRow({"id": "todo", "title": "  To do  "})],
        [
            KeysRow(
                {
                    "id": 1,
                    "column_id": "todo",
                    "title": "  Database card  ",
                    "tags": ["db"],
                }
            )
        ],
    )

    assert snapshot == {
        "columns": [{"id": "todo", "title": "To do"}],
        "cards": [
            {
                "id": 1,
                "column": "todo",
                "title": "Database card",
                "description": "",
                "priority": "",
                "tags": ["db"],
            }
        ],
    }
    with pytest.raises(BoardModelError, match="unknown column"):
        snapshot_from_rows(
            [{"id": "todo", "title": "To do"}],
            [{"id": 2, "column": "missing", "title": "Orphan"}],
        )


def test_snapshot_from_cursors_builds_the_exact_board_shape() -> None:
    columns_cursor = Cursor(
        (("id", None), ("title", None)),
        [("todo", "To do")],
    )
    cards_cursor = Cursor(
        (
            ("id", None),
            ("column", None),
            ("title", None),
            ("description", None),
            ("priority", None),
            ("tags", None),
        ),
        [(1, "todo", "Loaded", "From PostgreSQL", "High", ["database"])],
    )

    snapshot = snapshot_from_cursors(columns_cursor, cards_cursor)

    assert snapshot["cards"][0]["column"] == "todo"
    assert snapshot["cards"][0]["tags"] == ["database"]
