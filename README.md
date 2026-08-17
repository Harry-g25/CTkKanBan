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
            "description": "Click for details and use the handle to drag.",
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

- Click a card to select it and open the editor drawer.
- Save explicitly with **Save changes** or Enter; Escape cancels.
- Drag cards only from their upper-right drag handle.
- Use the visible menu for move and delete actions.
- Columns use menu actions for left/right movement instead of column dragging.

There is no inline editing, click-away autosave, whole-card dragging, floating
drag preview, or window-wide drag binding. A local Tk grab makes sure a handle
drag always receives its release event.

## Styling

Board surfaces, controls, text, hover states, and scrollbars follow the active
CustomTkinter color theme. Call `ctk.set_default_color_theme(...)` before
creating the board to use another built-in or custom theme. Priority and tag
metadata remain visible as compact colored pills. The optional `theme` mapping
can override individual board tokens when needed. `DEFAULT_THEME` contains the
complete supported token set and unknown keys are rejected to catch spelling
mistakes.

Themes now cover colors as well as component radii, borders, spacing, control
heights, scrollbar width, compact-card limits, animation timing, and font
definitions:

```python
board = CTkKanbanBoard(
    app,
    columns=columns,
    cards=cards,
    theme={
        "card_corner_radius": 16,
        "card_title_font": {"size": 15, "weight": "bold"},
        "card_description_max_chars": 220,
        "column_gap": 10,
        "editor_section_corner_radius": 14,
    },
)
```

Visual choices belong in `theme`; behavior, layout, and user-facing labels
belong in `config`.

## Configuration and permissions

`config` accepts a `BoardConfig` instance or a nested mapping. It separates
available actions, major layout choices, labels, and delete confirmation:

```python
board = CTkKanbanBoard(
    app,
    columns=columns,
    cards=cards,
    config={
        "actions": {
            "delete_cards": False,
            "delete_columns": False,
            "move_columns": False,
        },
        "layout": {
            "show_toolbar": True,
            "column_width": 340,
            "column_height": 560,
            "editor_width": 480,
        },
        "text": {
            "board_title": "Release planning",
            "add_card": "+ New work item",
        },
        "confirm_delete": True,
    },
)
```

The action switches are `add_cards`, `edit_cards`, `move_cards`,
`delete_cards`, `add_columns`, `edit_columns`, `move_columns`, and
`delete_columns`. They affect the visible controls and the corresponding public
board mutation methods. When card deletion is disabled, a non-empty column
cannot be deleted as a way around that restriction. `BoardModel` remains a
configuration-free data structure, so applications should expose the board API
rather than its model when these switches are being used as UI permissions.

For the common deletion-only case, the convenience arguments are equivalent:

```python
board = CTkKanbanBoard(
    app,
    columns=columns,
    cards=cards,
    allow_card_deletion=False,
    allow_column_deletion=False,
)
```

Existing direct options such as `show_toolbar`, `enable_drag`, `column_width`,
`column_height`, `editor_width`, `confirm_delete`, and `board_title` override
the corresponding structured setting when explicitly supplied.

## Configurable card fields

Pass `fields` to define any number of typed card values. The built-in editor is
generated from these definitions, card rendering uses their display roles, and
search uses fields marked `searchable`. When `fields` is omitted, the existing
title, description, priority, and tags behavior remains unchanged.

```python
fields = [
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "show_on_card": True,
        "searchable": True,
        "card_role": "title",
        "section": "Details",
    },
    {
        "key": "client",
        "label": "Client",
        "type": "text",
        "show_on_card": True,
        "searchable": True,
        "card_role": "metadata",
        "section": "Details",
    },
    {
        "key": "estimate",
        "label": "Estimate",
        "type": "integer",
        "min": 0,
        "max": 100,
        "show_on_card": True,
        "card_role": "metadata",
        "section": "Planning",
    },
    {
        "key": "blocked",
        "label": "Blocked",
        "type": "checkbox",
        "section": "Planning",
    },
    {
        "key": "stage",
        "label": "Stage",
        "type": "select",
        "options": ["Discovery", "Delivery", "Review"],
        "show_on_card": True,
        "card_role": "badge",
        "colors": {
            "Discovery": ("#DBEAFE", "#1E3A5F"),
            "Delivery": ("#DCFCE7", "#14532D"),
        },
    },
    {
        "key": "due_date",
        "label": "Due date",
        "type": "date",
        "show_on_card": True,
        "card_role": "metadata",
    },
]

cards = [
    {
        "id": 1,
        "column": "todo",
        "title": "Prepare proposal",
        "client": "Acme",
        "estimate": 8,
        "blocked": False,
        "stage": "Delivery",
        "due_date": "2026-08-28",
    }
]

board = CTkKanbanBoard(app, columns=columns, cards=cards, fields=fields)
```

Supported types are `text`, `textarea`, `number`, `integer`, `select`,
`multiselect`, `date`, `datetime`, `checkbox`, `tags`, and `hidden`. Dates and
datetimes are normalized to ISO strings. Definitions can also specify
`default`, `placeholder`, `show_in_editor`, `read_only`, `help_text`,
`min_length`, `max_length`, `validator`, and `formatter`.

Card display roles are `title`, `body`, `badge`, `tags`, `metadata`, and
`hidden`. `id`, `column`, and `column_id` are reserved structural keys, and a
title field is always retained. Additional card keys that are not in the schema
are preserved in snapshots, which allows applications to round-trip private
integration metadata without showing it in the editor.

Use `get_fields()` to inspect the active definitions and `set_fields(fields)`
to replace them at runtime. `set_fields()` validates existing cards atomically,
rebuilds their compact views, and rebuilds an open editor with the new controls.
If schema normalization changes stored card values, one `fields_changed` event
is emitted so the host can persist the new snapshot.

## Data

Columns contain `id` and `title`. With the default field schema, cards contain
`id`, `column`, `title`, and the optional `description`, `priority`, and `tags`
fields. Configured schemas may add any number of top-level values. IDs must be
unique and must be nonblank strings or integers. Default priorities are empty,
`Low`, `Medium`, `High`, or `Critical`. Tags are trimmed, nonblank strings
without commas.

`get_data()` returns a detached snapshot for application-owned storage. Use
string or integer IDs when the snapshot will be encoded as JSON.
`set_data(snapshot)` replaces the displayed board without emitting an event.
The optional `on_change` callback receives one event after each successful
add, edit, move, or delete that changes board data; `event["data"]` contains
the latest complete snapshot. Search also changes only the view and does not
emit an event.

Persistence, retries, paging, polling, and conflict handling intentionally live
in the host application rather than the widget.

### Database rows

Database results can be converted without adding a database-driver dependency
to CTkKanban. Mapping rows from psycopg `dict_row`, `sqlite3.Row`, and
SQLAlchemy are accepted by `snapshot_from_rows()`:

```python
from ctk_kanban import snapshot_from_rows

snapshot = snapshot_from_rows(column_rows, card_rows, fields=fields)
board.set_data(snapshot)
```

Plain DB-API tuple results can be converted using cursor metadata. Fetch each
result before reusing its cursor:

```python
from ctk_kanban import rows_from_cursor, snapshot_from_rows

cursor.execute("SELECT id, title FROM kanban_columns ORDER BY position")
columns = rows_from_cursor(cursor)

cursor.execute(
    """
    SELECT id, column_id AS column, title, description, priority, tags
    FROM kanban_cards
    ORDER BY column_id, position
    """
)
cards = rows_from_cursor(cursor)

board.set_data(snapshot_from_rows(columns, cards))
```

Use SQL aliases such as `column_id AS column` to produce CTkKanban's exact
record keys. Result column names must be unique. `rows_from_cursor()` consumes
all remaining rows returned by the cursor.

`snapshot_from_cursors(columns_cursor, cards_cursor)` is a shorter equivalent
when two separately executed cursors are available. Every snapshot helper
normalizes and validates the complete result before returning it.

### Asynchronous loading

`load_async()` performs fetching and validation on a daemon worker, then calls
`set_data()` and user callbacks safely on Tk's thread:

```python
import psycopg
from psycopg.rows import dict_row

from ctk_kanban import snapshot_from_rows


def fetch_board():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        columns = connection.execute(COLUMN_QUERY).fetchall()
        cards = connection.execute(CARD_QUERY).fetchall()
        return snapshot_from_rows(columns, cards)


board.load_async(
    fetch_board,
    on_success=lambda snapshot: print("Loaded", len(snapshot["cards"]), "cards"),
    on_error=lambda error: print("Load failed:", error),
)
```

`board.is_loading` reports pending work and `board.load_error` retains the most
recent asynchronous error. Existing data is preserved on failure unless
`clear_on_error=True` is requested. Starting a newer load makes an older result
stale, so it cannot overwrite newer data.

Pass `on_card_open` when the host application owns card editing. Its callback
receives the card snapshot and replaces the built-in drawer when a card opens.

## Main API

```text
get_data() / set_data(data)
get_card(id) / get_cards(column_id=None) / get_columns()
add_card() / update_card() / move_card() / delete_card()
add_column() / update_column() / move_column() / delete_column()
open_add_card_editor() / open_edit_card_editor(id)
search(query)
set_loading(bool) / load_async(fetch_snapshot, ...)
rows_from_cursor(cursor)
snapshot_from_rows(columns, cards, fields=...) / snapshot_from_cursors(..., fields=...)
get_fields() / set_fields(fields)
```

The Tk-free `BoardModel` is also public for applications that want to validate
or manipulate board data without creating a window. `Column.from_definition()`
and `Card.from_definition()` expose the same normalization for typed application
code, while `BoardSnapshot`, `ColumnRecord`, and `CardRecord` provide public
typing shapes.

## Migrating from 1.x

Version 2 is intentionally breaking. Replace mutation-specific callbacks with
`on_change`, and import from `ctk_kanban` rather than `CTkKanBan`. The focused
2.0 API initially removed dynamic fields; the current schema API restores that
capability without restoring the former persistence, filtering, sorting, and
large constructor-flag frameworks. Custom record keys are now preserved.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy ctk_kanban
```
