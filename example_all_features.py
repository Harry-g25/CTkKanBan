"""Interactive demonstration of the major CTkKanbanBoard features."""

from __future__ import annotations

import sys
from typing import Any

import customtkinter as ctk

import ctk_kanban
from ctk_kanban import CTkKanbanBoard, __version__

COLUMNS = [
    {"id": "backlog", "title": "Backlog", "color": "#64748B"},
    {"id": "todo", "title": "To Do", "color": "#3B82F6"},
    {"id": "in_progress", "title": "In Progress", "color": "#F59E0B", "max_cards": 4},
    {"id": "review", "title": "Review", "color": "#8B5CF6"},
    {"id": "done", "title": "Done", "color": "#10B981"},
]

FIELDS = [
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
        "sortable": True,
        "placeholder": "What needs doing?",
    },
    {
        "key": "description",
        "label": "Description",
        "type": "textarea",
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
    },
    {
        "key": "priority",
        "label": "Priority",
        "type": "select",
        "options": ["Low", "Medium", "High", "Critical"],
        "default": "Medium",
        "show_on_card": True,
        "show_in_form": True,
        "filterable": True,
        "sortable": True,
    },
    {
        "key": "assignee",
        "label": "Assignee",
        "type": "select",
        "options": ["Harry", "Maya", "Owen", "Priya"],
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
        "filterable": True,
    },
    {
        "key": "due_date",
        "label": "Due date",
        "type": "date",
        "placeholder": "YYYY-MM-DD",
        "show_on_card": True,
        "show_in_form": True,
        "filterable": True,
        "sortable": True,
    },
    {
        "key": "tags",
        "label": "Tags",
        "type": "tags",
        "placeholder": "Comma-separated tags",
        "show_on_card": True,
        "show_in_form": True,
        "searchable": True,
        "filterable": True,
    },
    {
        "key": "estimate",
        "label": "Estimate (hours)",
        "type": "number",
        "show_on_card": True,
        "show_in_form": True,
        "sortable": True,
    },
    {
        "key": "customer_visible",
        "label": "Customer visible",
        "type": "checkbox",
        "show_on_card": False,
        "show_in_form": True,
        "filterable": True,
    },
]

CARDS = [
    {
        "id": 1,
        "column": "backlog",
        "title": "Audit keyboard navigation",
        "description": "Review focus order and add a short accessibility checklist.",
        "priority": "Medium",
        "assignee": "Maya",
        "due_date": "2026-06-18",
        "tags": ["UX", "Audit"],
        "estimate": 3,
        "sort_order": 1,
    },
    {
        "id": 2,
        "column": "todo",
        "title": "Publish package metadata",
        "description": "Validate the wheel metadata and dependency declaration.",
        "priority": "High",
        "assignee": "Harry",
        "due_date": "2026-06-16",
        "tags": ["Release", "Python"],
        "estimate": 2,
        "sort_order": 1,
    },
    {
        "id": 3,
        "column": "todo",
        "title": "Prepare sales dashboard sample",
        "description": "Use the flexible field system for a small pipeline board.",
        "priority": "Low",
        "assignee": "Priya",
        "due_date": "2026-06-24",
        "tags": ["Example", "Sales"],
        "estimate": 5,
        "sort_order": 2,
    },
    {
        "id": 4,
        "column": "in_progress",
        "title": "Database rejection demo",
        "description": "Moving this card to Done is rejected by the example callback.",
        "priority": "Critical",
        "assignee": "Owen",
        "due_date": "2026-06-14",
        "tags": ["Callbacks", "Demo"],
        "estimate": 4,
        "sort_order": 1,
    },
    {
        "id": 5,
        "column": "review",
        "title": "Review dark theme contrast",
        "description": "Check cards, chips, toolbar controls, and selection colors.",
        "priority": "High",
        "assignee": "Maya",
        "due_date": "2026-06-15",
        "tags": ["Theme", "Review"],
        "estimate": 2,
        "sort_order": 1,
    },
    {
        "id": 6,
        "column": "done",
        "title": "Create package structure",
        "description": "Split board, column, card, toolbar, dialogs, models, and validation.",
        "priority": "Medium",
        "assignee": "Harry",
        "due_date": "2026-06-13",
        "tags": ["Architecture"],
        "estimate": 4,
        "sort_order": 1,
    },
]


def log_event(event: dict[str, Any]) -> None:
    """Stand-in for application logging or database persistence."""

    print(f"{event['type']}: {event.get('card_id', event.get('column_id', 'board'))}")


def save_board_data(event: dict[str, Any]) -> bool | dict[str, Any]:
    """Persist the full board snapshot in one place after any data change."""

    action = event["action_event"]
    print("Save board snapshot to database here:", action["type"], len(event["cards"]), "cards")
    if action["type"] == "card_moved" and action["card_id"] == 4 and action["new_column"] == "done":
        return {"cancel": True, "reason": "Demo database rejected card 4 moving to Done"}
    return True


def custom_assign_action(event: dict[str, Any]) -> None:
    card = event["card_data"]
    print(f"Custom action requested for {card['title']!r}")


def main() -> None:
    if "--diagnose" in sys.argv:
        print(f"CTkKanban {__version__}")
        print(f"Package: {ctk_kanban.__file__}")
        print(f"Theme: {ctk_kanban.DEFAULT_THEME['board_fg_color']}")
        return
    appearance = "System"
    if "--light" in sys.argv:
        appearance = "Light"
    elif "--dark" in sys.argv:
        appearance = "Dark"
    ctk.set_appearance_mode(appearance)
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title(f"CTkKanban - Modern Showcase v{__version__}")
    app.geometry("1450x820")
    app.minsize(950, 600)
    app.grid_rowconfigure(0, weight=1)
    app.grid_columnconfigure(0, weight=1)

    board = CTkKanbanBoard(
        app,
        columns=COLUMNS,
        cards=CARDS,
        fields=FIELDS,
        enable_horizontal_scroll=True,
        enable_column_scroll=True,
        card_form_mode="sidepanel",
        column_width=280,
        column_height=680,
        show_toolbar=True,
        show_search=True,
        show_filter_button=True,
        show_sort_button=True,
        show_add_card_button=True,
        show_column_add_button=True,
        enforce_column_limits=True,
        enable_card_drag=True,
        enable_card_reorder=True,
        enable_column_drag=True,
        enable_drag_preview=True,
        show_drop_indicator=True,
        enable_horizontal_autoscroll=True,
        enable_vertical_autoscroll=True,
        enable_builtin_card_form=True,
        enable_card_context_menu=True,
        enable_card_double_click=True,
        confirm_delete=True,
        filter_mode="hide",
        completed_columns=["done"],
        responsive_columns=True,
        show_drag_handles=True,
        card_context_menu_items=[
            {"label": "Assign to me", "callback": custom_assign_action, "separator_before": True},
        ],
        on_card_clicked=log_event,
        on_data_changed=save_board_data,
        on_column_reordered=log_event,
        on_filter_changed=log_event,
        on_search_changed=log_event,
        on_sort_changed=log_event,
        on_action_cancelled=lambda event: print("Action restored:", event["reason"]),
        on_error=lambda event: print("Board error:", event["message"]),
    )
    board.grid(row=0, column=0, sticky="nsew")
    if "--form" in sys.argv:
        app.after(300, lambda: board.open_add_card_form("todo"))

    app.mainloop()


if __name__ == "__main__":
    main()
