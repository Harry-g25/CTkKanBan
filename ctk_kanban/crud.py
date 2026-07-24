"""Small CRUD-to-Kanban bridge for application-owned database layers."""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Any, Callable, ContextManager, Iterable, Literal, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import (
    BoardLoadResult,
    CardPage,
    CardQuery,
    ChangePage,
    EventMetadata,
    MutationEvent,
    MutationResult,
)
from .query import card_matches_filters, card_matches_search, sort_cards

CRUDResource = Literal["card", "column"]
CRUDWriteResult = Mapping[str, Any] | MutationResult | bool | None


@dataclass(frozen=True, slots=True)
class CRUDContext:
    """Extra information available to each application CRUD callback.

    ``transaction`` is the object yielded by the optional transaction callback,
    such as a SQLAlchemy session. ``position`` is populated for ordered column
    writes and ``previous_id`` is populated for updates.
    """

    event: MutationEvent
    transaction: Any = None
    position: int | None = None
    previous_id: Any = None

    @property
    def metadata(self) -> EventMetadata:
        return self.event.metadata


CRUDRead = Callable[[str], BoardLoadResult | Mapping[str, Any]]
CRUDCreate = Callable[[CRUDResource, str, dict[str, Any], CRUDContext], CRUDWriteResult]
CRUDUpdate = Callable[
    [CRUDResource, str, Any, dict[str, Any], CRUDContext],
    CRUDWriteResult,
]
CRUDDelete = Callable[[CRUDResource, str, Any, CRUDContext], CRUDWriteResult]
CRUDTransaction = Callable[[list[MutationEvent]], ContextManager[Any]]
CRUDChanges = Callable[[str, int | str | None], ChangePage | Mapping[str, Any]]


class _RejectedCRUD(Exception):
    def __init__(self, result: MutationResult) -> None:
        super().__init__(result.reason or "CRUD operation rejected")
        self.result = result


def _mapped_identifier(value: Any, id_map: dict[Any, Any]) -> Any:
    try:
        return id_map[value] if value in id_map else value
    except TypeError:
        return value


def _rebase_event(event: MutationEvent, id_map: dict[Any, Any]) -> MutationEvent:
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


def _merge_records(target: list[dict[str, Any]], records: Iterable[dict[str, Any]]) -> None:
    for record in records:
        for index, existing in enumerate(target):
            if existing.get("id") == record.get("id"):
                target[index] = deepcopy(record)
                break
        else:
            target.append(deepcopy(record))


class CRUDKanbanDataSource:
    """Adapt four ordinary CRUD callbacks to :class:`KanbanDataSource`.

    The callbacks own database-specific code. This class translates Kanban
    mutation events into record-level creates, updates, and deletes, provides
    in-memory querying over the read result, and groups batches with an optional
    application transaction context.
    """

    def __init__(
        self,
        *,
        read: CRUDRead,
        create: CRUDCreate,
        update: CRUDUpdate,
        delete: CRUDDelete,
        transaction: CRUDTransaction | None = None,
        changes: CRUDChanges | None = None,
    ) -> None:
        for name, callback in (
            ("read", read),
            ("create", create),
            ("update", update),
            ("delete", delete),
        ):
            if not callable(callback):
                raise TypeError(f"{name} must be callable")
        if transaction is not None and not callable(transaction):
            raise TypeError("transaction must be callable")
        if changes is not None and not callable(changes):
            raise TypeError("changes must be callable")
        self._read = read
        self._create = create
        self._update = update
        self._delete = delete
        self._transaction = transaction
        self._changes = changes

    @staticmethod
    def _coerce_board(value: BoardLoadResult | Mapping[str, Any]) -> BoardLoadResult:
        if isinstance(value, BoardLoadResult):
            return deepcopy(value)
        if not isinstance(value, Mapping):
            raise TypeError("read must return BoardLoadResult or a mapping")
        columns = value.get("columns", [])
        cards = value.get("cards", [])
        if not isinstance(columns, (list, tuple)) or not isinstance(cards, (list, tuple)):
            raise TypeError("read result 'columns' and 'cards' must be lists")
        normalized_columns = [dict(column) for column in columns]
        normalized_cards = [dict(card) for card in cards]
        raw_totals = value.get("column_totals")
        totals: dict[Any, int] = {}
        if isinstance(raw_totals, Mapping):
            totals = {key: int(count) for key, count in raw_totals.items()}
        if not totals:
            for card in normalized_cards:
                column_id = card.get("column")
                totals[column_id] = totals.get(column_id, 0) + 1
        return BoardLoadResult(
            columns=normalized_columns,
            cards=normalized_cards,
            column_totals=totals,
            board_revision=value.get("board_revision", value.get("revision")),
            has_more=bool(value.get("has_more", False)),
        )

    def _read_board(self, board_id: str) -> BoardLoadResult:
        return self._coerce_board(self._read(board_id))

    @staticmethod
    def _page(board: BoardLoadResult, query: CardQuery) -> CardPage:
        totals: dict[Any, int] = {}
        for card in board.cards:
            column_id = card.get("column")
            totals[column_id] = totals.get(column_id, 0) + 1
        cards = [
            deepcopy(card)
            for card in board.cards
            if query.column_id is None or card.get("column") == query.column_id
        ]
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
            cards=cards[offset : offset + limit],
            total=total,
            offset=offset,
            limit=limit,
            column_totals=totals,
            board_revision=board.board_revision,
        )

    def load_board(self, board_id: str, query: CardQuery | None = None) -> BoardLoadResult:
        board = self._read_board(board_id)
        if query is None:
            return board
        page = self._page(board, query)
        return BoardLoadResult(
            columns=board.columns,
            cards=page.cards,
            column_totals=page.column_totals,
            board_revision=page.board_revision,
            has_more=page.has_more,
        )

    def query_cards(self, board_id: str, query: CardQuery) -> CardPage:
        return self._page(self._read_board(board_id), query)

    @staticmethod
    def _coerce_write(
        value: CRUDWriteResult,
        resource: CRUDResource,
        fallback: dict[str, Any] | None,
    ) -> MutationResult:
        if isinstance(value, MutationResult):
            result = deepcopy(value)
        elif value is False:
            return MutationResult(accepted=False, reason=f"{resource.title()} CRUD callback rejected write")
        elif value is None or value is True:
            result = MutationResult()
        elif isinstance(value, Mapping):
            canonical = {**(fallback or {}), **dict(value)}
            result = MutationResult()
            if resource == "card":
                result.card = canonical
            else:
                result.column = canonical
        else:
            raise TypeError(
                "CRUD write callbacks must return a record mapping, MutationResult, bool, or None"
            )
        if result.accepted and fallback is not None:
            if resource == "card" and result.card is None:
                result.card = deepcopy(fallback)
            elif resource == "column" and result.column is None:
                result.column = deepcopy(fallback)
        return result

    def _create_record(
        self,
        resource: CRUDResource,
        board_id: str,
        record: dict[str, Any],
        event: MutationEvent,
        transaction: Any,
        *,
        position: int | None = None,
    ) -> MutationResult:
        context = CRUDContext(event, transaction, position=position)
        value = self._create(resource, board_id, deepcopy(record), context)
        result = self._coerce_write(value, resource, record)
        if result.accepted and resource == "card" and result.card is not None:
            local_id = record.get("id")
            canonical_id = result.card.get("id")
            if local_id != canonical_id:
                result.id_map[local_id] = canonical_id
        return result

    def _update_record(
        self,
        resource: CRUDResource,
        board_id: str,
        previous_id: Any,
        record: dict[str, Any],
        event: MutationEvent,
        transaction: Any,
        *,
        position: int | None = None,
    ) -> MutationResult:
        context = CRUDContext(
            event,
            transaction,
            position=position,
            previous_id=previous_id,
        )
        value = self._update(
            resource,
            board_id,
            previous_id,
            deepcopy(record),
            context,
        )
        return self._coerce_write(value, resource, record)

    def _delete_record(
        self,
        resource: CRUDResource,
        board_id: str,
        record_id: Any,
        event: MutationEvent,
        transaction: Any,
    ) -> MutationResult:
        context = CRUDContext(event, transaction, previous_id=record_id)
        value = self._delete(resource, board_id, record_id, context)
        result = self._coerce_write(value, resource, None)
        if isinstance(value, Mapping):
            if resource == "card":
                result.card = None
            else:
                result.column = None
        return result

    @staticmethod
    def _require_accepted(result: MutationResult) -> MutationResult:
        if not result.accepted or result.conflict is not None:
            raise _RejectedCRUD(result)
        return result

    def _apply(self, event: MutationEvent, transaction: Any) -> MutationResult:
        board_id = event.metadata.board_id
        payload = deepcopy(event.payload)
        event_type = event.type

        if event_type == "card_created":
            card = dict(payload["card_data"])
            return self._create_record("card", board_id, card, event, transaction)
        if event_type == "card_updated":
            card = dict(payload["card_data"])
            old_id = payload.get("old_card_id", card["id"])
            return self._update_record("card", board_id, old_id, card, event, transaction)
        if event_type == "card_deleted":
            return self._delete_record("card", board_id, payload["card_id"], event, transaction)
        if event_type in {"card_moved", "card_reordered"}:
            raw_cards = payload.get("changed_cards") or [payload["card_data"]]
            if not isinstance(raw_cards, list) or not raw_cards:
                return MutationResult(accepted=False, reason="A card move requires changed cards")
            combined = MutationResult()
            for raw_card in raw_cards:
                card = dict(raw_card)
                result = self._require_accepted(
                    self._update_record(
                        "card",
                        board_id,
                        card["id"],
                        card,
                        event,
                        transaction,
                    )
                )
                canonical = result.card or card
                _merge_records(combined.changed_cards, [canonical, *result.changed_cards])
                combined.id_map.update(result.id_map)
                if result.board_revision is not None:
                    combined.board_revision = result.board_revision
            primary_id = payload.get("card_id", combined.changed_cards[0]["id"])
            combined.card = next(
                (card for card in combined.changed_cards if card.get("id") == primary_id),
                combined.changed_cards[0],
            )
            return combined
        if event_type == "column_created":
            column = dict(payload["column_data"])
            position = int(payload.get("index", 0))
            return self._create_record(
                "column",
                board_id,
                column,
                event,
                transaction,
                position=position,
            )
        if event_type == "column_updated":
            column = dict(payload["column_data"])
            old_id = payload.get("old_column_id", column["id"])
            result = self._require_accepted(
                self._update_record(
                    "column",
                    board_id,
                    old_id,
                    column,
                    event,
                    transaction,
                )
            )
            affected = payload.get("affected_cards", [])
            if old_id != column["id"] and not result.changed_cards and isinstance(affected, list):
                canonical_id = (
                    result.column.get("id", column["id"])
                    if result.column is not None
                    else column["id"]
                )
                for raw_card in affected:
                    card = dict(raw_card)
                    card["column"] = canonical_id
                    card_result = self._require_accepted(
                        self._update_record(
                            "card",
                            board_id,
                            card["id"],
                            card,
                            event,
                            transaction,
                        )
                    )
                    _merge_records(
                        result.changed_cards,
                        [card_result.card or card, *card_result.changed_cards],
                    )
                    if card_result.board_revision is not None:
                        result.board_revision = card_result.board_revision
            return result
        if event_type == "column_deleted":
            return self._delete_record(
                "column",
                board_id,
                payload["column_id"],
                event,
                transaction,
            )
        if event_type == "column_reordered":
            raw_columns = payload["columns"]
            if not isinstance(raw_columns, list):
                return MutationResult(
                    accepted=False,
                    reason="Column reorder data must be a list",
                )
            combined = MutationResult()
            for position, raw_column in enumerate(raw_columns):
                column = dict(raw_column)
                result = self._require_accepted(
                    self._update_record(
                        "column",
                        board_id,
                        column["id"],
                        column,
                        event,
                        transaction,
                        position=position,
                    )
                )
                canonical = result.column or column
                _merge_records(
                    combined.changed_columns,
                    [canonical, *result.changed_columns],
                )
                if result.board_revision is not None:
                    combined.board_revision = result.board_revision
            primary_id = payload.get("column_id")
            combined.column = next(
                (
                    column
                    for column in combined.changed_columns
                    if column.get("id") == primary_id
                ),
                None,
            )
            return combined
        if event_type == "board_replaced":
            return self._replace_board(event, transaction)
        return MutationResult(
            accepted=False,
            reason=f"Unsupported mutation type: {event_type}",
        )

    def _replace_board(self, event: MutationEvent, transaction: Any) -> MutationResult:
        board_id = event.metadata.board_id
        requested_columns = [dict(item) for item in event.payload["columns"]]
        requested_cards = [dict(item) for item in event.payload["cards"]]
        current = self._read_board(board_id)
        old_columns = {column["id"]: column for column in current.columns}
        old_cards = {card["id"]: card for card in current.cards}
        new_columns = {column["id"]: column for column in requested_columns}
        new_cards = {card["id"]: card for card in requested_cards}
        combined = MutationResult()

        for card_id in old_cards.keys() - new_cards.keys():
            self._require_accepted(
                self._delete_record("card", board_id, card_id, event, transaction)
            )
        for position, column in enumerate(requested_columns):
            if column["id"] in old_columns:
                result = self._update_record(
                    "column",
                    board_id,
                    column["id"],
                    column,
                    event,
                    transaction,
                    position=position,
                )
            else:
                result = self._create_record(
                    "column",
                    board_id,
                    column,
                    event,
                    transaction,
                    position=position,
                )
            result = self._require_accepted(result)
            _merge_records(
                combined.changed_columns,
                [result.column or column, *result.changed_columns],
            )
            if result.board_revision is not None:
                combined.board_revision = result.board_revision
        for card in requested_cards:
            if card["id"] in old_cards:
                result = self._update_record(
                    "card",
                    board_id,
                    card["id"],
                    card,
                    event,
                    transaction,
                )
            else:
                result = self._create_record(
                    "card",
                    board_id,
                    card,
                    event,
                    transaction,
                )
            result = self._require_accepted(result)
            _merge_records(
                combined.changed_cards,
                [result.card or card, *result.changed_cards],
            )
            combined.id_map.update(result.id_map)
            if result.board_revision is not None:
                combined.board_revision = result.board_revision
        for column_id in old_columns.keys() - new_columns.keys():
            self._require_accepted(
                self._delete_record("column", board_id, column_id, event, transaction)
            )
        return combined

    def _transaction_context(self, events: list[MutationEvent]) -> ContextManager[Any]:
        if self._transaction is None:
            return nullcontext(None)
        return self._transaction(deepcopy(events))

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        owned_event = deepcopy(event)
        try:
            with self._transaction_context([owned_event]) as transaction:
                return self._require_accepted(self._apply(owned_event, transaction))
        except _RejectedCRUD as exc:
            return exc.result

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        if not events:
            return MutationResult()
        board_id = events[0].metadata.board_id
        if any(event.metadata.board_id != board_id for event in events):
            return MutationResult(accepted=False, reason="A batch cannot span multiple boards")
        owned_events = deepcopy(events)
        combined = MutationResult()
        id_map: dict[Any, Any] = {}
        latest_revision: int | str | None = None
        try:
            with self._transaction_context(owned_events) as transaction:
                for original in owned_events:
                    event = _rebase_event(original, id_map)
                    if latest_revision is not None:
                        event.metadata.expected_revision = latest_revision
                    result = self._require_accepted(self._apply(event, transaction))
                    id_map.update(result.id_map)
                    card_records = (
                        ([result.card] if result.card is not None else [])
                        + result.changed_cards
                    )
                    column_records = (
                        ([result.column] if result.column is not None else [])
                        + result.changed_columns
                    )
                    _merge_records(combined.changed_cards, card_records)
                    _merge_records(combined.changed_columns, column_records)
                    if result.board_revision is not None:
                        latest_revision = result.board_revision
                        combined.board_revision = result.board_revision
        except _RejectedCRUD as exc:
            return exc.result
        combined.id_map = id_map
        return combined

    @staticmethod
    def _coerce_changes(
        value: ChangePage | Mapping[str, Any],
    ) -> ChangePage:
        if isinstance(value, ChangePage):
            return deepcopy(value)
        if not isinstance(value, Mapping):
            raise TypeError("changes must return ChangePage or a mapping")
        raw_events = value.get("events", [])
        if not isinstance(raw_events, (list, tuple)):
            raise TypeError("changes result 'events' must be a list")
        events = [
            deepcopy(item)
            if isinstance(item, MutationEvent)
            else MutationEvent.from_mapping(item)
            for item in raw_events
        ]
        return ChangePage(
            events=events,
            board_revision=value.get("board_revision", value.get("revision")),
        )

    def get_changes(
        self,
        board_id: str,
        since_revision: int | str | None,
    ) -> ChangePage:
        if self._changes is not None:
            return self._coerce_changes(self._changes(board_id, since_revision))
        current = self._read_board(board_id).board_revision
        if (
            current is not None
            and since_revision is not None
            and str(current) != str(since_revision)
        ):
            changed = MutationEvent(
                "board_changed",
                {},
                EventMetadata(
                    board_id=board_id,
                    expected_revision=since_revision,
                    source="crud_poll",
                ),
            )
            return ChangePage([changed], current)
        return ChangePage([], current if current is not None else since_revision)
