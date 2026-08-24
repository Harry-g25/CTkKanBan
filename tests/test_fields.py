"""Concise CardField and fluent Field behavior."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from ctk_kanban import BoardModel, CardField, Field


def test_strings_and_card_fields_use_database_friendly_defaults() -> None:
    model = BoardModel(
        columns=[{"id": "todo", "title": "To do"}],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "Database card",
                "customer_name": "Acme",
                "due_date": "2026-08-28",
            }
        ],
        fields=["customer_name", CardField("due_date", type="date")],
    )

    fields = {field["key"]: field for field in model.get_fields()}
    assert fields["customer_name"]["label"] == "Customer Name"
    assert fields["customer_name"]["card_role"] == "metadata"
    assert fields["customer_name"]["show_on_card"]
    assert fields["customer_name"]["show_in_editor"]
    assert fields["customer_name"]["searchable"]
    assert fields["due_date"]["type"] == "date"
    assert model.get_card(1)["due_date"] == "2026-08-28"


def test_fluent_field_controls_input_display_and_custom_title_key() -> None:
    fields = [
        Field("summary").label("Task").title(),
        Field("description").textarea().body(),
        Field("severity")
        .select(["Low", "High"])
        .badge(colors={"High": "#ef4444"}),
        Field("estimate_hours").label("Estimate").integer(minimum=0, maximum=40),
        Field("internal_notes").textarea().editor_only(),
    ]
    model = BoardModel(
        columns=[{"id": "todo", "title": "To do"}],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "Stale canonical title",
                "summary": "Use the database summary",
                "description": "Visible body",
                "severity": "High",
                "estimate_hours": "8",
                "internal_notes": "Form only",
            }
        ],
        fields=fields,
    )

    definitions = {field["key"]: field for field in model.get_fields()}
    assert "title" not in definitions
    assert definitions["summary"]["card_role"] == "title"
    assert definitions["summary"]["required"]
    assert definitions["description"]["card_role"] == "body"
    assert definitions["severity"]["card_role"] == "badge"
    assert definitions["severity"]["colors"] == {"High": "#ef4444"}
    assert definitions["internal_notes"]["show_in_editor"]
    assert not definitions["internal_notes"]["show_on_card"]
    card = model.get_card(1)
    assert "title" not in card
    assert card["estimate_hours"] == 8


def test_field_build_returns_detached_immutable_card_field() -> None:
    options = ["Open", "Closed"]
    builder = Field("status").select(options).required()
    built = builder.build()
    options.append("Archived")
    builder.label("Changed later")

    assert built.label == "Status"
    assert built.options == ("Open", "Closed")
    with pytest.raises(FrozenInstanceError):
        setattr(built, "label", "Cannot change")


@pytest.mark.parametrize(
    "builder, field_type",
    [
        (Field("amount").number(minimum=0), "number"),
        (Field("count").integer(maximum=10), "integer"),
        (Field("active").checkbox(), "checkbox"),
        (Field("owners").multiselect(["Ada", "Grace"]), "multiselect"),
        (Field("tags").tags(), "tags"),
        (Field("created_at").datetime(), "datetime"),
    ],
)
def test_fluent_input_methods_compile_to_existing_schema(
    builder: Field,
    field_type: str,
) -> None:
    definition: dict[str, Any] = builder.build().to_definition()
    assert definition["type"] == field_type
