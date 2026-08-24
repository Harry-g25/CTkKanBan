"""Load and update a board using real SQLite cursors and database key names."""

from __future__ import annotations

import sqlite3
from typing import Any

import customtkinter as ctk

from ctk_kanban import ActionConfig, BoardConfig, CTkKanbanBoard, Field


def create_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE statuses (
            status_id INTEGER PRIMARY KEY,
            status_name TEXT NOT NULL,
            position INTEGER NOT NULL
        );
        CREATE TABLE tasks (
            task_id INTEGER PRIMARY KEY,
            status_id INTEGER NOT NULL REFERENCES statuses(status_id),
            summary TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            due_date TEXT NOT NULL,
            estimate_hours INTEGER NOT NULL
        );
        INSERT INTO statuses VALUES
            (10, 'To do', 1), (20, 'Doing', 2), (30, 'Done', 3);
        INSERT INTO tasks VALUES
            (101, 10, 'Map the onboarding journey', 'Northstar', 'High', '2026-09-10', 8),
            (102, 20, 'Prepare the release', 'Internal', 'Medium', '2026-09-05', 5);
        """
    )
    return connection


def main() -> None:
    connection = create_database()
    app = ctk.CTk()
    app.title("CTkKanban SQLite rows")
    app.geometry("1150x720")

    fields = [
        "customer_name",
        Field("severity")
        .select(["Low", "Medium", "High"])
        .badge(colors={"High": "#EF4444", "Medium": "#F59E0B"}),
        Field("due_date").date(),
        Field("estimate_hours").label("Estimate").integer(minimum=0),
    ]

    def persist(event: dict[str, Any]) -> None:
        # SQLite is local and fast enough for this demo. Queue slow remote
        # database writes to a worker instead of blocking Tk's UI thread.
        with connection:
            for card in event["data"]["cards"]:
                connection.execute(
                    """
                    UPDATE tasks
                    SET status_id = ?, summary = ?, customer_name = ?,
                        severity = ?, due_date = ?, estimate_hours = ?
                    WHERE task_id = ?
                    """,
                    (
                        card["column"],
                        card["title"],
                        card["customer_name"],
                        card["severity"],
                        card["due_date"],
                        card["estimate_hours"],
                        card["id"],
                    ),
                )
        print("Persisted", event["type"])

    board = CTkKanbanBoard.from_rows(
        app,
        columns=connection.execute(
            "SELECT status_id, status_name FROM statuses ORDER BY position"
        ),
        cards=connection.execute(
            """
            SELECT task_id, status_id, summary, customer_name,
                   severity, due_date, estimate_hours
            FROM tasks
            ORDER BY task_id
            """
        ),
        column_keys={"id": "status_id", "title": "status_name"},
        card_keys={"id": "task_id", "column": "status_id", "title": "summary"},
        fields=fields,
        config=BoardConfig(
            actions=ActionConfig(
                add_cards=False,
                delete_cards=False,
                add_columns=False,
                edit_columns=False,
                move_columns=False,
                delete_columns=False,
            )
        ),
        fill_columns=True,
        on_change=persist,
    )
    board.pack(fill="both", expand=True, padx=16, pady=16)
    app.mainloop()
    connection.close()


if __name__ == "__main__":
    main()
