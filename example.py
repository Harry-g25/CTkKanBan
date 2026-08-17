"""Minimal runnable CTkKanban example."""

import customtkinter as ctk

from ctk_kanban import CTkKanbanBoard


def main() -> None:
    app = ctk.CTk()
    app.title("CTkKanban")
    app.geometry("1050x680")

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
                "title": "A straightforward Kanban card",
                "description": "Use Edit for details and :: to drag.",
                "priority": "Medium",
                "tags": ["welcome"],
            }
        ],
        on_change=lambda event: print(event["type"]),
    )
    board.pack(fill="both", expand=True)
    app.mainloop()


if __name__ == "__main__":
    main()
