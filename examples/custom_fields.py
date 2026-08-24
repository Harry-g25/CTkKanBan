"""Generated inputs and compact-card roles using the concise Field API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import customtkinter as ctk

from ctk_kanban import CardField, CTkKanbanBoard, Field


def validate_estimate(value: Any, card: Mapping[str, Any]) -> bool | str:
    if card.get("blocked") and value is not None and value > 8:
        return "Blocked work must be split into estimates of 8 or fewer"
    return True


def format_budget(value: Any, _card: Mapping[str, Any]) -> str:
    return "" if value is None else f"£{value:,.2f}"


FIELDS = [
    Field("summary").label("Task").title().placeholder("What needs doing?"),
    "customer_name",
    Field("description").textarea().body().length(maximum=500),
    Field("budget").number(minimum=0).fmt(format_budget),
    Field("estimate")
    .integer(minimum=0, maximum=100)
    .validate(validate_estimate),
    Field("stage")
    .select(["Discovery", "Delivery", "Review"])
    .badge(
        colors={
            "Discovery": "#7C3AED",
            "Delivery": "#2563EB",
            "Review": "#059669",
        }
    ),
    Field("owners").multiselect(["Avery", "Harry", "Morgan", "Sam"]),
    CardField("due_date", label="Due", type="date"),
    Field("review_at").datetime().card_only(),
    Field("blocked").checkbox(),
    Field("labels").tags(),
    Field("source_name").default("Imported").read_only(),
    Field("internal_notes").textarea().editor_only(),
    Field("source_payload").hide(),
]


def main() -> None:
    app = ctk.CTk()
    app.title("CTkKanban custom fields")
    app.geometry("1100x760")

    board = CTkKanbanBoard(
        app,
        columns=[{"id": "planned", "title": "Planned"}],
        cards=[
            {
                "id": 1,
                "column": "planned",
                "summary": "Prepare customer workshop",
                "customer_name": "Northstar",
                "description": "Collect examples and agree the agenda.",
                "budget": 1250,
                "estimate": 5,
                "stage": "Discovery",
                "owners": ["Avery", "Harry"],
                "due_date": "2026-09-10",
                "review_at": "2026-09-08T14:30:00",
                "blocked": False,
                "labels": ["customer", "workshop"],
                "source_name": "CRM",
                "internal_notes": "Confirm room capacity.",
                "source_payload": {"record_id": "CRM-184"},
            }
        ],
        fields=FIELDS,
        on_change=lambda event: print(event["type"], event["data"]),
    )
    board.pack(fill="both", expand=True, padx=16, pady=16)
    app.mainloop()


if __name__ == "__main__":
    main()
