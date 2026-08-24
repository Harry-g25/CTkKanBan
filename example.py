"""Runnable CTkKanban 2.2 example with fields, configuration, and theming."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Mapping
from pprint import pprint
from typing import Any

import customtkinter as ctk

from ctk_kanban import (
    ActionConfig,
    BoardConfig,
    CTkKanbanBoard,
    FieldDefinition,
    LayoutConfig,
    TextConfig,
)


def validate_estimate(value: Any, card: Mapping[str, Any]) -> bool | str:
    """Keep blocked work small enough to resolve quickly."""

    if card.get("blocked") and value is not None and value > 8:
        return "Blocked work must be estimated at 8 points or fewer"
    return True


def format_estimate(value: Any, _card: Mapping[str, Any]) -> str:
    """Control how an estimate appears on compact cards."""

    return "" if value is None else f"{value} pts"


def format_yes_no(value: Any, _card: Mapping[str, Any]) -> str:
    return "Yes" if value else "No"


# The schema controls validation, editor widgets, search, and compact-card output.
# Add as many definitions as your application needs; unconfigured card keys are
# also preserved when data is loaded, edited, emitted, or returned by get_data().
FIELDS: list[FieldDefinition] = [
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "placeholder": "What needs doing?",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "title",
        "section": "Details",
    },
    {
        "key": "description",
        "label": "Description",
        "type": "textarea",
        "default": "",
        "placeholder": "Add useful context",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "body",
        "section": "Details",
        "max_length": 500,
    },
    {
        "key": "client",
        "label": "Client",
        "type": "text",
        "default": "Internal",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "metadata",
        "section": "Details",
    },
    {
        "key": "stage",
        "label": "Stage",
        "type": "select",
        "default": "Discovery",
        "options": ["Discovery", "Delivery", "Review"],
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "badge",
        "section": "Planning",
        "colors": {
            "Discovery": "#6C5CE7",
            "Delivery": "#0984E3",
            "Review": "#00A884",
        },
    },
    {
        "key": "blocked",
        "label": "Blocked",
        "type": "checkbox",
        "default": False,
        "show_on_card": True,
        "show_in_editor": True,
        "card_role": "metadata",
        "section": "Planning",
        "help_text": "Blocked items are limited to an eight-point estimate.",
        "formatter": format_yes_no,
    },
    {
        "key": "estimate",
        "label": "Estimate",
        "type": "integer",
        "min": 0,
        "max": 100,
        "show_on_card": True,
        "show_in_editor": True,
        "card_role": "metadata",
        "section": "Planning",
        "help_text": "Whole story points from 0 to 100.",
        "validator": validate_estimate,
        "formatter": format_estimate,
    },
    {
        "key": "due_date",
        "label": "Due date",
        "type": "date",
        "placeholder": "YYYY-MM-DD",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "metadata",
        "section": "Planning",
    },
    {
        "key": "owners",
        "label": "Owners",
        "type": "multiselect",
        "default": [],
        "options": ["Avery", "Harry", "Morgan", "Sam"],
        "placeholder": "Choose one or more people",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "metadata",
        "section": "People",
    },
    {
        "key": "tags",
        "label": "Tags",
        "type": "tags",
        "default": [],
        "placeholder": "Comma-separated tags",
        "show_on_card": True,
        "show_in_editor": True,
        "searchable": True,
        "card_role": "tags",
        "section": "People",
    },
    {
        "key": "integration_ref",
        "label": "Integration reference",
        "type": "hidden",
        "show_on_card": False,
        "show_in_editor": False,
        "searchable": False,
        "card_role": "hidden",
    },
]

# This definition is added while the app is running to demonstrate that cards
# and the generated editor/sidebar immediately follow a replaced schema.
REVIEWER_FIELD: FieldDefinition = {
    "key": "reviewer",
    "label": "Reviewer",
    "type": "select",
    "default": "Unassigned",
    "options": ["Unassigned", "Avery", "Harry", "Morgan", "Sam"],
    "show_on_card": True,
    "show_in_editor": True,
    "searchable": True,
    "card_role": "metadata",
    "section": "People",
    "help_text": "This field was added at runtime with board.set_fields().",
}

COLUMNS = [
    {"id": "backlog", "title": "Backlog"},
    {"id": "doing", "title": "In progress"},
    {"id": "done", "title": "Done"},
]

CARDS = [
    {
        "id": 101,
        "column": "backlog",
        "title": "Map the onboarding journey",
        "description": "Interview recent customers and identify the rough edges.",
        "client": "Northstar",
        "stage": "Discovery",
        "blocked": False,
        "estimate": 5,
        "due_date": "2026-08-28",
        "owners": ["Avery", "Harry"],
        "tags": ["research", "ux"],
        "integration_ref": {"source": "crm", "record_id": "NS-184"},
    },
    {
        "id": 102,
        "column": "doing",
        "title": "Ship the configurable board",
        "description": "Verify field validation, search, persistence, and editor updates.",
        "client": "Internal",
        "stage": "Delivery",
        "blocked": True,
        "estimate": 8,
        "due_date": "2026-08-21",
        "owners": ["Harry"],
        "tags": ["release", "python"],
        "integration_ref": {"source": "github", "issue": 21},
    },
    {
        "id": 103,
        "column": "done",
        "title": "Agree the visual language",
        "description": "The theme now covers typography, spacing, controls, and cards.",
        "client": "Northstar",
        "stage": "Review",
        "blocked": False,
        "estimate": 3,
        "due_date": "2026-08-18",
        "owners": ["Morgan", "Sam"],
        "tags": ["theme", "design-system"],
        "integration_ref": {"source": "figma", "node": "42:7"},
    },
]

# Structured configuration is the clearest way to set permissions, layout, and
# text. The legacy allow_card_deletion=False shortcut remains supported too.
CONFIG = BoardConfig(
    actions=ActionConfig(
        delete_cards=False,
        delete_columns=False,
    ),
    layout=LayoutConfig(
        show_toolbar=True,
        enable_drag=True,
        fill_columns=True,
        use_builtin_editor=True,
        column_width=350,
        column_height=540,
        editor_width=500,
    ),
    text=TextConfig(
        board_title="CTkKanban 2.2 showcase",
        search_placeholder="Search every configured field…",
        add_card="+  New work item",
        add_column="New column",
    ),
    confirm_delete=True,
)

# Override only the tokens you need; every other value comes from the active
# CustomTkinter theme and CTkKanban's defaults.
THEME = {
    "card_corner_radius": 14,
    "card_description_max_chars": 190,
    "card_max_visible_tags": 5,
    "column_gap": 10,
    "editor_section_corner_radius": 14,
    "card_title_font": {"size": 15, "weight": "bold"},
}


def main() -> None:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("CTkKanban 2.2 example")
    app.geometry("1280x800")
    app.minsize(960, 640)
    app.grid_columnconfigure(0, weight=1)
    app.grid_rowconfigure(1, weight=1)

    intro = ctk.CTkLabel(
        app,
        text=(
            "Click a card to open its generated editor. Drag by the handle; "
            "card and column deletion are disabled in CONFIG."
        ),
        anchor="w",
        justify="left",
        wraplength=1080,
    )
    intro.grid(row=0, column=0, padx=20, pady=(14, 6), sticky="ew")

    status = tk.StringVar(app, value="Ready · no changes yet")

    def board_changed(event: dict[str, Any]) -> None:
        snapshot = event["data"]
        status.set(f"{event['type']} · {len(snapshot['cards'])} cards")
        pprint(event)

    board = CTkKanbanBoard(
        app,
        columns=COLUMNS,
        cards=CARDS,
        fields=FIELDS,
        config=CONFIG,
        theme=THEME,
        on_change=board_changed,
    )
    board.grid(row=1, column=0, padx=20, pady=6, sticky="nsew")

    controls = ctk.CTkFrame(app, fg_color="transparent")
    controls.grid(row=2, column=0, padx=20, pady=(6, 14), sticky="ew")
    controls.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(controls, textvariable=status, anchor="w").grid(
        row=0, column=0, sticky="ew"
    )
    ctk.CTkButton(
        controls,
        text="Print snapshot",
        command=lambda: pprint(board.get_data()),
    ).grid(row=0, column=1, padx=(10, 0))

    def add_reviewer() -> None:
        board.set_fields([*board.get_fields(), REVIEWER_FIELD])
        add_reviewer_button.configure(state="disabled", text="Reviewer field added")
        status.set("Schema updated · click a card to see the Reviewer field")

    add_reviewer_button = ctk.CTkButton(
        controls,
        text="Add runtime field",
        command=add_reviewer,
    )
    add_reviewer_button.grid(row=0, column=2, padx=(10, 0))

    app.mainloop()


if __name__ == "__main__":
    main()
