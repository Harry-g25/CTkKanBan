"""Smallest practical CTkKanban board with built-in editing and events."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ctk_kanban import CTkKanbanBoard


def main() -> None:
    app = ctk.CTk()
    app.title("CTkKanban basic board")
    app.geometry("1100x700")

    def changed(event: dict[str, Any]) -> None:
        print(event["type"], event["data"])

    board = CTkKanbanBoard(
        app,
        columns=[
            {"id": "todo", "title": "To do"},
            {"id": "doing", "title": "Doing"},
            {"id": "done", "title": "Done"},
        ],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "Try the board",
                "description": "Click to edit or drag from the handle.",
                "priority": "High",
                "tags": ["getting-started"],
            }
        ],
        fill_columns=True,
        on_change=changed,
    )
    board.pack(fill="both", expand=True, padx=16, pady=16)
    app.mainloop()


if __name__ == "__main__":
    main()
