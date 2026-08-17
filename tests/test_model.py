"""Focused tests for the small, Tk-free board model."""

from __future__ import annotations

from datetime import date

import pytest

from ctk_kanban.model import BoardModel, BoardModelError, Card, Column


def make_model() -> BoardModel:
    return BoardModel(
        columns=[Column("todo", "To do"), {"id": "done", "title": "Done"}],
        cards=[
            Card(1, "todo", "First", tags=("small",)),
            {"id": 2, "column": "todo", "title": "Second"},
            {"id": 3, "column_id": "done", "title": "Third"},
        ],
    )


def test_accepts_dataclasses_and_mappings_and_preserves_manual_order() -> None:
    model = make_model()

    assert [column["id"] for column in model.get_columns()] == ["todo", "done"]
    assert [card["id"] for card in model.get_cards()] == [1, 2, 3]
    assert [card["id"] for card in model.get_cards("todo")] == [1, 2]
    assert model.get_card(1)["column"] == "todo"
    assert "column_id" not in model.get_card(1)
    assert model.get_card(1)["tags"] == ["small"]


def test_rejects_invalid_ids_titles_duplicates_and_unknown_columns() -> None:
    with pytest.raises(BoardModelError, match="string or integer"):
        BoardModel(columns=[{"id": None, "title": "Bad"}])
    with pytest.raises(BoardModelError, match="string or integer"):
        BoardModel(
            columns=[Column("todo", "To do")],
            cards=[{"id": None, "column": "todo", "title": "Bad"}],
        )
    with pytest.raises(BoardModelError, match="string or integer"):
        BoardModel(columns=[{"id": [], "title": "Bad"}])
    with pytest.raises(BoardModelError, match="string or integer"):
        BoardModel(columns=[{"id": True, "title": "Bad"}])
    with pytest.raises(BoardModelError, match="must not be blank"):
        BoardModel(columns=[{"id": " ", "title": "Bad"}])
    with pytest.raises(BoardModelError, match="nonblank"):
        BoardModel(columns=[{"id": "todo", "title": "  "}])
    with pytest.raises(BoardModelError, match="duplicate column"):
        BoardModel(columns=[Column("todo", "One"), Column("todo", "Two")])
    with pytest.raises(BoardModelError, match="duplicate card"):
        BoardModel(
            columns=[Column("todo", "To do")],
            cards=[Card(1, "todo", "One"), Card(1, "todo", "Two")],
        )
    with pytest.raises(BoardModelError, match="unknown column"):
        BoardModel(cards=[Card(1, "missing", "Orphan")])
    with pytest.raises(BoardModelError, match="nonblank"):
        BoardModel(columns=[Column("todo", "To do")], cards=[Card(1, "todo", "")])
    with pytest.raises(BoardModelError, match="same column"):
        BoardModel(
            columns=[Column("todo", "To do"), Column("done", "Done")],
            cards=[
                {
                    "id": 1,
                    "column": "todo",
                    "column_id": "done",
                    "title": "Ambiguous",
                }
            ],
        )


def test_editor_facing_values_are_normalized_and_unambiguous() -> None:
    model = BoardModel(
        columns=[{"id": "todo", "title": "  To do  "}],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "  Card  ",
                "description": "  Details  ",
                "priority": "High",
                "tags": [" one ", "two"],
            }
        ],
    )

    assert model.get_columns()[0]["title"] == "To do"
    assert model.get_card(1) == {
        "id": 1,
        "column": "todo",
        "title": "Card",
        "description": "Details",
        "priority": "High",
        "tags": ["one", "two"],
    }
    with pytest.raises(BoardModelError, match="priority"):
        model.update_card(1, priority="None")
    with pytest.raises(BoardModelError, match="commas"):
        model.update_card(1, tags=["ACME, Inc."])
    with pytest.raises(BoardModelError, match="must not be blank"):
        model.update_card(1, tags=[" "])


def test_public_card_round_trips_a_snapshot_record() -> None:
    source = make_model()
    record = source.get_card(1)

    restored = BoardModel(columns=source.get_columns(), cards=[Card(**record)])

    assert restored.get_card(1) == record


def test_typed_records_normalize_mapping_definitions() -> None:
    column = Column.from_definition({"id": "todo", "title": "  To do  "})
    card = Card.from_definition(
        {
            "id": 1,
            "column_id": "todo",
            "title": "  Loaded  ",
            "description": "  Details  ",
            "priority": "Medium",
            "tags": [" database "],
        }
    )

    assert column == Column("todo", "To do")
    assert card == Card(1, "todo", "Loaded", "Details", "Medium", ("database",))
    assert Column.from_definition(column) is column
    assert Card.from_definition(card) is card


def test_snapshots_and_getters_are_defensive() -> None:
    source_tags = ["one"]
    model = BoardModel(
        columns=[{"id": "todo", "title": "To do"}],
        cards=[{"id": 1, "column_id": "todo", "title": "Card", "tags": source_tags}],
    )
    source_tags.append("changed outside")

    card = model.get_card(1)
    card["title"] = "changed copy"
    card["tags"].append("changed copy")
    snapshot = model.snapshot()
    snapshot["columns"][0]["title"] = "changed snapshot"
    snapshot["cards"].clear()

    assert model.get_columns() == [{"id": "todo", "title": "To do"}]
    assert model.get_card(1)["title"] == "Card"
    assert model.get_card(1)["tags"] == ["one"]
    assert len(model.get_cards()) == 1


def test_load_is_snapshot_round_trip_and_atomic_on_failure() -> None:
    model = make_model()
    saved = model.snapshot()
    model.clear()
    model.load(saved)

    assert model.snapshot() == saved

    with pytest.raises(BoardModelError, match="missing"):
        model.load({"columns": []})
    assert model.snapshot() == saved

    with pytest.raises(BoardModelError, match="must be iterables"):
        model.load({"columns": None, "cards": None})
    assert model.snapshot() == saved

    model.load(
        {
            "columns": [{"id": "todo", "title": "To do"}],
            "cards": [
                {"id": 1, "column": "todo", "title": "Card", "custom": "retained"}
            ],
        }
    )
    assert model.get_card(1)["custom"] == "retained"
    custom_saved = model.snapshot()

    with pytest.raises(BoardModelError, match="unknown column"):
        model.load(
            {
                "columns": [{"id": "new", "title": "New"}],
                "cards": [{"id": 99, "column_id": "missing", "title": "Bad"}],
            }
        )
    assert model.snapshot() == custom_saved


def test_card_crud_and_input_validation() -> None:
    model = BoardModel(columns=[Column("todo", "To do"), Column("done", "Done")])

    added = model.add_card(
        {"id": 1, "column_id": "todo", "title": "Write tests", "tags": ["dev"]}
    )
    assert added["title"] == "Write tests"
    assert model.update_card(1, title="Ship", priority="High")["priority"] == "High"
    assert model.update_card(1, {"description": "Ready"})["description"] == "Ready"
    assert model.update_card(1, {"column": "done"})["column"] == "done"

    with pytest.raises(BoardModelError, match="unknown column"):
        model.update_card(1, column_id="elsewhere")
    with pytest.raises(BoardModelError, match="between"):
        model.add_card(Card(2, "todo", "Out of range"), index=2)

    assert model.delete_card(1)["title"] == "Ship"
    assert model.get_cards() == []
    with pytest.raises(BoardModelError, match="unknown card"):
        model.get_card(1)


def test_move_and_reorder_card_have_predictable_insertion_order() -> None:
    model = BoardModel(
        columns=[Column("a", "A"), Column("b", "B")],
        cards=[
            Card(1, "a", "One"),
            Card(2, "a", "Two"),
            Card(3, "a", "Three"),
            Card(4, "b", "Four"),
        ],
    )

    model.reorder_card(3, 0)
    assert [card["id"] for card in model.get_cards("a")] == [3, 1, 2]

    moved = model.move_card(1, "b", 0)
    assert moved["column"] == "b"
    assert [card["id"] for card in model.get_cards("a")] == [3, 2]
    assert [card["id"] for card in model.get_cards("b")] == [1, 4]

    model.move_card(1, "b")
    assert [card["id"] for card in model.get_cards("b")] == [4, 1]


def test_column_crud_ordering_delete_guard_and_clear() -> None:
    model = BoardModel(columns=[Column("a", "A"), Column("b", "B")])
    model.add_column(Column("middle", "Middle"), index=1)
    model.move_column("b", 0)
    model.update_column("middle", "Renamed")

    assert model.get_columns() == [
        {"id": "b", "title": "B"},
        {"id": "a", "title": "A"},
        {"id": "middle", "title": "Renamed"},
    ]

    model.add_card(Card(1, "a", "Card"))
    with pytest.raises(BoardModelError, match="still contains cards"):
        model.delete_column("a")
    model.delete_column("a", delete_cards=True)
    assert model.get_cards() == []

    model.clear()
    assert model.snapshot() == {"columns": [], "cards": []}


def test_configured_fields_normalize_types_validate_and_preserve_unknown_data() -> None:
    fields = [
        {
            "key": "title",
            "label": "Title",
            "type": "text",
            "required": True,
            "card_role": "title",
            "show_on_card": True,
        },
        {
            "key": "estimate",
            "label": "Estimate",
            "type": "integer",
            "min": 0,
            "max": 20,
            "show_on_card": True,
            "card_role": "metadata",
        },
        {"key": "blocked", "label": "Blocked", "type": "checkbox"},
        {"key": "due_date", "label": "Due date", "type": "date"},
        {
            "key": "stage",
            "label": "Stage",
            "type": "select",
            "options": ["Discovery", "Delivery"],
        },
    ]
    nested = {"owners": ["Ada"]}
    model = BoardModel(
        columns=[{"id": "todo", "title": "To do"}],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "  Flexible card  ",
                "estimate": "8",
                "blocked": False,
                "due_date": date(2026, 8, 28),
                "stage": "Delivery",
                "integration_data": nested,
            }
        ],
        fields=fields,
    )
    nested["owners"].append("Changed outside")

    card = model.get_card(1)
    assert card["title"] == "Flexible card"
    assert card["estimate"] == 8
    assert card["blocked"] is False
    assert card["due_date"] == "2026-08-28"
    assert card["integration_data"] == {"owners": ["Ada"]}

    card["integration_data"]["owners"].append("Changed copy")
    assert model.get_card(1)["integration_data"] == {"owners": ["Ada"]}
    with pytest.raises(BoardModelError, match="Estimate"):
        model.update_card(1, estimate=21)
    with pytest.raises(BoardModelError, match="Stage"):
        model.update_card(1, stage="Unknown")
    with pytest.raises(BoardModelError, match="YYYY-MM-DD"):
        model.update_card(1, due_date="28/08/2026")


def test_field_schema_can_be_replaced_atomically() -> None:
    model = BoardModel(
        columns=[{"id": "todo", "title": "To do"}],
        cards=[{"id": 1, "column": "todo", "title": "Card", "score": 5}],
    )
    original_fields = model.get_fields()

    with pytest.raises(BoardModelError, match="at most"):
        model.set_fields(
            [
                {"key": "title", "label": "Title", "type": "text"},
                {"key": "score", "label": "Score", "type": "integer", "max": 2},
            ]
        )

    assert model.get_fields() == original_fields
    assert model.get_card(1)["score"] == 5
