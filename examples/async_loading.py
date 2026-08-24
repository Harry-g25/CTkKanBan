"""Load a validated snapshot in the background without touching Tk widgets."""

from __future__ import annotations

import time

import customtkinter as ctk

from ctk_kanban import BoardSnapshot, CTkKanbanBoard, Field, snapshot_from_rows

FIELDS = ["customer_name", Field("estimate_hours").integer(minimum=0)]


def fetch_snapshot() -> BoardSnapshot:
    # Replace this delay and static data with HTTP or database work. This
    # function runs on a worker and must never read or configure Tk widgets.
    time.sleep(0.75)
    return snapshot_from_rows(
        [{"id": "queued", "title": "Queued"}, {"id": "done", "title": "Done"}],
        [
            {
                "id": 1,
                "column": "queued",
                "title": "Loaded off the UI thread",
                "customer_name": "Northstar",
                "estimate_hours": "5",
            }
        ],
        fields=FIELDS,
    )


def main() -> None:
    app = ctk.CTk()
    app.title("CTkKanban async loading")
    app.geometry("1050x680")

    status = ctk.CTkLabel(app, text="Ready", anchor="w")
    status.pack(fill="x", padx=16, pady=(12, 0))
    board = CTkKanbanBoard(app, fields=FIELDS)
    board.pack(fill="both", expand=True, padx=16, pady=12)

    def start_load() -> None:
        status.configure(text="Loading…")
        board.load_async(
            fetch_snapshot,
            on_success=lambda snapshot: status.configure(
                text=f"Loaded {len(snapshot['cards'])} card"
            ),
            on_error=lambda error: status.configure(text=f"Load failed: {error}"),
        )

    ctk.CTkButton(app, text="Load again", command=start_load).pack(pady=(0, 14))
    app.after(100, start_load)
    app.mainloop()


if __name__ == "__main__":
    main()
