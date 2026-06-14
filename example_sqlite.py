"""Runnable SQLite-backed CTkKanban example."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ctk_kanban import CTkKanbanBoard, SQLiteKanbanDataSource

DATABASE = Path(__file__).with_name("kanban_demo.db")
BOARD_ID = "sqlite-demo"


def main() -> None:
    source = SQLiteKanbanDataSource(DATABASE)
    source.seed_board(
        BOARD_ID,
        [
            {"id": "todo", "title": "To Do", "max_cards": 5},
            {"id": "doing", "title": "Doing", "max_cards": 3},
            {"id": "done", "title": "Done"},
        ],
        [
            {"id": "welcome", "column": "todo", "title": "Drag me", "sort_order": 1024},
        ],
    )

    app = ctk.CTk()
    app.title("CTkKanban SQLite Demo")
    app.geometry("1100x700")
    app.grid_rowconfigure(0, weight=1)
    app.grid_columnconfigure(0, weight=1)

    board = CTkKanbanBoard(
        app,
        data_source=source,
        board_id=BOARD_ID,
        auto_load=True,
        server_side_query=True,
        page_size=100,
        poll_interval_ms=2000,
        completed_columns=["done"],
        show_toolbar=True,
        responsive_columns=True,
        card_form_mode="sidepanel",
    )
    board.grid(row=0, column=0, sticky="nsew")
    app.mainloop()


if __name__ == "__main__":
    main()
