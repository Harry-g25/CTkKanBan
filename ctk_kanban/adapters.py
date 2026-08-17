"""Small adapters for database and row-oriented data sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .model import BoardModel, BoardSnapshot


def normalize_row(row: Any) -> dict[str, Any]:
    """Convert common database row objects into a plain dictionary.

    Mapping rows, ``sqlite3.Row`` values, and SQLAlchemy-style rows exposing
    ``_mapping`` are accepted. Plain DB-API tuples need cursor metadata and
    should be converted with :func:`rows_from_cursor` instead.
    """

    if isinstance(row, Mapping):
        return dict(row)

    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return dict(mapping)

    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in keys()}

    raise TypeError(
        "Rows must be mappings, sqlite3.Row objects, SQLAlchemy mapping rows, "
        "or PostgreSQL rows returned as dictionaries. Plain tuple rows require "
        "rows_from_cursor(cursor)."
    )


def normalize_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Convert an iterable of supported row objects into dictionaries."""

    return [normalize_row(row) for row in rows]


def rows_from_cursor(cursor: Any) -> list[dict[str, Any]]:
    """Consume a DB-API cursor result and return dictionaries by column name."""

    if cursor.description is None:
        raise ValueError("Cursor has no result columns. Execute a SELECT query first.")
    column_names = [column[0] for column in cursor.description]
    if len(column_names) != len(set(column_names)):
        raise ValueError("Cursor result column names must be unique; use SQL aliases.")
    return [dict(zip(column_names, row, strict=False)) for row in cursor.fetchall()]


def snapshot_from_rows(
    columns: Iterable[Any],
    cards: Iterable[Any],
) -> BoardSnapshot:
    """Normalize and validate column/card row iterables as a board snapshot."""

    model = BoardModel(
        columns=normalize_rows(columns),
        cards=normalize_rows(cards),
    )
    return model.snapshot()


def snapshot_from_cursors(columns_cursor: Any, cards_cursor: Any) -> BoardSnapshot:
    """Build a validated board snapshot from two executed DB-API cursors."""

    return snapshot_from_rows(
        rows_from_cursor(columns_cursor),
        rows_from_cursor(cards_cursor),
    )


__all__ = [
    "normalize_row",
    "normalize_rows",
    "rows_from_cursor",
    "snapshot_from_cursors",
    "snapshot_from_rows",
]
