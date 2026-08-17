# CTkKanban

CTkKanban is a small Kanban widget for CustomTkinter. It focuses on predictable
card editing and movement instead of trying to be a database framework or a
complete project-management application.

## Install

```bash
python -m pip install CTkKanBan
```

Import the package with its canonical lowercase name:

```python
import customtkinter as ctk

from ctk_kanban import CTkKanbanBoard

app = ctk.CTk()
app.geometry("1000x650")

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
            "title": "Try the simplified board",
            "description": "Drag only from the :: handle.",
            "priority": "High",
            "tags": ["demo"],
        }
    ],
    on_change=lambda event: print(event["type"], event["data"]),
)
board.pack(fill="both", expand=True)
app.mainloop()
```

## Interaction model

- Click a card to select it.
- Choose **Edit** to slide open the editor drawer from the right side of the board.
- Save explicitly with **Save** or Enter; Escape cancels.
- Drag cards only from their `::` handle.
- Use the visible `...` menu for move and delete actions.
- Columns use menu actions for left/right movement instead of column dragging.

There is no inline editing, click-away autosave, whole-card dragging, floating
drag preview, or window-wide drag binding. A local Tk grab makes sure a handle
drag always receives its release event.

## Styling

Board surfaces, controls, text, hover states, and scrollbars follow the active
CustomTkinter color theme. Call `ctk.set_default_color_theme(...)` before
creating the board to use another built-in or custom theme. Priority and tag
metadata remain visible as compact colored pills. The optional `theme` mapping
can override individual board tokens when needed.

## Data

Columns contain `id` and `title`. Cards contain `id`, `column`, `title`, and the
optional `description`, `priority`, and `tags` fields. IDs must be unique and
must be nonblank strings or integers. Priorities are empty, `Low`, `Medium`,
`High`, or `Critical`. Tags are trimmed, nonblank strings without commas.

`get_data()` returns a detached snapshot for application-owned storage. Use
string or integer IDs when the snapshot will be encoded as JSON.
`set_data(snapshot)` replaces the displayed board without emitting an event.
The optional `on_change` callback receives one event after each successful
add, edit, move, or delete that changes board data; `event["data"]` contains
the latest complete snapshot. Search also changes only the view and does not
emit an event.

Persistence, retries, paging, polling, and conflict handling intentionally live
in the host application rather than the widget.

Pass `on_card_open` when the host application owns card editing. Its callback
receives the card snapshot and replaces the built-in drawer for the Edit
action.

## Main API

```text
get_data() / set_data(data)
get_card(id) / get_cards(column_id=None) / get_columns()
add_card() / update_card() / move_card() / delete_card()
add_column() / update_column() / move_column() / delete_column()
open_add_card_editor() / open_edit_card_editor(id)
search(query)
```

The Tk-free `BoardModel` is also public for applications that want to validate
or manipulate board data without creating a window.

## Migrating from 1.x

Version 2 is intentionally breaking. Remove dynamic field definitions, inline
editing options, persistence adapters, advanced filter/sort options, and the
large set of `enable_*`/`show_*` constructor flags. Replace mutation-specific
callbacks with `on_change`, and import from `ctk_kanban` rather than
`CTkKanBan`. Remove custom record keys before loading data; v2 rejects fields
outside its small schema instead of silently discarding them.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy ctk_kanban
```
