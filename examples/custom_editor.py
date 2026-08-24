"""Replace the generated drawer with a small application-owned card form."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ctk_kanban import CTkKanbanBoard


def main() -> None:
    app = ctk.CTk()
    app.title("CTkKanban custom editor")
    app.geometry("1050x680")

    editor_window: ctk.CTkToplevel | None = None
    board: CTkKanbanBoard

    def open_custom_editor(card: dict[str, Any]) -> None:
        nonlocal editor_window
        if editor_window is not None and editor_window.winfo_exists():
            editor_window.destroy()

        editor_window = ctk.CTkToplevel(app)
        editor_window.title(f"Edit card {card['id']}")
        editor_window.geometry("420x360")
        editor_window.grid_columnconfigure(0, weight=1)
        editor_window.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(editor_window, text="Title", anchor="w").grid(
            row=0, column=0, padx=18, pady=(18, 4), sticky="ew"
        )
        title_entry = ctk.CTkEntry(editor_window)
        title_entry.insert(0, card["title"])
        title_entry.grid(row=1, column=0, padx=18, sticky="ew")

        ctk.CTkLabel(editor_window, text="Description", anchor="w").grid(
            row=2, column=0, padx=18, pady=(14, 4), sticky="ew"
        )
        description = ctk.CTkTextbox(editor_window)
        description.insert("1.0", card.get("description", ""))
        description.grid(row=3, column=0, padx=18, sticky="nsew")

        def save() -> None:
            board.update_card(
                card["id"],
                {
                    "title": title_entry.get(),
                    "description": description.get("1.0", "end").strip(),
                },
            )
            if editor_window is not None:
                editor_window.destroy()

        ctk.CTkButton(editor_window, text="Save", command=save).grid(
            row=4, column=0, padx=18, pady=18, sticky="e"
        )
        editor_window.transient(app)
        editor_window.lift()
        title_entry.focus_set()

    board = CTkKanbanBoard(
        app,
        columns=[{"id": "todo", "title": "To do"}],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "Open the custom editor",
                "description": "Click this card to open application-owned UI.",
            }
        ],
        use_builtin_editor=False,
        on_card_open=open_custom_editor,
        on_change=lambda event: print(event["type"], event["data"]),
    )
    board.pack(fill="both", expand=True, padx=16, pady=16)
    app.mainloop()


if __name__ == "__main__":
    main()
