"""Small adapters for database and row-oriented data sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .fields import FieldInput
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


def _rows_from_source(source: Any) -> list[dict[str, Any]]:
    """Normalize a row iterable or consume a DB-API cursor."""

    if hasattr(source, "description") and callable(getattr(source, "fetchall", None)):
        return rows_from_cursor(source)
    return normalize_rows(source)


def _remap_row_keys(
    rows: list[dict[str, Any]],
    keys: Mapping[str, str] | None,
    *,
    allowed: set[str],
    kind: str,
) -> list[dict[str, Any]]:
    if keys is None:
        return rows
    if not isinstance(keys, Mapping):
        raise TypeError(f"{kind}_keys must be a mapping")
    unknown = set(keys) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown {kind} key mapping(s): {names}")
    for canonical, source in keys.items():
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{kind}_keys[{canonical!r}] must name a nonblank source column")

    remapped: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        value = dict(row)
        for canonical, source in keys.items():
            if source not in row:
                raise ValueError(f"{kind} row {index} is missing mapped source column {source!r}")
            value[canonical] = row[source]
        for canonical, source in keys.items():
            if source != canonical and source not in keys:
                value.pop(source, None)
        remapped.append(value)
    return remapped


def snapshot_from_rows(
    columns: Iterable[Any] | Any,
    cards: Iterable[Any] | Any,
    *,
    fields: Iterable[FieldInput] | None = None,
    card_keys: Mapping[str, str] | None = None,
    column_keys: Mapping[str, str] | None = None,
) -> BoardSnapshot:
    """Normalize and validate row iterables or cursors as a board snapshot.

    ``card_keys`` maps canonical ``id``, ``column``, and ``title`` names to
    source database columns. ``column_keys`` does the same for ``id`` and
    ``title`` board-column values.
    """

    model = BoardModel(
        columns=_remap_row_keys(
            _rows_from_source(columns),
            column_keys,
            allowed={"id", "title"},
            kind="column",
        ),
        cards=_remap_row_keys(
            _rows_from_source(cards),
            card_keys,
            allowed={"id", "column", "title"},
            kind="card",
        ),
        fields=fields,
    )
    return model.snapshot()


def snapshot_from_cursors(
    columns_cursor: Any,
    cards_cursor: Any,
    *,
    fields: Iterable[FieldInput] | None = None,
    card_keys: Mapping[str, str] | None = None,
    column_keys: Mapping[str, str] | None = None,
) -> BoardSnapshot:
    """Build a validated board snapshot from two executed DB-API cursors."""

    return snapshot_from_rows(
        rows_from_cursor(columns_cursor),
        rows_from_cursor(cards_cursor),
        fields=fields,
        card_keys=card_keys,
        column_keys=column_keys,
    )


__all__ = [
    "normalize_row",
    "normalize_rows",
    "rows_from_cursor",
    "snapshot_from_cursors",
    "snapshot_from_rows",
]
