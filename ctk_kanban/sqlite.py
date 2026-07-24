"""Transactional SQLite data source included with CTkKanban."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, tzinfo
from math import isfinite
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import (
    BoardLoadResult,
    CardPage,
    CardQuery,
    ChangePage,
    ConflictDetails,
    MutationEvent,
    MutationResult,
)
from .exceptions import KanbanValidationError
from .query import card_matches_filters, card_matches_search, sort_cards

SCHEMA_VERSION = 2


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)


def _id_key(value: Any) -> str:
    return _json(value)


def _validate_storage_id(value: Any, label: str) -> None:
    """Reject IDs whose type or equality cannot survive a JSON round trip."""

    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise KanbanValidationError(f"{label} must be a string or integer for SQLite storage")
    if value == "":
        raise KanbanValidationError(f"{label} is required")


def _rank_value(card: dict[str, Any]) -> float:
    value = card.get("sort_order", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise KanbanValidationError("Card 'sort_order' must be a finite number")
    return float(value)


def _result_data(result: MutationResult) -> dict[str, Any]:
    conflict = result.conflict
    return {
        "accepted": result.accepted,
        "reason": result.reason,
        "card": result.card,
        "column": result.column,
        "changed_cards": result.changed_cards,
        "changed_columns": result.changed_columns,
        "id_map": [[old_id, new_id] for old_id, new_id in result.id_map.items()],
        "board_revision": result.board_revision,
        "retryable": result.retryable,
        "conflict": None
        if conflict is None
        else {
            "expected_revision": conflict.expected_revision,
            "actual_revision": conflict.actual_revision,
            "server_data": conflict.server_data,
            "message": conflict.message,
        },
    }


def _result_from_data(value: dict[str, Any]) -> MutationResult:
    conflict_data = value.get("conflict")
    conflict = None
    if isinstance(conflict_data, dict):
        conflict = ConflictDetails(
            conflict_data.get("expected_revision"),
            conflict_data.get("actual_revision"),
            conflict_data.get("server_data"),
            str(conflict_data.get("message") or "The board changed in storage"),
        )
    return MutationResult(
        accepted=bool(value.get("accepted", True)),
        reason=value.get("reason"),
        card=dict(value["card"]) if isinstance(value.get("card"), dict) else None,
        column=dict(value["column"]) if isinstance(value.get("column"), dict) else None,
        changed_cards=[dict(card) for card in value.get("changed_cards", [])],
        changed_columns=[dict(column) for column in value.get("changed_columns", [])],
        id_map={item[0]: item[1] for item in value.get("id_map", [])},
        board_revision=value.get("board_revision"),
        conflict=conflict,
        retryable=bool(value.get("retryable", False)),
    )


def _merge_canonical_records(
    target: list[dict[str, Any]], records: Iterator[dict[str, Any]]
) -> None:
    """Keep one final canonical record per ID in a combined batch result."""

    for record in records:
        record_id = record.get("id")
        for index, existing in enumerate(target):
            if existing.get("id") == record_id:
                target[index] = deepcopy(record)
                break
        else:
            target.append(deepcopy(record))


def _mapped_identifier(value: Any, id_map: dict[Any, Any]) -> Any:
    try:
        return id_map[value] if value in id_map else value
    except TypeError:
        return value


def _rebased_event(event: MutationEvent, id_map: dict[Any, Any]) -> MutationEvent:
    rebased = deepcopy(event)
    payload = rebased.payload
    for key in ("card_id", "old_card_id"):
        if key in payload:
            payload[key] = _mapped_identifier(payload[key], id_map)
    for key in ("card_data", "old_card_data"):
        record = payload.get(key)
        if isinstance(record, dict) and "id" in record:
            record["id"] = _mapped_identifier(record["id"], id_map)
    for key in ("changed_cards", "affected_cards", "cards"):
        records = payload.get(key)
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict) and "id" in record:
                    record["id"] = _mapped_identifier(record["id"], id_map)
    return rebased


class SQLiteKanbanDataSource:
    """Reference adapter using one SQLite transaction per mutation or batch."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    @staticmethod
    def _validate_column_record(column: dict[str, Any]) -> None:
        if not isinstance(column, dict) or "id" not in column:
            raise KanbanValidationError("Column data must include an 'id'")
        _validate_storage_id(column["id"], "Column 'id'")

    @staticmethod
    def _validate_card_record(card: dict[str, Any]) -> None:
        if not isinstance(card, dict) or "id" not in card or "column" not in card:
            raise KanbanValidationError("Card data must include 'id' and 'column'")
        _validate_storage_id(card["id"], "Card 'id'")
        _validate_storage_id(card["column"], "Card 'column'")

    @classmethod
    def _validate_snapshot(
        cls, columns: list[dict[str, Any]], cards: list[dict[str, Any]]
    ) -> None:
        column_keys: set[str] = set()
        for column in columns:
            cls._validate_column_record(column)
            key = _id_key(column["id"])
            if key in column_keys:
                raise KanbanValidationError(f"Duplicate column ID: {column['id']!r}")
            column_keys.add(key)
        card_keys: set[str] = set()
        for card in cards:
            cls._validate_card_record(card)
            _rank_value(card)
            key = _id_key(card["id"])
            if key in card_keys:
                raise KanbanValidationError(f"Duplicate card ID: {card['id']!r}")
            card_keys.add(key)
            if _id_key(card["column"]) not in column_keys:
                raise KanbanValidationError(
                    f"Card {card['id']!r} references unknown column {card['column']!r}"
                )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS kanban_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            version_row = connection.execute(
                "SELECT value FROM kanban_meta WHERE key = 'schema_version'"
            ).fetchone()
            try:
                stored_version = int(version_row["value"]) if version_row is not None else 0
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Invalid CTkKanban SQLite schema version") from exc
            if stored_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {stored_version} is newer than supported "
                    f"version {SCHEMA_VERSION}"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS kanban_boards (
                    board_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kanban_columns (
                    board_id TEXT NOT NULL,
                    id_key TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (board_id, id_key),
                    FOREIGN KEY (board_id) REFERENCES kanban_boards(board_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS kanban_cards (
                    board_id TEXT NOT NULL,
                    id_key TEXT NOT NULL,
                    column_key TEXT NOT NULL,
                    rank REAL NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (board_id, id_key),
                    FOREIGN KEY (board_id) REFERENCES kanban_boards(board_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS kanban_cards_column_rank
                    ON kanban_cards(board_id, column_key, rank);
                CREATE TABLE IF NOT EXISTS kanban_events (
                    event_id TEXT PRIMARY KEY,
                    board_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    result_data TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS kanban_events_board_revision
                    ON kanban_events(board_id, revision);
                """
            )
            event_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(kanban_events)").fetchall()
            }
            if "result_data" not in event_columns:
                connection.execute("ALTER TABLE kanban_events ADD COLUMN result_data TEXT")
            connection.execute(
                """INSERT INTO kanban_meta(key, value) VALUES('schema_version', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()

    def seed_board(
        self,
        board_id: str,
        columns: list[dict[str, Any]],
        cards: list[dict[str, Any]],
        *,
        replace: bool = False,
    ) -> None:
        """Create an initial board for examples, imports, and tests."""

        self._validate_snapshot(columns, cards)
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO kanban_boards(board_id, revision, updated_at) VALUES(?, 0, ?)",
                (board_id, now),
            )
            if replace:
                connection.execute("DELETE FROM kanban_cards WHERE board_id = ?", (board_id,))
                connection.execute("DELETE FROM kanban_columns WHERE board_id = ?", (board_id,))
                connection.execute("DELETE FROM kanban_events WHERE board_id = ?", (board_id,))
                connection.execute(
                    "UPDATE kanban_boards SET revision = 0, updated_at = ? WHERE board_id = ?",
                    (now, board_id),
                )
            for position, column in enumerate(columns):
                connection.execute(
                    "INSERT OR REPLACE INTO kanban_columns(board_id, id_key, position, data) VALUES(?, ?, ?, ?)",
                    (board_id, _id_key(column["id"]), position, _json(column)),
                )
            for card in cards:
                connection.execute(
                    "INSERT OR REPLACE INTO kanban_cards(board_id, id_key, column_key, rank, data) VALUES(?, ?, ?, ?, ?)",
                    (
                        board_id,
                        _id_key(card["id"]),
                        _id_key(card["column"]),
                        _rank_value(card),
                        _json(card),
                    ),
                )
            connection.commit()

    def load_board(self, board_id: str, query: CardQuery | None = None) -> BoardLoadResult:
        with self._connection() as connection:
            connection.execute("BEGIN")
            board = connection.execute(
                "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
            ).fetchone()
            if board is None:
                now = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    "INSERT INTO kanban_boards(board_id, revision, updated_at) VALUES(?, 0, ?)",
                    (board_id, now),
                )
            columns = [
                json.loads(row["data"])
                for row in connection.execute(
                    "SELECT data FROM kanban_columns WHERE board_id = ? ORDER BY position", (board_id,)
                )
            ]
            for column in columns:
                self._validate_column_record(column)
            page = self._query_cards(connection, board_id, query or CardQuery(limit=100))
            connection.commit()
        return BoardLoadResult(
            columns=columns,
            cards=page.cards,
            column_totals=page.column_totals,
            board_revision=page.board_revision,
            has_more=page.has_more,
        )

    def query_cards(self, board_id: str, query: CardQuery) -> CardPage:
        with self._connection() as connection:
            connection.execute("BEGIN")
            page = self._query_cards(connection, board_id, query)
            connection.commit()
            return page

    def _query_cards(
        self, connection: sqlite3.Connection, board_id: str, query: CardQuery
    ) -> CardPage:
        rows = connection.execute(
            "SELECT data FROM kanban_cards WHERE board_id = ? ORDER BY column_key, rank", (board_id,)
        ).fetchall()
        board = connection.execute(
            "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
        ).fetchone()
        column_keys = {
            str(row["id_key"])
            for row in connection.execute(
                "SELECT id_key FROM kanban_columns WHERE board_id = ?", (board_id,)
            ).fetchall()
        }
        all_cards = [json.loads(row["data"]) for row in rows]
        totals: dict[Any, int] = {}
        for card in all_cards:
            self._validate_card_record(card)
            if _id_key(card["column"]) not in column_keys:
                raise KanbanValidationError(
                    f"Card {card['id']!r} references unknown column {card['column']!r}"
                )
            totals[card["column"]] = totals.get(card["column"], 0) + 1
        cards = [card for card in all_cards if query.column_id is None or card["column"] == query.column_id]
        cards = [card for card in cards if card_matches_search(card, query.search)]
        try:
            query_timezone: tzinfo = ZoneInfo(query.timezone_name)
        except ZoneInfoNotFoundError:
            query_timezone = timezone.utc
        cards = [
            card
            for card in cards
            if card_matches_filters(
                card,
                query.filters,
                completion_field=query.completion_field,
                completed_columns=query.completed_columns,
                now=datetime.now(query_timezone),
            )
        ]
        cards = sort_cards(cards, query.sort_key, query.reverse)
        total = len(cards)
        offset = max(0, query.offset)
        limit = max(1, query.limit)
        return CardPage(
            cards=deepcopy(cards[offset : offset + limit]),
            total=total,
            offset=offset,
            limit=limit,
            column_totals=totals,
            board_revision=int(board["revision"]) if board else 0,
        )

    @staticmethod
    def _record_exists(
        connection: sqlite3.Connection, table: str, board_id: str, identifier: Any
    ) -> bool:
        queries = {
            "kanban_columns": (
                "SELECT 1 FROM kanban_columns WHERE board_id = ? AND id_key = ?"
            ),
            "kanban_cards": "SELECT 1 FROM kanban_cards WHERE board_id = ? AND id_key = ?",
        }
        if table not in queries:
            raise ValueError(f"Unsupported Kanban table: {table}")
        row = connection.execute(
            queries[table],
            (board_id, _id_key(identifier)),
        ).fetchone()
        return row is not None

    @staticmethod
    def _stored_card(
        connection: sqlite3.Connection, board_id: str, identifier: Any
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT data FROM kanban_cards WHERE board_id = ? AND id_key = ?",
            (board_id, _id_key(identifier)),
        ).fetchone()
        return json.loads(row["data"]) if row is not None else None

    @staticmethod
    def _server_snapshot(connection: sqlite3.Connection, board_id: str) -> dict[str, Any]:
        columns = [
            json.loads(row["data"])
            for row in connection.execute(
                "SELECT data FROM kanban_columns WHERE board_id = ? ORDER BY position",
                (board_id,),
            ).fetchall()
        ]
        cards = [
            json.loads(row["data"])
            for row in connection.execute(
                "SELECT data FROM kanban_cards WHERE board_id = ? ORDER BY column_key, rank",
                (board_id,),
            ).fetchall()
        ]
        return {"columns": columns, "cards": cards}

    @staticmethod
    def _replayed_result(
        connection: sqlite3.Connection, event: MutationEvent
    ) -> MutationResult | None:
        row = connection.execute(
            """SELECT board_id, revision, event_type, event_data, result_data
               FROM kanban_events WHERE event_id = ?""",
            (event.metadata.event_id,),
        ).fetchone()
        if row is None:
            return None
        board = connection.execute(
            "SELECT revision FROM kanban_boards WHERE board_id = ?", (row["board_id"],)
        ).fetchone()
        current_revision = int(board["revision"]) if board is not None else int(row["revision"])
        stored = json.loads(row["event_data"])
        if (
            row["board_id"] != event.metadata.board_id
            or row["event_type"] != event.type
            or stored.get("payload") != json.loads(_json(event.payload))
        ):
            return MutationResult(
                accepted=False,
                reason=f"Event ID {event.metadata.event_id!r} is already used by another mutation",
                board_revision=current_revision,
            )
        if row["result_data"]:
            result = _result_from_data(json.loads(row["result_data"]))
            result.board_revision = current_revision
            return result
        return MutationResult(board_revision=current_revision)

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = self._apply(connection, deepcopy(event))
            except (KeyError, TypeError, ValueError, OverflowError, sqlite3.IntegrityError) as exc:
                connection.rollback()
                return MutationResult(accepted=False, reason=str(exc) or "Invalid mutation")
            if not result.accepted:
                connection.rollback()
                return result
            connection.commit()
            return result

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        if not events:
            return MutationResult()
        board_id = events[0].metadata.board_id
        if any(event.metadata.board_id != board_id for event in events):
            return MutationResult(accepted=False, reason="A batch cannot span multiple boards")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            combined = MutationResult()
            id_map: dict[Any, Any] = {}
            for index, original in enumerate(events):
                event = _rebased_event(original, id_map)
                if index > 0:
                    row = connection.execute(
                        "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
                    ).fetchone()
                    event.metadata.expected_revision = int(row["revision"]) if row else 0
                try:
                    result = self._apply(connection, event)
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    OverflowError,
                    sqlite3.IntegrityError,
                ) as exc:
                    connection.rollback()
                    return MutationResult(accepted=False, reason=str(exc) or "Invalid mutation")
                if not result.accepted:
                    connection.rollback()
                    return result
                id_map.update(result.id_map)
                card_records = iter(
                    ([result.card] if result.card is not None else []) + result.changed_cards
                )
                column_records = iter(
                    ([result.column] if result.column is not None else [])
                    + result.changed_columns
                )
                _merge_canonical_records(combined.changed_cards, card_records)
                _merge_canonical_records(combined.changed_columns, column_records)
                combined.board_revision = result.board_revision
            combined.id_map.update(id_map)
            connection.commit()
            return combined

    def _apply(self, connection: sqlite3.Connection, event: MutationEvent) -> MutationResult:
        replayed = self._replayed_result(connection, event)
        if replayed is not None:
            return replayed

        board_id = event.metadata.board_id
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT OR IGNORE INTO kanban_boards(board_id, revision, updated_at) VALUES(?, 0, ?)",
            (board_id, now),
        )
        row = connection.execute(
            "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
        ).fetchone()
        actual_revision = int(row["revision"])
        expected = event.metadata.expected_revision
        if expected is not None and int(expected) != actual_revision:
            return MutationResult(
                accepted=False,
                reason="Revision conflict",
                conflict=ConflictDetails(
                    expected,
                    actual_revision,
                    self._server_snapshot(connection, board_id),
                ),
                board_revision=actual_revision,
            )

        def rejected(reason: str) -> MutationResult:
            return MutationResult(
                accepted=False,
                reason=reason,
                board_revision=actual_revision,
            )

        payload = deepcopy(event.payload)
        result = MutationResult()
        event_type = event.type
        if event_type == "card_created":
            card = dict(payload["card_data"])
            self._validate_card_record(card)
            local_id = card["id"]
            if not self._record_exists(connection, "kanban_columns", board_id, card["column"]):
                return rejected(f"Unknown column: {card['column']!r}")
            if payload.get("temporary_id"):
                card["id"] = str(uuid4())
                result.id_map[local_id] = card["id"]
            if self._record_exists(connection, "kanban_cards", board_id, card["id"]):
                return rejected(f"Card already exists: {card['id']!r}")
            card.setdefault("created_at", now)
            card["updated_at"] = now
            card["version"] = int(card.get("version", 0)) + 1
            connection.execute(
                "INSERT INTO kanban_cards(board_id, id_key, column_key, rank, data) VALUES(?, ?, ?, ?, ?)",
                (
                    board_id,
                    _id_key(card["id"]),
                    _id_key(card["column"]),
                    _rank_value(card),
                    _json(card),
                ),
            )
            result.card = card
        elif event_type == "card_updated":
            card = dict(payload["card_data"])
            old_id = payload.get("old_card_id", card["id"])
            self._validate_card_record(card)
            _validate_storage_id(old_id, "Old card 'id'")
            stored_card = self._stored_card(connection, board_id, old_id)
            if stored_card is None:
                return rejected(f"Card not found: {old_id!r}")
            if not self._record_exists(connection, "kanban_columns", board_id, card["column"]):
                return rejected(f"Unknown column: {card['column']!r}")
            if card["id"] != old_id and self._record_exists(
                connection, "kanban_cards", board_id, card["id"]
            ):
                return rejected(f"Card already exists: {card['id']!r}")
            card["updated_at"] = now
            card["version"] = max(
                int(card.get("version", 0)), int(stored_card.get("version", 0))
            ) + 1
            cursor = connection.execute(
                """UPDATE kanban_cards
                   SET id_key = ?, column_key = ?, rank = ?, data = ?
                   WHERE board_id = ? AND id_key = ?""",
                (
                    _id_key(card["id"]),
                    _id_key(card["column"]),
                    _rank_value(card),
                    _json(card),
                    board_id,
                    _id_key(old_id),
                ),
            )
            if cursor.rowcount != 1:
                return rejected(f"Card not found: {old_id!r}")
            result.card = card
        elif event_type == "card_deleted":
            card_id = payload["card_id"]
            _validate_storage_id(card_id, "Card 'id'")
            cursor = connection.execute(
                "DELETE FROM kanban_cards WHERE board_id = ? AND id_key = ?",
                (board_id, _id_key(card_id)),
            )
            if cursor.rowcount != 1:
                return rejected(f"Card not found: {card_id!r}")
        elif event_type in {"card_moved", "card_reordered"}:
            changed = payload.get("changed_cards") or [payload["card_data"]]
            if not isinstance(changed, list) or not changed:
                return rejected("A card move must include at least one changed card")
            seen_card_keys: set[str] = set()
            stored_cards: dict[str, dict[str, Any]] = {}
            for item in changed:
                card = dict(item)
                self._validate_card_record(card)
                card_key = _id_key(card["id"])
                if card_key in seen_card_keys:
                    return rejected(f"Duplicate changed card ID: {card['id']!r}")
                seen_card_keys.add(card_key)
                stored_card = self._stored_card(connection, board_id, card["id"])
                if stored_card is None:
                    return rejected(f"Card not found: {card['id']!r}")
                stored_cards[card_key] = stored_card
                if not self._record_exists(connection, "kanban_columns", board_id, card["column"]):
                    return rejected(f"Unknown column: {card['column']!r}")
            canonical: list[dict[str, Any]] = []
            for item in changed:
                card = dict(item)
                card["updated_at"] = now
                card["version"] = max(
                    int(card.get("version", 0)),
                    int(stored_cards[_id_key(card["id"])].get("version", 0)),
                ) + 1
                cursor = connection.execute(
                    "UPDATE kanban_cards SET column_key = ?, rank = ?, data = ? WHERE board_id = ? AND id_key = ?",
                    (
                        _id_key(card["column"]),
                        _rank_value(card),
                        _json(card),
                        board_id,
                        _id_key(card["id"]),
                    ),
                )
                if cursor.rowcount != 1:
                    return rejected(f"Card not found: {card['id']!r}")
                canonical.append(card)
            result.changed_cards = canonical
            primary_id = payload.get("card_id", canonical[0]["id"])
            _validate_storage_id(primary_id, "Card 'id'")
            result.card = next((card for card in canonical if card["id"] == primary_id), None)
            if result.card is None:
                return rejected(f"Moved card not found in changed cards: {primary_id!r}")
        elif event_type == "column_created":
            column = dict(payload["column_data"])
            self._validate_column_record(column)
            if self._record_exists(connection, "kanban_columns", board_id, column["id"]):
                return rejected(f"Column already exists: {column['id']!r}")
            count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM kanban_columns WHERE board_id = ?", (board_id,)
                ).fetchone()["count"]
            )
            position = max(0, min(int(payload.get("index", count)), count))
            connection.execute(
                "UPDATE kanban_columns SET position = position + 1 WHERE board_id = ? AND position >= ?",
                (board_id, position),
            )
            connection.execute(
                "INSERT INTO kanban_columns(board_id, id_key, position, data) VALUES(?, ?, ?, ?)",
                (board_id, _id_key(column["id"]), position, _json(column)),
            )
            result.column = column
        elif event_type == "column_updated":
            column = dict(payload["column_data"])
            old_id = payload.get("old_column_id", column["id"])
            self._validate_column_record(column)
            _validate_storage_id(old_id, "Old column 'id'")
            if not self._record_exists(connection, "kanban_columns", board_id, old_id):
                return rejected(f"Column not found: {old_id!r}")
            if column["id"] != old_id and self._record_exists(
                connection, "kanban_columns", board_id, column["id"]
            ):
                return rejected(f"Column already exists: {column['id']!r}")
            cursor = connection.execute(
                "UPDATE kanban_columns SET id_key = ?, data = ? WHERE board_id = ? AND id_key = ?",
                (_id_key(column["id"]), _json(column), board_id, _id_key(old_id)),
            )
            if cursor.rowcount != 1:
                return rejected(f"Column not found: {old_id!r}")
            if old_id != column["id"]:
                cards = connection.execute(
                    "SELECT id_key, data FROM kanban_cards WHERE board_id = ? AND column_key = ?",
                    (board_id, _id_key(old_id)),
                ).fetchall()
                for card_row in cards:
                    card = json.loads(card_row["data"])
                    card["column"] = column["id"]
                    connection.execute(
                        "UPDATE kanban_cards SET column_key = ?, data = ? WHERE board_id = ? AND id_key = ?",
                        (_id_key(column["id"]), _json(card), board_id, card_row["id_key"]),
                    )
            result.column = column
        elif event_type == "column_deleted":
            column_id = payload["column_id"]
            _validate_storage_id(column_id, "Column 'id'")
            column_row = connection.execute(
                "SELECT position FROM kanban_columns WHERE board_id = ? AND id_key = ?",
                (board_id, _id_key(column_id)),
            ).fetchone()
            if column_row is None:
                return rejected(f"Column not found: {column_id!r}")
            card_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM kanban_cards WHERE board_id = ? AND column_key = ?",
                    (board_id, _id_key(column_id)),
                ).fetchone()["count"]
            )
            if card_count:
                return rejected("Cannot delete a column while it still contains cards")
            cursor = connection.execute(
                "DELETE FROM kanban_columns WHERE board_id = ? AND id_key = ?",
                (board_id, _id_key(column_id)),
            )
            if cursor.rowcount != 1:
                return rejected(f"Column not found: {column_id!r}")
            connection.execute(
                "UPDATE kanban_columns SET position = position - 1 WHERE board_id = ? AND position > ?",
                (board_id, int(column_row["position"])),
            )
        elif event_type == "column_reordered":
            columns = payload["columns"]
            if not isinstance(columns, list):
                return rejected("Column reorder data must be a list")
            requested_keys: list[str] = []
            for column in columns:
                self._validate_column_record(column)
                requested_keys.append(_id_key(column["id"]))
            if len(requested_keys) != len(set(requested_keys)):
                return rejected("Column reorder data contains duplicate IDs")
            stored_keys = {
                str(row["id_key"])
                for row in connection.execute(
                    "SELECT id_key FROM kanban_columns WHERE board_id = ?", (board_id,)
                ).fetchall()
            }
            if set(requested_keys) != stored_keys:
                return rejected("Column reorder data must contain every stored column exactly once")
            for position, column in enumerate(columns):
                cursor = connection.execute(
                    "UPDATE kanban_columns SET position = ? WHERE board_id = ? AND id_key = ?",
                    (position, board_id, _id_key(column["id"])),
                )
                if cursor.rowcount != 1:
                    return rejected(f"Column not found: {column['id']!r}")
        elif event_type == "board_replaced":
            columns = payload["columns"]
            cards = payload["cards"]
            if not isinstance(columns, list) or not isinstance(cards, list):
                return rejected("Board replacement requires column and card lists")
            self._validate_snapshot(columns, cards)
            connection.execute("DELETE FROM kanban_cards WHERE board_id = ?", (board_id,))
            connection.execute("DELETE FROM kanban_columns WHERE board_id = ?", (board_id,))
            for position, column in enumerate(columns):
                connection.execute(
                    "INSERT INTO kanban_columns(board_id, id_key, position, data) VALUES(?, ?, ?, ?)",
                    (board_id, _id_key(column["id"]), position, _json(column)),
                )
            for card in cards:
                connection.execute(
                    "INSERT INTO kanban_cards(board_id, id_key, column_key, rank, data) VALUES(?, ?, ?, ?, ?)",
                    (
                        board_id,
                        _id_key(card["id"]),
                        _id_key(card["column"]),
                        _rank_value(card),
                        _json(card),
                    ),
                )
        else:
            return rejected(f"Unsupported mutation type: {event_type}")
        new_revision = actual_revision + 1
        connection.execute(
            "UPDATE kanban_boards SET revision = ?, updated_at = ? WHERE board_id = ?",
            (new_revision, now, board_id),
        )
        persisted_event = event.to_dict()
        persisted_event["payload"] = payload
        result.board_revision = new_revision
        connection.execute(
            """INSERT INTO kanban_events(
                   event_id, board_id, revision, event_type, event_data, result_data, created_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                event.metadata.event_id,
                board_id,
                new_revision,
                event_type,
                _json(persisted_event),
                _json(_result_data(result)),
                now,
            ),
        )
        return result

    def get_changes(self, board_id: str, since_revision: int | str | None) -> ChangePage:
        revision = int(since_revision or 0)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_data FROM kanban_events WHERE board_id = ? AND revision > ? ORDER BY revision",
                (board_id, revision),
            ).fetchall()
            board = connection.execute(
                "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
            ).fetchone()
        events = [MutationEvent.from_mapping(json.loads(row["event_data"])) for row in rows]
        return ChangePage(events, int(board["revision"]) if board else revision)
