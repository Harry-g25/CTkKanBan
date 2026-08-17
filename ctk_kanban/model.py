"""Small, UI-independent data model for a Kanban board.

The model deliberately owns only board data and manual ordering.  It has no
knowledge of Tk, persistence, callbacks, filtering, or rendering.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, TypedDict

BoardId = str | int
CARD_PRIORITIES = ("", "Low", "Medium", "High", "Critical")


class ColumnRecord(TypedDict):
    """Serializable shape returned for a board column."""

    id: BoardId
    title: str


class CardRecord(TypedDict):
    """Serializable shape returned for a board card."""

    id: BoardId
    column: BoardId
    title: str
    description: str
    priority: str
    tags: list[str]


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
    """A card and the column that currently contains it."""

    id: BoardId
    column: BoardId
    title: str
    description: str = ""
    priority: str = ""
    tags: tuple[str, ...] = ()

    @classmethod
    def from_definition(cls, definition: Card | Mapping[str, Any]) -> Card:
        """Validate and normalize a typed or mapping card definition."""

        return BoardModel._coerce_card(definition)


ColumnInput = Column | Mapping[str, Any]
CardInput = Card | Mapping[str, Any]


class BoardModel:
    """Mutable Kanban state with predictable, manual ordering.

    Input records may be :class:`Column`/:class:`Card` instances or mappings.
    Card mappings accept ``column`` and the alternate spelling ``column_id``.
    Returned records are fresh dictionaries, so callers cannot mutate internal
    model state accidentally.
    """

    def __init__(
        self,
        columns: Iterable[ColumnInput] = (),
        cards: Iterable[CardInput] = (),
    ) -> None:
        self._columns: dict[BoardId, Column] = {}
        self._column_order: list[BoardId] = []
        self._cards: dict[BoardId, Card] = {}
        self._card_order: dict[BoardId, list[BoardId]] = {}
        self._replace(columns, cards)

    def snapshot(self) -> BoardSnapshot:
        """Return a detached, serialisable representation of the board."""

        return {
            "columns": self.get_columns(),
            "cards": self.get_cards(),
        }

    def load(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        columns: Iterable[ColumnInput] | None = None,
        cards: Iterable[CardInput] | None = None,
    ) -> None:
        """Atomically replace the board from a snapshot or explicit iterables.

        ``load(snapshot)`` is the natural inverse of :meth:`snapshot`.
        ``load(columns=..., cards=...)`` is also supported for convenience.
        If validation fails, the existing board is left unchanged.
        """

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
        """Return one detached card record."""

        return self._card_dict(self._require_card(card_id))

    def get_cards(self, column_id: BoardId | None = None) -> list[CardRecord]:
        """Return cards in manual order, optionally for one column."""

        if column_id is not None:
            self._require_column(column_id)
            ids = self._card_order[column_id]
        else:
            ids = [
                card_id
                for current_column_id in self._column_order
                for card_id in self._card_order[current_column_id]
            ]
        return [self._card_dict(self._cards[card_id]) for card_id in ids]

    def get_columns(self) -> list[ColumnRecord]:
        """Return columns in manual order as detached records."""

        return [self._column_dict(self._columns[column_id]) for column_id in self._column_order]

    def add_card(self, card: CardInput, *, index: int | None = None) -> CardRecord:
        """Add a card at ``index`` in its column, or append it."""

        value = self._coerce_card(card)
        self._ensure_new_id(value.id, self._cards, "card")
        self._require_column(value.column)
        position = self._position(index, len(self._card_order[value.column]))

        self._cards[value.id] = value
        self._card_order[value.column].insert(position, value.id)
        return self._card_dict(value)

    def update_card(
        self,
        card_id: BoardId,
        updates: Mapping[str, Any] | None = None,
        **changes: Any,
    ) -> CardRecord:
        """Update editable card fields, optionally moving it to a column."""

        values = self._merge_changes(updates, changes)
        allowed = {"title", "description", "priority", "tags", "column", "column_id"}
        self._reject_unknown_fields(values, allowed, "card")
        current = self._require_card(card_id)

        if "column" in values and "column_id" in values and values["column"] != values["column_id"]:
            raise BoardModelError("column and column_id must refer to the same column")
        column_id = values.get("column", values.get("column_id", current.column))
        self._validate_id(column_id, "column")
        self._require_column(column_id)

        title = values.get("title", current.title)
        self._validate_title(title, "card")
        description = values.get("description", current.description)
        priority = self._coerce_priority(values.get("priority", current.priority))
        self._validate_text(description, "card description")
        title = title.strip()
        description = description.strip()
        tags = self._coerce_tags(values.get("tags", current.tags))

        updated = replace(
            current,
            column=column_id,
            title=title,
            description=description,
            priority=priority,
            tags=tags,
        )
        if column_id != current.column:
            self._card_order[current.column].remove(card_id)
            self._card_order[column_id].append(card_id)
        self._cards[card_id] = updated
        return self._card_dict(updated)

    def delete_card(self, card_id: BoardId) -> CardRecord:
        """Delete and return a detached copy of a card."""

        card = self._require_card(card_id)
        self._card_order[card.column].remove(card_id)
        del self._cards[card_id]
        return self._card_dict(card)

    def move_card(
        self,
        card_id: BoardId,
        column_id: BoardId,
        index: int | None = None,
    ) -> CardRecord:
        """Move a card to a column and insertion index, appending by default."""

        card = self._require_card(card_id)
        self._require_column(column_id)
        target_size = len(self._card_order[column_id])
        if card.column == column_id:
            target_size -= 1
        position = self._position(index, target_size)

        self._card_order[card.column].remove(card_id)
        moved = replace(card, column=column_id)
        self._cards[card_id] = moved
        self._card_order[column_id].insert(position, card_id)
        return self._card_dict(moved)

    def reorder_card(self, card_id: BoardId, index: int) -> CardRecord:
        """Move a card to another position within its current column."""

        card = self._require_card(card_id)
        return self.move_card(card_id, card.column, index)

    def add_column(self, column: ColumnInput, *, index: int | None = None) -> ColumnRecord:
        """Add a column at ``index``, or append it."""

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
        """Rename a column.

        A title string may be passed directly, or supplied in a mapping/keyword.
        """

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

    def delete_column(
        self,
        column_id: BoardId,
        *,
        delete_cards: bool = False,
    ) -> ColumnRecord:
        """Delete a column.

        Non-empty columns are protected unless ``delete_cards=True`` is
        explicitly requested.
        """

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
        """Move a column to a new manual position."""

        column = self._require_column(column_id)
        position = self._position(index, len(self._column_order) - 1)
        self._column_order.remove(column_id)
        self._column_order.insert(position, column_id)
        return self._column_dict(column)

    def clear(self) -> None:
        """Remove all columns and cards."""

        self._columns.clear()
        self._column_order.clear()
        self._cards.clear()
        self._card_order.clear()

    def _replace(
        self,
        columns: Iterable[ColumnInput],
        cards: Iterable[CardInput],
    ) -> None:
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

        new_cards: dict[BoardId, Card] = {}
        try:
            for raw_card in cards:
                card = self._coerce_card(raw_card)
                self._ensure_new_id(card.id, new_cards, "card")
                if card.column not in new_columns:
                    raise BoardModelError(f"unknown column ID: {card.column!r}")
                new_cards[card.id] = card
                new_card_order[card.column].append(card.id)
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
    def _coerce_card(cls, value: CardInput) -> Card:
        if isinstance(value, Card):
            priority = cls._coerce_priority(value.priority)
            tags = cls._coerce_tags(value.tags)
            card = value
            if priority != value.priority or tags != value.tags:
                card = replace(value, priority=priority, tags=tags)
        elif isinstance(value, Mapping):
            cls._reject_unknown_fields(
                value,
                {"id", "column", "column_id", "title", "description", "priority", "tags"},
                "card",
            )
            try:
                if (
                    "column" in value
                    and "column_id" in value
                    and value["column"] != value["column_id"]
                ):
                    raise BoardModelError("column and column_id must refer to the same column")
                column_id = value["column_id"] if "column_id" in value else value["column"]
                card = Card(
                    id=value["id"],
                    column=column_id,
                    title=value["title"],
                    description=value.get("description", ""),
                    priority=cls._coerce_priority(value.get("priority", "")),
                    tags=cls._coerce_tags(value.get("tags", ())),
                )
            except KeyError as exc:
                raise BoardModelError(f"card is missing {exc.args[0]!r}") from exc
        else:
            raise BoardModelError("card must be a Card or mapping")

        cls._validate_id(card.id, "card")
        cls._validate_id(card.column, "column")
        cls._validate_title(card.title, "card")
        cls._validate_text(card.description, "card description")
        title = card.title.strip()
        description = card.description.strip()
        if title == card.title and description == card.description:
            return card
        return replace(card, title=title, description=description)

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
    def _validate_text(value: object, field: str) -> None:
        if not isinstance(value, str):
            raise BoardModelError(f"{field} must be a string")

    @staticmethod
    def _coerce_tags(value: object) -> tuple[str, ...]:
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise BoardModelError("card tags must be an iterable of strings")
        raw_tags = tuple(value)
        if not all(isinstance(tag, str) for tag in raw_tags):
            raise BoardModelError("card tags must contain only strings")
        tags = tuple(tag.strip() for tag in raw_tags)
        if any(not tag for tag in tags):
            raise BoardModelError("card tags must not be blank")
        if any("," in tag for tag in tags):
            raise BoardModelError("card tags must not contain commas")
        return tags

    @staticmethod
    def _coerce_priority(value: object) -> str:
        if not isinstance(value, str) or value not in CARD_PRIORITIES:
            choices = ", ".join(name or "empty" for name in CARD_PRIORITIES)
            raise BoardModelError(f"card priority must be one of: {choices}")
        return value

    @staticmethod
    def _ensure_new_id(
        value: BoardId,
        records: Mapping[BoardId, object],
        kind: str,
    ) -> None:
        if value in records:
            raise BoardModelError(f"duplicate {kind} ID: {value!r}")

    def _require_card(self, card_id: BoardId) -> Card:
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
    def _card_dict(card: Card) -> CardRecord:
        return {
            "id": card.id,
            "column": card.column,
            "title": card.title,
            "description": card.description,
            "priority": card.priority,
            "tags": list(card.tags),
        }

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
