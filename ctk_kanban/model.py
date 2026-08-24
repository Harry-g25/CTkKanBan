"""Small, UI-independent data model for a configurable Kanban board."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, TypeAlias, TypedDict, cast

from .fields import FieldInput, normalize_field_value, normalize_fields

BoardId = str | int
CARD_PRIORITIES = ("", "Low", "Medium", "High", "Critical")


class ColumnRecord(TypedDict):
    """Serializable shape returned for a board column."""

    id: BoardId
    title: str


CardRecord: TypeAlias = dict[str, Any]


class BoardSnapshot(TypedDict):
    """Detached, serializable board state used by persistence adapters."""

    columns: list[ColumnRecord]
    cards: list[CardRecord]


class BoardModelError(ValueError):
    """Raised when board data or a requested model operation is invalid."""


@dataclass(frozen=True, slots=True)
class Column:
    """A board column."""

    id: BoardId
    title: str

    @classmethod
    def from_definition(cls, definition: Column | Mapping[str, Any]) -> Column:
        """Validate and normalize a typed or mapping column definition."""

        return BoardModel._coerce_column(definition)


@dataclass(frozen=True, slots=True)
class Card:
    """The backwards-compatible typed shape for the four default fields.

    Mapping card definitions may contain any number of additional configured
    data points. The dataclass intentionally remains compact for callers that
    use the default schema.
    """

    id: BoardId
    column: BoardId
    title: str
    description: str = ""
    priority: str = ""
    tags: tuple[str, ...] = ()

    @classmethod
    def from_definition(cls, definition: Card | Mapping[str, Any]) -> Card:
        """Validate and normalize the default typed card fields."""

        if isinstance(definition, cls):
            record = BoardModel._normalize_card(definition, normalize_fields())
            if (
                record["title"] == definition.title
                and record["description"] == definition.description
                and record["priority"] == definition.priority
                and tuple(record["tags"]) == definition.tags
            ):
                return definition
        record = BoardModel._normalize_card(definition, normalize_fields())
        return cls(
            id=record["id"],
            column=record["column"],
            title=record["title"],
            description=record["description"],
            priority=record["priority"],
            tags=tuple(record["tags"]),
        )


ColumnInput = Column | Mapping[str, Any]
CardInput = Card | Mapping[str, Any]


class BoardModel:
    """Mutable Kanban state with schema-aware card values and manual ordering.

    ``id`` and ``column`` are reserved structural card keys. Every other key is
    retained and round-tripped. Configured fields additionally receive type,
    option, range, required, and custom validation.
    """

    def __init__(
        self,
        columns: Iterable[ColumnInput] = (),
        cards: Iterable[CardInput] = (),
        *,
        fields: Iterable[FieldInput] | None = None,
    ) -> None:
        self._columns: dict[BoardId, Column] = {}
        self._column_order: list[BoardId] = []
        self._cards: dict[BoardId, CardRecord] = {}
        self._card_order: dict[BoardId, list[BoardId]] = {}
        try:
            self._fields = normalize_fields(fields)
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        self._replace(columns, cards)

    def snapshot(self) -> BoardSnapshot:
        """Return a detached, serialisable representation of the board."""

        return {"columns": self.get_columns(), "cards": self.get_cards()}

    def get_fields(self) -> list[dict[str, Any]]:
        """Return detached field definitions in editor/render order."""

        return deepcopy(list(self._fields))

    def set_fields(self, fields: Iterable[FieldInput]) -> None:
        """Atomically replace the card schema and revalidate existing cards."""

        try:
            candidate_fields = normalize_fields(fields)
            candidate_cards = {
                card_id: self._normalize_card(card, candidate_fields)
                for card_id, card in self._cards.items()
            }
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        self._fields = candidate_fields
        self._cards = candidate_cards

    def load(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        columns: Iterable[ColumnInput] | None = None,
        cards: Iterable[CardInput] | None = None,
    ) -> None:
        """Atomically replace the board from a snapshot or explicit iterables."""

        if data is not None:
            if columns is not None or cards is not None:
                raise BoardModelError("pass either a snapshot or columns/cards, not both")
            if not isinstance(data, Mapping):
                raise BoardModelError("board snapshot must be a mapping")
            self._reject_unknown_fields(data, {"columns", "cards"}, "board")
            missing = {"columns", "cards"} - set(data)
            if missing:
                names = ", ".join(sorted(missing))
                raise BoardModelError(f"board snapshot is missing: {names}")
            columns = data["columns"]
            cards = data["cards"]
            if columns is None or cards is None:
                raise BoardModelError("board columns and cards must be iterables")
        self._replace(columns if columns is not None else (), cards if cards is not None else ())

    def get_card(self, card_id: BoardId) -> CardRecord:
        return deepcopy(self._require_card(card_id))

    def get_cards(self, column_id: BoardId | None = None) -> list[CardRecord]:
        if column_id is not None:
            self._require_column(column_id)
            ids = self._card_order[column_id]
        else:
            ids = [
                card_id
                for current_column_id in self._column_order
                for card_id in self._card_order[current_column_id]
            ]
        return [deepcopy(self._cards[card_id]) for card_id in ids]

    def get_columns(self) -> list[ColumnRecord]:
        return [self._column_dict(self._columns[column_id]) for column_id in self._column_order]

    def add_card(self, card: CardInput, *, index: int | None = None) -> CardRecord:
        try:
            value = self._normalize_card(card, self._fields)
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        self._ensure_new_id(value["id"], self._cards, "card")
        self._require_column(value["column"])
        position = self._position(index, len(self._card_order[value["column"]]))
        self._cards[value["id"]] = value
        self._card_order[value["column"]].insert(position, value["id"])
        return deepcopy(value)

    def update_card(
        self,
        card_id: BoardId,
        updates: Mapping[str, Any] | None = None,
        **changes: Any,
    ) -> CardRecord:
        values = self._merge_changes(updates, changes)
        if "id" in values:
            raise BoardModelError("cannot update card field(s): id")
        current = self._require_card(card_id)
        if "column" in values and "column_id" in values and values["column"] != values["column_id"]:
            raise BoardModelError("column and column_id must refer to the same column")
        raw_column_id = values.get("column", values.get("column_id", current["column"]))
        self._validate_id(raw_column_id, "column")
        column_id = cast(BoardId, raw_column_id)
        self._require_column(column_id)

        candidate = deepcopy(current)
        candidate.update({key: value for key, value in values.items() if key != "column_id"})
        candidate["column"] = column_id
        try:
            updated = self._normalize_card(candidate, self._fields)
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        if column_id != current["column"]:
            self._card_order[current["column"]].remove(card_id)
            self._card_order[column_id].append(card_id)
        self._cards[card_id] = updated
        return deepcopy(updated)

    def delete_card(self, card_id: BoardId) -> CardRecord:
        card = self._require_card(card_id)
        self._card_order[card["column"]].remove(card_id)
        del self._cards[card_id]
        return deepcopy(card)

    def move_card(
        self,
        card_id: BoardId,
        column_id: BoardId,
        index: int | None = None,
    ) -> CardRecord:
        card = self._require_card(card_id)
        self._require_column(column_id)
        target_size = len(self._card_order[column_id])
        if card["column"] == column_id:
            target_size -= 1
        position = self._position(index, target_size)
        self._card_order[card["column"]].remove(card_id)
        moved = deepcopy(card)
        moved["column"] = column_id
        self._cards[card_id] = moved
        self._card_order[column_id].insert(position, card_id)
        return deepcopy(moved)

    def reorder_card(self, card_id: BoardId, index: int) -> CardRecord:
        card = self._require_card(card_id)
        return self.move_card(card_id, card["column"], index)

    def add_column(self, column: ColumnInput, *, index: int | None = None) -> ColumnRecord:
        value = self._coerce_column(column)
        self._ensure_new_id(value.id, self._columns, "column")
        position = self._position(index, len(self._column_order))
        self._columns[value.id] = value
        self._column_order.insert(position, value.id)
        self._card_order[value.id] = []
        return self._column_dict(value)

    def update_column(
        self,
        column_id: BoardId,
        updates: Mapping[str, Any] | str | None = None,
        **changes: Any,
    ) -> ColumnRecord:
        if isinstance(updates, str):
            values = {"title": updates, **changes}
        else:
            values = self._merge_changes(updates, changes)
        self._reject_unknown_fields(values, {"title"}, "column")
        current = self._require_column(column_id)
        title = values.get("title", current.title)
        self._validate_title(title, "column")
        updated = replace(current, title=title.strip())
        self._columns[column_id] = updated
        return self._column_dict(updated)

    def delete_column(self, column_id: BoardId, *, delete_cards: bool = False) -> ColumnRecord:
        column = self._require_column(column_id)
        card_ids = self._card_order[column_id]
        if card_ids and not delete_cards:
            raise BoardModelError("cannot delete a column that still contains cards")
        for card_id in card_ids:
            del self._cards[card_id]
        del self._card_order[column_id]
        del self._columns[column_id]
        self._column_order.remove(column_id)
        return self._column_dict(column)

    def move_column(self, column_id: BoardId, index: int) -> ColumnRecord:
        column = self._require_column(column_id)
        position = self._position(index, len(self._column_order) - 1)
        self._column_order.remove(column_id)
        self._column_order.insert(position, column_id)
        return self._column_dict(column)

    def clear(self) -> None:
        self._columns.clear()
        self._column_order.clear()
        self._cards.clear()
        self._card_order.clear()

    def _replace(self, columns: Iterable[ColumnInput], cards: Iterable[CardInput]) -> None:
        new_columns: dict[BoardId, Column] = {}
        new_column_order: list[BoardId] = []
        new_card_order: dict[BoardId, list[BoardId]] = {}
        try:
            for raw_column in columns:
                column = self._coerce_column(raw_column)
                self._ensure_new_id(column.id, new_columns, "column")
                new_columns[column.id] = column
                new_column_order.append(column.id)
                new_card_order[column.id] = []
        except TypeError as exc:
            raise BoardModelError("columns must be an iterable of column records") from exc

        new_cards: dict[BoardId, CardRecord] = {}
        try:
            for raw_card in cards:
                try:
                    card = self._normalize_card(raw_card, self._fields)
                except (TypeError, ValueError) as exc:
                    raise BoardModelError(str(exc)) from exc
                self._ensure_new_id(card["id"], new_cards, "card")
                if card["column"] not in new_columns:
                    raise BoardModelError(f"unknown column ID: {card['column']!r}")
                new_cards[card["id"]] = card
                new_card_order[card["column"]].append(card["id"])
        except TypeError as exc:
            raise BoardModelError("cards must be an iterable of card records") from exc

        self._columns = new_columns
        self._column_order = new_column_order
        self._cards = new_cards
        self._card_order = new_card_order

    @classmethod
    def _coerce_column(cls, value: ColumnInput) -> Column:
        if isinstance(value, Column):
            column = value
        elif isinstance(value, Mapping):
            cls._reject_unknown_fields(value, {"id", "title"}, "column")
            try:
                column = Column(id=value["id"], title=value["title"])
            except KeyError as exc:
                raise BoardModelError(f"column is missing {exc.args[0]!r}") from exc
        else:
            raise BoardModelError("column must be a Column or mapping")
        cls._validate_id(column.id, "column")
        cls._validate_title(column.title, "column")
        title = column.title.strip()
        return column if title == column.title else replace(column, title=title)

    @classmethod
    def _normalize_card(
        cls,
        value: CardInput,
        fields: tuple[dict[str, Any], ...],
    ) -> CardRecord:
        if isinstance(value, Card):
            source: dict[str, Any] = {
                "id": value.id,
                "column": value.column,
                "title": value.title,
                "description": value.description,
                "priority": value.priority,
                "tags": value.tags,
            }
        elif isinstance(value, Mapping):
            source = dict(value)
        else:
            raise BoardModelError("card must be a Card or mapping")

        if "column" in source and "column_id" in source and source["column"] != source["column_id"]:
            raise BoardModelError("column and column_id must refer to the same column")
        title_field = next(field for field in fields if field["card_role"] == "title")
        title_key = title_field["key"]
        try:
            card_id = source["id"]
            column_id = source["column_id"] if "column_id" in source else source["column"]
            title = source[title_key]
        except KeyError as exc:
            raise BoardModelError(f"card is missing {exc.args[0]!r}") from exc
        cls._validate_id(card_id, "card")
        cls._validate_id(column_id, "column")
        cls._validate_title(title, "card")

        record: CardRecord = {"id": card_id, "column": column_id}
        field_keys = {field["key"] for field in fields}
        context = {**source, "column": column_id}
        for field in fields:
            key = field["key"]
            if key in source:
                raw = source[key]
            elif "default" in field:
                raw = deepcopy(field["default"])
            elif field.get("required"):
                raw = None
            else:
                continue
            record[key] = normalize_field_value(field, raw, context)
            context[key] = record[key]

        structural_keys = {"id", "column", "column_id"}
        if title_key != "title":
            structural_keys.add("title")
        for key, item in source.items():
            if key not in structural_keys and key not in field_keys:
                record[key] = deepcopy(item)
        return record

    @staticmethod
    def _validate_id(value: object, kind: str) -> None:
        if type(value) not in (str, int):
            raise BoardModelError(f"{kind} ID must be a string or integer")
        if isinstance(value, str) and not value.strip():
            raise BoardModelError(f"{kind} ID must not be blank")

    @staticmethod
    def _validate_title(value: object, kind: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise BoardModelError(f"{kind} title must be a nonblank string")

    @staticmethod
    def _ensure_new_id(value: BoardId, records: Mapping[BoardId, object], kind: str) -> None:
        if value in records:
            raise BoardModelError(f"duplicate {kind} ID: {value!r}")

    def _require_card(self, card_id: BoardId) -> CardRecord:
        self._validate_id(card_id, "card")
        try:
            return self._cards[card_id]
        except KeyError as exc:
            raise BoardModelError(f"unknown card ID: {card_id!r}") from exc

    def _require_column(self, column_id: BoardId) -> Column:
        self._validate_id(column_id, "column")
        try:
            return self._columns[column_id]
        except KeyError as exc:
            raise BoardModelError(f"unknown column ID: {column_id!r}") from exc

    @staticmethod
    def _position(index: int | None, size: int) -> int:
        if index is None:
            return size
        if isinstance(index, bool) or not isinstance(index, int):
            raise BoardModelError("index must be an integer")
        if not 0 <= index <= size:
            raise BoardModelError(f"index must be between 0 and {size}")
        return index

    @staticmethod
    def _merge_changes(
        updates: Mapping[str, Any] | None,
        changes: Mapping[str, Any],
    ) -> dict[str, Any]:
        if updates is not None and not isinstance(updates, Mapping):
            raise BoardModelError("updates must be a mapping")
        values = dict(updates or {})
        values.update(changes)
        return values

    @staticmethod
    def _reject_unknown_fields(values: Mapping[str, Any], allowed: set[str], kind: str) -> None:
        unknown = set(values) - allowed
        if unknown:
            fields = ", ".join(sorted(unknown))
            raise BoardModelError(f"cannot update {kind} field(s): {fields}")

    @staticmethod
    def _column_dict(column: Column) -> ColumnRecord:
        return {"id": column.id, "title": column.title}


__all__ = [
    "BoardModel",
    "BoardModelError",
    "BoardSnapshot",
    "Card",
    "CardRecord",
    "Column",
    "ColumnRecord",
]
