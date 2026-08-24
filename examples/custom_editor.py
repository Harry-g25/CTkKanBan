"""Build an application-owned card form from CTkKanban field data."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from ctk_kanban import BoardModelError, CTkKanbanBoard, Field


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
        editor_window.geometry("460x610")
        editor_window.grid_columnconfigure(0, weight=1)
        editor_window.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(editor_window, label_text="Card details")
        form.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="nsew")
        form.grid_columnconfigure(0, weight=1)

        readers: dict[str, Callable[[], Any]] = {}
        field_data = board.get_field_data(card["id"])
        row = 0

        for key, field in field_data.items():
            if not field["show_in_editor"]:
                continue

            field_type = field["type"]
            state = "disabled" if field["read_only"] else "normal"
            ctk.CTkLabel(form, text=field["label"], anchor="w").grid(
                row=row, column=0, padx=8, pady=(10, 4), sticky="ew"
            )
            row += 1

            if field_type == "textarea":
                control = ctk.CTkTextbox(form, height=96)
                control.insert("1.0", str(field["value"] or ""))
                control.configure(state=state)
                readers[key] = lambda widget=control: widget.get("1.0", "end-1c")
            elif field_type == "select":
                options = [str(option) for option in field.get("options", ())]
                current = str(field["value"] or "")
                if current not in options:
                    options.insert(0, current)
                control = ctk.CTkOptionMenu(form, values=options or [""])
                control.set(current)
                control.configure(state=state)
                readers[key] = control.get
            elif field_type == "checkbox":
                variable = ctk.BooleanVar(value=bool(field["value"]))
                control = ctk.CTkCheckBox(
                    form,
                    text=field.get("help_text") or "Enabled",
                    variable=variable,
                    state=state,
                )
                readers[key] = variable.get
            else:
                # The model converts number, integer, date, and datetime text
                # when update_card() validates the completed form.
                control = ctk.CTkEntry(form, state="normal")
                control.insert(0, "" if field["value"] is None else str(field["value"]))
                control.configure(state=state)
                readers[key] = control.get

            control.grid(row=row, column=0, padx=8, sticky="ew")
            row += 1

            if field.get("help_text") and field_type != "checkbox":
                ctk.CTkLabel(
                    form,
                    text=field["help_text"],
                    anchor="w",
                    text_color=("gray45", "gray65"),
                ).grid(row=row, column=0, padx=8, pady=(3, 0), sticky="ew")
                row += 1

        columns = board.get_columns()
        column_choices = {
            f"{column['title']} [{index + 1}]": column["id"]
            for index, column in enumerate(columns)
        }
        selected_column = next(
            label for label, column_id in column_choices.items() if column_id == card["column"]
        )
        ctk.CTkLabel(form, text="Column", anchor="w").grid(
            row=row, column=0, padx=8, pady=(10, 4), sticky="ew"
        )
        row += 1
        column_menu = ctk.CTkOptionMenu(form, values=list(column_choices))
        column_menu.set(selected_column)
        if not board.actions.move_cards:
            column_menu.configure(state="disabled")
        column_menu.grid(row=row, column=0, padx=8, sticky="ew")

        error_label = ctk.CTkLabel(editor_window, text="", text_color="#DC2626")
        error_label.grid(row=1, column=0, padx=18, sticky="ew")

        def save() -> None:
            # Read-only fields are presentation-only in this form and are left
            # unchanged. One update_card() call validates and saves everything.
            updates = {
                key: read()
                for key, read in readers.items()
                if not field_data[key]["read_only"]
            }
            if board.actions.move_cards:
                updates["column"] = column_choices[column_menu.get()]
            try:
                board.update_card(card["id"], updates)
            except BoardModelError as exc:
                error_label.configure(text=str(exc))
                return
            if editor_window is not None:
                editor_window.destroy()

        actions = ctk.CTkFrame(editor_window, fg_color="transparent")
        actions.grid(row=2, column=0, padx=18, pady=(8, 18), sticky="e")
        ctk.CTkButton(
            actions,
            text="Cancel",
            fg_color="transparent",
            border_width=1,
            command=editor_window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(actions, text="Save changes", command=save).grid(row=0, column=1)

        editor_window.transient(app)
        editor_window.lift()

    board = CTkKanbanBoard(
        app,
        columns=[
            {"id": "todo", "title": "To do"},
            {"id": "done", "title": "Done"},
        ],
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "Open the custom editor",
                "description": "The form is generated from get_field_data().",
                "status": "Doing",
                "estimate": 4,
                "approved": False,
                "reference": "APP-17",
            }
        ],
        fields=[
            Field("title").label("Task").title(),
            Field("description").textarea().body(),
            Field("status").select(["To do", "Doing", "Done"]).badge(),
            Field("estimate").integer(minimum=0).metadata(),
            Field("approved").checkbox().editor_only(),
            Field("reference").editor_only().read_only(),
        ],
        use_builtin_editor=False,
        on_card_open=open_custom_editor,
        on_change=lambda event: print(event["type"], event["data"]),
    )
    board.pack(fill="both", expand=True, padx=16, pady=16)
    app.mainloop()


if __name__ == "__main__":
    main()
