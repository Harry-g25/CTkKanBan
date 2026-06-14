"""Typed contracts shared by boards, persistence adapters, and applications."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping
from uuid import uuid4

PersistenceState = Literal[
    "idle",
    "loading",
    "saving",
    "saved",
    "offline",
    "retrying",
    "conflict",
    "error",
]


@dataclass(slots=True)
class EventMetadata:
    """Trace and concurrency metadata attached to every durable mutation."""

    board_id: str = "default"
    actor_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    transaction_id: str = field(default_factory=lambda: str(uuid4()))
    expected_revision: int | str | None = None
    source: str = "api"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class MutationEvent:
    """Operation-first persistence event.

    ``payload`` contains only records affected by the operation. Full board
    snapshots are intentionally excluded so adapters can issue focused writes.
    """

    type: str
    payload: dict[str, Any]
    metadata: EventMetadata = field(default_factory=EventMetadata)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload, **asdict(self.metadata)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MutationEvent":
        metadata = EventMetadata(
            board_id=str(value.get("board_id", "default")),
            actor_id=value.get("actor_id"),
            event_id=str(value.get("event_id") or uuid4()),
            transaction_id=str(value.get("transaction_id") or uuid4()),
            expected_revision=value.get("expected_revision"),
            source=str(value.get("source", "api")),
            timestamp=str(value.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        )
        payload = value.get("payload")
        if payload is None:
            metadata_keys = set(asdict(metadata)) | {"type"}
            payload = {key: item for key, item in value.items() if key not in metadata_keys}
        return cls(type=str(value["type"]), payload=dict(payload), metadata=metadata)


@dataclass(slots=True)
class ConflictDetails:
    """Optimistic-concurrency information returned by an adapter."""

    expected_revision: int | str | None
    actual_revision: int | str | None
    server_data: dict[str, Any] | None = None
    message: str = "The board changed in storage"


@dataclass(slots=True)
class MutationResult:
    """Canonical result returned by callbacks and data sources."""

    accepted: bool = True
    reason: str | None = None
    card: dict[str, Any] | None = None
    column: dict[str, Any] | None = None
    changed_cards: list[dict[str, Any]] = field(default_factory=list)
    changed_columns: list[dict[str, Any]] = field(default_factory=list)
    id_map: dict[Any, Any] = field(default_factory=dict)
    board_revision: int | str | None = None
    conflict: ConflictDetails | None = None
    retryable: bool = False

    @property
    def cancelled(self) -> bool:
        return not self.accepted


@dataclass(slots=True)
class CardQuery:
    """Server-query request used for paging, search, filters, and sorting."""

    column_id: Any | None = None
    search: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    sort_key: str = "manual"
    reverse: bool = False
    offset: int = 0
    limit: int = 100
    completion_field: str = "completed"
    completed_columns: tuple[Any, ...] = ()
    timezone_name: str = "UTC"


@dataclass(slots=True)
class CardPage:
    """One page of cards plus totals for lazy column rendering."""

    cards: list[dict[str, Any]]
    total: int
    offset: int = 0
    limit: int = 100
    column_totals: dict[Any, int] = field(default_factory=dict)
    board_revision: int | str | None = None

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.cards) < self.total


@dataclass(slots=True)
class BoardLoadResult:
    """Initial board payload returned by a data source."""

    columns: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    column_totals: dict[Any, int] = field(default_factory=dict)
    board_revision: int | str | None = None
    has_more: bool = False


@dataclass(slots=True)
class ChangePage:
    """Durable operations that occurred after a known revision."""

    events: list[MutationEvent]
    board_revision: int | str | None = None


def coerce_mutation_result(value: Any) -> MutationResult:
    """Normalize legacy callback values and modern typed results."""

    if isinstance(value, MutationResult):
        return value
    if value is False:
        return MutationResult(accepted=False, reason="Action cancelled by callback")
    if value is None or value is True:
        return MutationResult()
    if isinstance(value, Mapping):
        conflict_value = value.get("conflict")
        conflict = conflict_value if isinstance(conflict_value, ConflictDetails) else None
        if isinstance(conflict_value, Mapping):
            conflict = ConflictDetails(
                expected_revision=conflict_value.get("expected_revision"),
                actual_revision=conflict_value.get("actual_revision"),
                server_data=conflict_value.get("server_data"),
                message=str(conflict_value.get("message") or "The board changed in storage"),
            )
        accepted = not bool(value.get("cancel", False)) and bool(value.get("accepted", True))
        return MutationResult(
            accepted=accepted,
            reason=str(value.get("reason")) if value.get("reason") else None,
            card=dict(value["card"]) if isinstance(value.get("card"), Mapping) else None,
            column=dict(value["column"]) if isinstance(value.get("column"), Mapping) else None,
            changed_cards=[dict(item) for item in value.get("changed_cards", [])],
            changed_columns=[dict(item) for item in value.get("changed_columns", [])],
            id_map=dict(value.get("id_map", {})),
            board_revision=value.get("board_revision"),
            conflict=conflict,
            retryable=bool(value.get("retryable", False)),
        )
    return MutationResult()
