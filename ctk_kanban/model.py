"""Small, UI-independent data model for a configurable Kanban board."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, NamedTuple, TypeAlias, TypedDict, cast

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


_ATOMIC_TYPES = (type(None), bool, int, float, complex, str, bytes)
_NORMALIZE_FALLBACK = object()
_STRUCTURAL_CARD_KEYS = frozenset(("id", "column", "column_id"))
_NO_DEFAULT = object()


class _FieldPlan(NamedTuple):
    definition: dict[str, Any]
    key: str
    kind: int
    required: bool
    default: Any
    options: Any
    minimum: Any
    maximum: Any


def _detach(value: Any, memo: dict[int, Any] | None = None) -> Any:
    """Copy common JSON-like board data without ``deepcopy`` dispatch overhead.

    Cards overwhelmingly contain dictionaries, lists, tuples, and immutable
    scalar values. Handling those exact built-ins directly is several times
    faster while preserving detached public results, shared references, and
    cyclic containers. Custom objects still use ``deepcopy`` as before.
    """

    value_type = type(value)
    if value_type in _ATOMIC_TYPES:
        return value
    if memo is None:
        memo = {}
    identity = id(value)
    existing = memo.get(identity)
    if existing is not None:
        return existing
    if value_type is list:
        copied_list: list[Any] = []
        memo[identity] = copied_list
        copied_list.extend(_detach(item, memo) for item in value)
        return copied_list
    if value_type is dict:
        copied_dict: dict[Any, Any] = {}
        memo[identity] = copied_dict
        copied_dict.update(
            (_detach(key, memo), _detach(item, memo)) for key, item in value.items()
        )
        return copied_dict
    if value_type is tuple:
        # A temporary list lets recursive values resolve through ``memo``.
        placeholder: list[Any] = []
        memo[identity] = placeholder
        copied_tuple = tuple(_detach(item, memo) for item in value)
        memo[identity] = copied_tuple
        return copied_tuple
    if value_type is set:
        copied_set: set[Any] = set()
        memo[identity] = copied_set
        copied_set.update(_detach(item, memo) for item in value)
        return copied_set
    if value_type is frozenset:
        copied_frozen = frozenset(_detach(item, memo) for item in value)
        memo[identity] = copied_frozen
        return copied_frozen
    return deepcopy(value, memo)


def _detach_card(card: CardRecord) -> CardRecord:
    # Avoid recursive function dispatch for the overwhelmingly common card
    # shape (scalar values plus flat tag/owner lists). Fall back to the fully
    # recursive copier only when a value can itself contain mutable objects.
    result = card.copy()
    for key, value in card.items():
        value_type = type(value)
        if value_type in _ATOMIC_TYPES:
            continue
        if value_type is list:
            copied_list = value.copy()
            for index, item in enumerate(value):
                if type(item) not in _ATOMIC_TYPES:
                    copied_list[index] = _detach(item)
            result[key] = copied_list
        elif value_type is tuple:
            if any(type(item) not in _ATOMIC_TYPES for item in value):
                result[key] = _detach(value)
        else:
            result[key] = _detach(value)
    return result


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
        self._revision = 0
        try:
            self._fields = normalize_fields(fields)
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        (
            self._title_key,
            self._field_keys,
            self._has_field_validators,
            self._field_plans,
        ) = self._compile_fields(self._fields)
        self._replace(columns, cards)

    def snapshot(self) -> BoardSnapshot:
        """Return a detached, serialisable representation of the board."""

        return {"columns": self.get_columns(), "cards": self.get_cards()}

    def _card_records(self, column_id: BoardId | None = None) -> list[CardRecord]:
        """Return internal card records for trusted package rendering code.

        Public accessors remain detached.  Keeping this package-private view
        avoids deep-copying a large board merely to paint it.
        """

        if column_id is not None:
            self._require_column(column_id)
            ids = self._card_order[column_id]
        else:
            ids = [
                card_id
                for current_column_id in self._column_order
                for card_id in self._card_order[current_column_id]
            ]
        return [self._cards[card_id] for card_id in ids]

    def _card_count(self) -> int:
        return len(self._cards)

    def get_fields(self) -> list[dict[str, Any]]:
        """Return detached field definitions in editor/render order."""

        return cast(list[dict[str, Any]], _detach(list(self._fields)))

    def set_fields(self, fields: Iterable[FieldInput]) -> None:
        """Atomically replace the card schema and revalidate existing cards."""

        try:
            candidate_fields = normalize_fields(fields)
            (
                title_key,
                field_keys,
                has_validators,
                field_plans,
            ) = self._compile_fields(candidate_fields)
            candidate_cards = {
                card_id: self._normalize_card(
                    card,
                    candidate_fields,
                    title_key=title_key,
                    field_keys=field_keys,
                    has_validators=has_validators,
                    field_plans=field_plans,
                )
                for card_id, card in self._cards.items()
            }
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        if self._safe_equal(candidate_fields, self._fields) and self._safe_equal(
            candidate_cards, self._cards
        ):
            return
        self._fields = candidate_fields
        self._title_key = title_key
        self._field_keys = field_keys
        self._has_field_validators = has_validators
        self._field_plans = field_plans
        self._cards = candidate_cards
        self._revision += 1

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
        return _detach_card(self._require_card(card_id))

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
        return [_detach_card(self._cards[card_id]) for card_id in ids]

    def get_columns(self) -> list[ColumnRecord]:
        return [self._column_dict(self._columns[column_id]) for column_id in self._column_order]

    def add_card(self, card: CardInput, *, index: int | None = None) -> CardRecord:
        try:
            value = self._normalize_card(
                card,
                self._fields,
                title_key=self._title_key,
                field_keys=self._field_keys,
                has_validators=self._has_field_validators,
                field_plans=self._field_plans,
            )
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        self._ensure_new_id(value["id"], self._cards, "card")
        self._require_column(value["column"])
        position = self._position(index, len(self._card_order[value["column"]]))
        self._cards[value["id"]] = value
        self._card_order[value["column"]].insert(position, value["id"])
        self._revision += 1
        return _detach_card(value)

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

        # Normalization creates fresh mutable field values, so a shallow
        # candidate is sufficient and avoids copying unchanged rich data twice.
        candidate = current.copy()
        candidate.update({key: value for key, value in values.items() if key != "column_id"})
        candidate["column"] = column_id
        try:
            updated = self._normalize_card(
                candidate,
                self._fields,
                title_key=self._title_key,
                field_keys=self._field_keys,
                has_validators=self._has_field_validators,
                field_plans=self._field_plans,
            )
        except (TypeError, ValueError) as exc:
            raise BoardModelError(str(exc)) from exc
        if self._safe_equal(updated, current):
            return _detach_card(current)
        if column_id != current["column"]:
            self._card_order[current["column"]].remove(card_id)
            self._card_order[column_id].append(card_id)
        self._cards[card_id] = updated
        self._revision += 1
        return _detach_card(updated)

    def delete_card(self, card_id: BoardId) -> CardRecord:
        card = self._require_card(card_id)
        self._card_order[card["column"]].remove(card_id)
        del self._cards[card_id]
        self._revision += 1
        return _detach_card(card)

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
        if card["column"] == column_id:
            current_position = self._card_order[column_id].index(card_id)
            if position == current_position:
                return _detach_card(card)
        self._card_order[card["column"]].remove(card_id)
        # Moving changes only the structural column key. Keep all other
        # already-normalized values and detach once for the public return.
        moved = card.copy()
        moved["column"] = column_id
        self._cards[card_id] = moved
        self._card_order[column_id].insert(position, card_id)
        self._revision += 1
        return _detach_card(moved)

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
        self._revision += 1
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
        if updated == current:
            return self._column_dict(current)
        self._columns[column_id] = updated
        self._revision += 1
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
        self._revision += 1
        return self._column_dict(column)

    def move_column(self, column_id: BoardId, index: int) -> ColumnRecord:
        column = self._require_column(column_id)
        position = self._position(index, len(self._column_order) - 1)
        current_position = self._column_order.index(column_id)
        if position == current_position:
            return self._column_dict(column)
        self._column_order.remove(column_id)
        self._column_order.insert(position, column_id)
        self._revision += 1
        return self._column_dict(column)

    def clear(self) -> None:
        if not self._columns and not self._cards:
            return
        self._columns.clear()
        self._column_order.clear()
        self._cards.clear()
        self._card_order.clear()
        self._revision += 1

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
        normalize_card = self._normalize_card
        fields = self._fields
        title_key = self._title_key
        field_keys = self._field_keys
        has_validators = self._has_field_validators
        field_plans = self._field_plans
        try:
            for raw_card in cards:
                try:
                    card = normalize_card(
                        raw_card,
                        fields,
                        title_key=title_key,
                        field_keys=field_keys,
                        has_validators=has_validators,
                        field_plans=field_plans,
                    )
                except (TypeError, ValueError) as exc:
                    raise BoardModelError(str(exc)) from exc
                card_id = card["id"]
                if card_id in new_cards:
                    raise BoardModelError(f"duplicate card ID: {card_id!r}")
                column_id = card["column"]
                if column_id not in new_columns:
                    raise BoardModelError(f"unknown column ID: {column_id!r}")
                new_cards[card_id] = card
                new_card_order[column_id].append(card_id)
        except TypeError as exc:
            raise BoardModelError("cards must be an iterable of card records") from exc

        self._columns = new_columns
        self._column_order = new_column_order
        self._cards = new_cards
        self._card_order = new_card_order
        self._revision += 1

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
        *,
        title_key: str | None = None,
        field_keys: frozenset[str] | None = None,
        has_validators: bool = True,
        field_plans: tuple[_FieldPlan, ...] | None = None,
    ) -> CardRecord:
        # Mapping dictionaries are the overwhelmingly common bulk-load input.
        # Check their exact type first so every card avoids an unnecessary
        # dataclass instance check.
        if type(value) is dict:
            source: Mapping[str, Any] = value
        elif isinstance(value, Card):
            source = {
                "id": value.id,
                "column": value.column,
                "title": value.title,
                "description": value.description,
                "priority": value.priority,
                "tags": value.tags,
            }
        elif isinstance(value, Mapping):
            source = value
        else:
            raise BoardModelError("card must be a Card or mapping")

        has_column = "column" in source
        has_column_id = "column_id" in source
        if has_column and has_column_id and source["column"] != source["column_id"]:
            raise BoardModelError("column and column_id must refer to the same column")
        if title_key is None:
            title_key = next(field["key"] for field in fields if field["card_role"] == "title")
        try:
            card_id = source["id"]
            column_id = source["column_id"] if has_column_id else source["column"]
            title = source[title_key]
        except KeyError as exc:
            raise BoardModelError(f"card is missing {exc.args[0]!r}") from exc
        card_id_type = type(card_id)
        if card_id_type is str:
            if not card_id.strip():
                raise BoardModelError("card ID must not be blank")
        elif card_id_type is not int:
            raise BoardModelError("card ID must be a string or integer")
        column_id_type = type(column_id)
        if column_id_type is str:
            if not column_id.strip():
                raise BoardModelError("column ID must not be blank")
        elif column_id_type is not int:
            raise BoardModelError("column ID must be a string or integer")
        if not isinstance(title, str):
            raise BoardModelError("card title must be a nonblank string")
        normalized_title = title.strip()
        if not normalized_title:
            raise BoardModelError("card title must be a nonblank string")

        record: CardRecord = {"id": card_id, "column": column_id}
        if field_keys is None:
            field_keys = frozenset(field["key"] for field in fields)
        if field_plans is None:
            field_plans = cls._build_field_plans(fields)
        mutable_context = {**source, "column": column_id} if has_validators else None
        context: Mapping[str, Any] = source if mutable_context is None else mutable_context
        # Account for structural fields while consuming configured fields.
        # Most cards contain no extension keys, so the count lets that hot path
        # skip a second complete iteration over the source dictionary.
        consumed_count = 1 + int(has_column) + int(has_column_id)
        for plan in field_plans:
            (
                field,
                key,
                kind,
                required,
                default,
                options,
                minimum,
                maximum,
            ) = plan
            if key in source:
                raw = source[key]
                consumed_count += 1
            elif default is not _NO_DEFAULT:
                raw = _detach(default)
            elif required:
                raw = None
            else:
                continue
            normalized: Any = _NORMALIZE_FALLBACK
            if kind:
                if kind == 1 and type(raw) is str:
                    candidate = normalized_title if key == title_key else raw.strip()
                    if candidate or not required:
                        normalized = candidate
                elif kind == 2 and type(raw) is int:
                    if (minimum is _NO_DEFAULT or raw >= minimum) and (
                        maximum is _NO_DEFAULT or raw <= maximum
                    ):
                        normalized = raw
                elif kind == 3 and type(raw) is float:
                    if (minimum is _NO_DEFAULT or raw >= minimum) and (
                        maximum is _NO_DEFAULT or raw <= maximum
                    ):
                        normalized = raw
                elif kind == 4 and type(raw) is bool:
                    normalized = raw
                elif kind == 5 and type(raw) in _ATOMIC_TYPES:
                    if (
                        (raw not in (None, "") or not required)
                        and (not options or raw in options)
                    ):
                        normalized = raw
                elif (kind == 6 or kind == 7) and type(raw) is list:
                    items: list[str] = []
                    valid = True
                    for item in raw:
                        if type(item) is not str:
                            valid = False
                            break
                        item = item.strip()
                        if (
                            not item
                            or (kind == 6 and "," in item)
                            or (kind == 7 and options and item not in options)
                        ):
                            valid = False
                            break
                        if item not in items:
                            items.append(item)
                    if valid and (items or not required):
                        normalized = items
            if normalized is _NORMALIZE_FALLBACK:
                normalized = normalize_field_value(field, raw, context)
            record[key] = normalized
            if mutable_context is not None:
                mutable_context[key] = normalized

        if title_key != "title" and "title" in source and "title" not in field_keys:
            consumed_count += 1
        if consumed_count != len(source):
            for key, item in source.items():
                if (
                    key not in field_keys
                    and key not in _STRUCTURAL_CARD_KEYS
                    and not (title_key != "title" and key == "title")
                ):
                    record[key] = _detach(item)
        return record

    @staticmethod
    def _compile_fields(
        fields: tuple[dict[str, Any], ...],
    ) -> tuple[str, frozenset[str], bool, tuple[_FieldPlan, ...]]:
        return (
            next(field["key"] for field in fields if field["card_role"] == "title"),
            frozenset(field["key"] for field in fields),
            any(field.get("validator") is not None for field in fields),
            BoardModel._build_field_plans(fields),
        )

    @staticmethod
    def _build_field_plans(
        fields: tuple[dict[str, Any], ...],
    ) -> tuple[_FieldPlan, ...]:
        kinds = {
            "text": 1,
            "textarea": 1,
            "integer": 2,
            "number": 3,
            "checkbox": 4,
            "select": 5,
            "tags": 6,
            "multiselect": 7,
        }
        plans: list[_FieldPlan] = []
        for field in fields:
            kind = kinds.get(field["type"], 0)
            if field.get("validator") is not None or (
                kind == 1 and ("min_length" in field or "max_length" in field)
            ):
                kind = 0
            plans.append(
                _FieldPlan(
                    definition=field,
                    key=field["key"],
                    kind=kind,
                    required=bool(field.get("required")),
                    default=field.get("default", _NO_DEFAULT),
                    options=field.get("options", ()),
                    minimum=field.get("min", _NO_DEFAULT),
                    maximum=field.get("max", _NO_DEFAULT),
                )
            )
        return tuple(plans)

    @staticmethod
    def _validate_id(value: object, kind: str) -> None:
        value_type = type(value)
        if value_type is str:
            if not cast(str, value).strip():
                raise BoardModelError(f"{kind} ID must not be blank")
        elif value_type is not int:
            raise BoardModelError(f"{kind} ID must be a string or integer")

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
    def _safe_equal(left: Any, right: Any) -> bool:
        """Compare user data without assuming custom values return a bool."""

        try:
            result = left == right
        except (TypeError, ValueError):
            return False
        return result if isinstance(result, bool) else False

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
