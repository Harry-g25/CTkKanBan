"""Transactional SQLite data source included with CTkKanban."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, tzinfo
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
from .query import card_matches_filters, card_matches_search, sort_cards

SCHEMA_VERSION = 1


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)


def _id_key(value: Any) -> str:
    return _json(value)


class SQLiteKanbanDataSource:
    """Reference adapter using one SQLite transaction per mutation or batch."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS kanban_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
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
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO kanban_meta(key, value) VALUES('schema_version', ?)",
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

        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if replace:
                connection.execute("DELETE FROM kanban_cards WHERE board_id = ?", (board_id,))
                connection.execute("DELETE FROM kanban_columns WHERE board_id = ?", (board_id,))
            connection.execute(
                "INSERT OR IGNORE INTO kanban_boards(board_id, revision, updated_at) VALUES(?, 0, ?)",
                (board_id, now),
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
                        float(card.get("sort_order", 0)),
                        _json(card),
                    ),
                )
            connection.commit()

    def load_board(self, board_id: str, query: CardQuery | None = None) -> BoardLoadResult:
        with self._connection() as connection:
            board = connection.execute(
                "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
            ).fetchone()
            if board is None:
                now = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    "INSERT INTO kanban_boards(board_id, revision, updated_at) VALUES(?, 0, ?)",
                    (board_id, now),
                )
                connection.commit()
                revision = 0
            else:
                revision = int(board["revision"])
            columns = [
                json.loads(row["data"])
                for row in connection.execute(
                    "SELECT data FROM kanban_columns WHERE board_id = ? ORDER BY position", (board_id,)
                )
            ]
        page = self.query_cards(board_id, query or CardQuery(limit=100))
        return BoardLoadResult(
            columns=columns,
            cards=page.cards,
            column_totals=page.column_totals,
            board_revision=revision,
            has_more=page.has_more,
        )

    def query_cards(self, board_id: str, query: CardQuery) -> CardPage:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT data FROM kanban_cards WHERE board_id = ? ORDER BY column_key, rank", (board_id,)
            ).fetchall()
            board = connection.execute(
                "SELECT revision FROM kanban_boards WHERE board_id = ?", (board_id,)
            ).fetchone()
        all_cards = [json.loads(row["data"]) for row in rows]
        totals: dict[Any, int] = {}
        for card in all_cards:
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

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = self._apply(connection, event)
            if not result.accepted:
                connection.rollback()
                return result
            connection.commit()
            return result

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        if not events:
            return MutationResult()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            combined = MutationResult()
            expected = events[0].metadata.expected_revision
            for index, event in enumerate(events):
                if index > 0:
                    event.metadata.expected_revision = None
                result = self._apply(connection, event)
                if not result.accepted:
                    connection.rollback()
                    return result
                if result.card is not None:
                    combined.changed_cards.append(result.card)
                    if event.type == "card_created":
                        local_id = event.payload["card_data"]["id"]
                        if local_id != result.card["id"]:
                            combined.id_map[local_id] = result.card["id"]
                combined.changed_cards.extend(result.changed_cards)
                if result.column is not None:
                    combined.changed_columns.append(result.column)
                combined.changed_columns.extend(result.changed_columns)
                combined.board_revision = result.board_revision
            connection.commit()
            events[0].metadata.expected_revision = expected
            return combined

    def _apply(self, connection: sqlite3.Connection, event: MutationEvent) -> MutationResult:
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
            server = self.load_board(board_id)
            return MutationResult(
                accepted=False,
                reason="Revision conflict",
                conflict=ConflictDetails(expected, actual_revision, {
                    "columns": server.columns,
                    "cards": server.cards,
                }),
                board_revision=actual_revision,
            )
        payload = deepcopy(event.payload)
        result = MutationResult()
        event_type = event.type
        if event_type == "card_created":
            card = dict(payload["card_data"])
            if payload.get("temporary_id"):
                card["id"] = str(uuid4())
            card.setdefault("created_at", now)
            card["updated_at"] = now
            card["version"] = int(card.get("version", 0)) + 1
            connection.execute(
                "INSERT INTO kanban_cards(board_id, id_key, column_key, rank, data) VALUES(?, ?, ?, ?, ?)",
                (board_id, _id_key(card["id"]), _id_key(card["column"]), float(card.get("sort_order", 0)), _json(card)),
            )
            result.card = card
        elif event_type == "card_updated":
            card = dict(payload["card_data"])
            old_id = payload.get("old_card_id", card["id"])
            card["updated_at"] = now
            card["version"] = int(card.get("version", 0)) + 1
            connection.execute(
                "DELETE FROM kanban_cards WHERE board_id = ? AND id_key = ?", (board_id, _id_key(old_id))
            )
            connection.execute(
                "INSERT INTO kanban_cards(board_id, id_key, column_key, rank, data) VALUES(?, ?, ?, ?, ?)",
                (board_id, _id_key(card["id"]), _id_key(card["column"]), float(card.get("sort_order", 0)), _json(card)),
            )
            result.card = card
        elif event_type == "card_deleted":
            connection.execute(
                "DELETE FROM kanban_cards WHERE board_id = ? AND id_key = ?",
                (board_id, _id_key(payload["card_id"])),
            )
        elif event_type in {"card_moved", "card_reordered"}:
            changed = payload.get("changed_cards") or [payload["card_data"]]
            canonical: list[dict[str, Any]] = []
            for item in changed:
                card = dict(item)
                card["updated_at"] = now
                card["version"] = int(card.get("version", 0)) + 1
                connection.execute(
                    "UPDATE kanban_cards SET column_key = ?, rank = ?, data = ? WHERE board_id = ? AND id_key = ?",
                    (_id_key(card["column"]), float(card.get("sort_order", 0)), _json(card), board_id, _id_key(card["id"])),
                )
                canonical.append(card)
            result.changed_cards = canonical
            result.card = next((card for card in canonical if card["id"] == payload.get("card_id")), None)
        elif event_type == "column_created":
            column = dict(payload["column_data"])
            position = int(payload.get("index", 0))
            connection.execute(
                "INSERT INTO kanban_columns(board_id, id_key, position, data) VALUES(?, ?, ?, ?)",
                (board_id, _id_key(column["id"]), position, _json(column)),
            )
            result.column = column
        elif event_type == "column_updated":
            column = dict(payload["column_data"])
            old_id = payload.get("old_column_id", column["id"])
            connection.execute(
                "UPDATE kanban_columns SET id_key = ?, data = ? WHERE board_id = ? AND id_key = ?",
                (_id_key(column["id"]), _json(column), board_id, _id_key(old_id)),
            )
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
            connection.execute(
                "DELETE FROM kanban_columns WHERE board_id = ? AND id_key = ?",
                (board_id, _id_key(payload["column_id"])),
            )
        elif event_type == "column_reordered":
            for position, column in enumerate(payload["columns"]):
                connection.execute(
                    "UPDATE kanban_columns SET position = ? WHERE board_id = ? AND id_key = ?",
                    (position, board_id, _id_key(column["id"])),
                )
        elif event_type == "board_replaced":
            connection.execute("DELETE FROM kanban_cards WHERE board_id = ?", (board_id,))
            connection.execute("DELETE FROM kanban_columns WHERE board_id = ?", (board_id,))
            for position, column in enumerate(payload["columns"]):
                connection.execute(
                    "INSERT INTO kanban_columns(board_id, id_key, position, data) VALUES(?, ?, ?, ?)",
                    (board_id, _id_key(column["id"]), position, _json(column)),
                )
            for card in payload["cards"]:
                connection.execute(
                    "INSERT INTO kanban_cards(board_id, id_key, column_key, rank, data) VALUES(?, ?, ?, ?, ?)",
                    (
                        board_id,
                        _id_key(card["id"]),
                        _id_key(card["column"]),
                        float(card.get("sort_order", 0)),
                        _json(card),
                    ),
                )
        else:
            return MutationResult(accepted=False, reason=f"Unsupported mutation type: {event_type}")
        new_revision = actual_revision + 1
        connection.execute(
            "UPDATE kanban_boards SET revision = ?, updated_at = ? WHERE board_id = ?",
            (new_revision, now, board_id),
        )
        persisted_event = event.to_dict()
        persisted_event["payload"] = payload
        connection.execute(
            "INSERT INTO kanban_events(event_id, board_id, revision, event_type, event_data, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (event.metadata.event_id, board_id, new_revision, event_type, _json(persisted_event), now),
        )
        result.board_revision = new_revision
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
