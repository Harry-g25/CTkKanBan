# CTkKanban

CTkKanban is a small Kanban widget for CustomTkinter. It focuses on predictable
card editing and movement instead of trying to be a database framework or a
complete project-management application.

It provides:

- a `CTkKanbanBoard` widget with explicit editing, search, selection, menus,
  handle-only dragging, loading states, and light/dark theme support;
- a schema-driven editor for any number of typed card fields;
- granular action permissions, layout configuration, and customizable text;
- a Tk-free `BoardModel` with validation and deterministic manual ordering;
- detached snapshots, database-row adapters, and one application-owned change
  boundary for persistence.

The complete single-page guide is also available in
[`docs/index.html`](docs/index.html). This README covers the same contracts in
a format suited to package and repository viewers.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Interaction model](#interaction-model)
- [Styling and theme tokens](#styling-and-theme-tokens)
- [Configuration and permissions](#configuration-and-permissions)
- [Configurable card fields](#configurable-card-fields)
- [Data contract and ordering](#data-contract-and-ordering)
- [Change events and persistence](#change-events-and-persistence)
- [Database rows](#database-rows)
- [Asynchronous loading](#asynchronous-loading)
- [API reference](#api-reference)
- [Errors and lifecycle](#errors-and-lifecycle)
- [Migrating from 1.x](#migrating-from-1x)
- [Development](#development)

## Install

```bash
python -m pip install CTkKanBan
```

CTkKanban requires Python 3.10 or newer and installs CustomTkinter 5.2.2 or
newer (below major version 7). `CTkKanBan` is the PyPI distribution name;
`ctk_kanban` is the lowercase Python package name.

## Quick start

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

`columns` and `cards` may be any iterables of mappings. Their input order is
the initial manual order. Call `board.get_data()` at any time to retrieve the
complete, detached state.

## Interaction model

- Click a card to select it and open the editor drawer.
- Save explicitly with **Save changes** or Enter; Escape cancels.
- Drag cards only from their upper-right drag handle.
- Use the visible menu for move and delete actions.
- Columns use menu actions for left/right movement instead of column dragging.

There is no inline editing, click-away autosave, whole-card dragging, floating
drag preview, or window-wide drag binding. A local Tk grab makes sure a handle
drag always receives its release event.

The drawer marks changed state and disables Save until a value differs. Enter
saves from ordinary controls, `Ctrl+Enter` saves from anywhere in the drawer,
and Escape cancels. Enter inside a multiline textbox inserts a new
line. Opening another editor replaces the currently open drawer.

Search is a case-insensitive substring match across only fields marked
`searchable`; lists contribute each item. Search changes visibility, not data.
Dragging and menu up/down ordering are disabled while results are filtered,
because a visible index is ambiguous relative to hidden cards. Clear the query
before interactive reordering.

## Styling and theme tokens

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

Call `merge_theme(overrides)` when a reusable, validated mapping is useful.
It reads fresh defaults from the active CustomTkinter theme, deep-copies the
overrides where possible, and rejects unknown token names. `DEFAULT_THEME` is
the import-time discovery snapshot. A color may be a normal CustomTkinter
color string or a `(light, dark)` pair. Font tokens are keyword mappings passed
to `ctk.CTkFont`. Palette tokens such as `column_accent_colors` and
`tag_pill_colors` must remain non-empty sequences.

### Complete token reference

The supported token set is intentionally closed. Values are shown through
`DEFAULT_THEME`; the table below describes all 97 names.

| Area | Tokens |
| --- | --- |
| Board surfaces | `board_fg_color`, `toolbar_fg_color`, `column_fg_color`, `column_header_fg_color`, `column_border_color`, `column_accent_colors` |
| Cards and drag feedback | `card_fg_color`, `card_hover_color`, `dragging_card_fg_color`, `card_border_color`, `selected_border_color`, `drop_indicator_color` |
| Shared colors | `text_color`, `muted_text_color`, `accent_color`, `control_hover_color`, `count_fg_color`, `empty_icon_fg_color`, `divider_color`, `danger_color` |
| Editor/input/scroll colors | `editor_fg_color`, `editor_section_fg_color`, `input_border_color`, `scrollbar_color`, `scrollbar_hover_color`, `error_text_color` |
| Pills and priorities | `pill_text_color`, `priority_low_color`, `priority_medium_color`, `priority_high_color`, `priority_critical_color`, `tag_pill_colors` |
| Native context menu | `menu_fg_color`, `menu_text_color`, `menu_hover_color`, `menu_disabled_text_color` |
| Board and toolbar geometry | `board_padding_x`, `board_padding_y`, `toolbar_height`, `toolbar_corner_radius`, `toolbar_padding_x`, `toolbar_padding_y`, `toolbar_content_padding_y`, `search_width`, `button_height`, `control_corner_radius`, `small_control_size` |
| Toolbar fonts | `toolbar_title_font`, `toolbar_summary_font` |
| Column geometry | `column_corner_radius`, `column_border_width`, `column_gap`, `column_accent_height`, `column_header_padding_x`, `card_gap` |
| Column fonts | `column_title_font`, `column_count_font`, `column_empty_title_font`, `column_empty_body_font` |
| Card geometry and limits | `card_corner_radius`, `card_border_width`, `card_selected_border_width`, `card_accent_width`, `card_description_max_chars`, `card_max_visible_tags`, `pill_height`, `pill_corner_radius` |
| Card fonts | `card_title_font`, `card_body_font`, `card_metadata_font`, `pill_font` |
| Editor layout | `editor_border_width`, `editor_header_padding_x`, `editor_header_padding_y`, `editor_form_padding_x`, `editor_form_padding_y`, `editor_field_padding_x`, `editor_field_gap`, `editor_section_gap`, `editor_section_corner_radius`, `editor_section_border_width`, `editor_section_title_padding_y` |
| Editor motion | `editor_slide_step`, `editor_slide_interval_ms` |
| Editor fonts | `editor_eyebrow_font`, `editor_title_font`, `editor_status_font`, `section_title_font`, `field_label_font`, `help_text_font`, `status_text_font` |
| Inputs and scrollbar | `input_height`, `compact_input_height`, `input_corner_radius`, `input_border_width`, `textbox_height`, `scrollbar_width` |

Theme mappings are resolved at construction time. Changing the source mapping
later does not restyle existing child widgets; create or rebuild the board when
switching to a substantially different per-board theme.

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

The same configuration can be constructed with frozen dataclasses:

```python
from ctk_kanban import ActionConfig, BoardConfig, LayoutConfig, TextConfig

config = BoardConfig(
    actions=ActionConfig(delete_cards=False, delete_columns=False),
    layout=LayoutConfig(column_width=340, column_height=560),
    text=TextConfig(board_title="Release planning"),
    confirm_delete=True,
)
```

Nested mappings may be partial; omitted values retain the defaults. Unknown
keys are rejected. `merge_config(config)` validates either representation and
returns a `BoardConfig`.

### Action settings

All action settings default to `True`.

| Setting | Affected board behavior |
| --- | --- |
| `add_cards` | Add-card controls and `add_card()`; the add-card editor becomes a no-op. |
| `edit_cards` | Card opening/edit controls and `update_card()`; `on_card_open` is not called when editing is disabled. |
| `move_cards` | Dragging, card move menus, editor column changes, `move_card()`, and `update_card()` calls that change column. |
| `delete_cards` | Card delete menus and `delete_card()`; also blocks cascading deletion through a non-empty column. |
| `add_columns` | Add-column controls/dialog and `add_column()`. |
| `edit_columns` | Column rename controls and `update_column()`. |
| `move_columns` | Column left/right controls and `move_column()`. |
| `delete_columns` | Column delete controls and `delete_column()`. |

Disabled public mutation methods raise `BoardModelError`. UI-opening helpers
return without opening when their action is disabled. These settings do not
block `set_data()`, `set_fields()`, or direct access to `board.model`; they are
widget behavior controls, not a security boundary. `BoardModel` deliberately
has no action configuration.

When card deletion is disabled, `delete_column(..., delete_cards=True)` is
also blocked for non-empty columns. This prevents column deletion from
bypassing the card policy. `confirm_delete` only controls confirmation dialogs
started by the built-in menus; direct API deletions never prompt.

### Layout settings

| Setting | Default | Contract |
| --- | ---: | --- |
| `show_toolbar` | `True` | Show the title, summary, search, and add buttons. `search()` remains usable when hidden. |
| `enable_drag` | `True` | Enable handle-only card dragging when `move_cards` is also enabled. Menu/API movement remains available when only dragging is off. |
| `column_width` | `320` | Column width in widget pixels; integer at least `220`. |
| `column_height` | `500` | Minimum board-column height; integer at least `240`. |
| `editor_width` | `420` | Width of the embedded drawer; integer at least `320`. |

### Text settings

| Setting | Default |
| --- | --- |
| `board_title` | `"Board"` |
| `search_placeholder` | `"Search cards…"` |
| `add_card` | `"+  Add card"` |
| `add_column` | `"Add column"` |
| `no_columns` | `"No columns yet"` |
| `no_columns_help` | `"Create a column to start planning"` |
| `no_cards` | `"No cards yet"` |
| `no_cards_help` | `"Add a card to get started"` |
| `no_results` | `"No results"` |
| `no_results_help` | `"Try another search"` |

Every text setting must be a string. These are the stable application-facing
labels; short mechanical labels inside the editor and context menus are not
currently configurable.

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
the corresponding structured setting when explicitly supplied. The two
`allow_*_deletion` arguments override `actions.delete_cards` and
`actions.delete_columns`. Remaining keyword arguments are forwarded to the
outer `CTkFrame` after the board supplies its default `fg_color`.

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

### Field types and stored values

| Type | Generated editor control | Normalized stored value |
| --- | --- | --- |
| `text` | Single-line entry | Trimmed `str`; `None` becomes `""`. |
| `textarea` | Multi-line textbox | Trimmed `str`; `None` becomes `""`. |
| `number` | Entry | `float`, or `None` when blank. Booleans are rejected. |
| `integer` | Entry | `int`, or `None` when blank; a fractional float is rejected. |
| `select` | Option menu | The selected value. Non-empty `options` are enforced. |
| `multiselect` | Add/remove pill input | Deduplicated `list`; non-empty `options` are enforced on save. |
| `date` | Entry | ISO `YYYY-MM-DD` string or `""`; accepts `datetime.date` input. |
| `datetime` | Entry | ISO date-time string or `""`; accepts `datetime.datetime` and `Z` input. |
| `checkbox` | Checkbox | Strict `bool`. |
| `tags` | Add/remove tag pills | Deduplicated `list[str]`; values are trimmed, nonblank, and comma-free. |
| `hidden` | Hidden by default | Deep-copied application value; useful for schema-controlled values without UI. |

Date and date-time controls are plain text entries, so validation occurs on
save. `multiselect` uses the same compact add/remove interaction as tags;
invalid choices are reported when the schema validates the completed card.

### Field definition reference

Every definition requires a unique, nonblank `key` and `label`.

| Option | Default | Meaning |
| --- | --- | --- |
| `type` | `"text"` | One of the eleven types above. |
| `required` | `False` | Reject `None`, `""`, and `[]`. The title is always required. |
| `default` | Type default | Deep-copied when the field is absent. Lists default to `[]`, checkbox to `False`, numeric fields to `None`, and other controls to `""` in a new editor. |
| `placeholder` | `""` | Entry hint; list fields fall back to `"Add a value"`. |
| `options` | `()` | Sequence of allowed `select` or `multiselect` values. An empty sequence means unrestricted validation. |
| `show_on_card` | Role-dependent | Render the value on the compact card. Defaults to true unless the role is `hidden`. |
| `show_in_editor` | Type-dependent | Generate an editor control. Defaults to false only for `hidden`. |
| `searchable` | `False` | Include the field in local case-insensitive substring search. |
| `read_only` | `False` | Disable its generated control while retaining the value. Give required read-only fields a default for new cards. |
| `section` | `"Details"` | Drawer section heading. Sections follow first appearance; column selection is in `Organisation`. |
| `card_role` | `metadata` or `hidden` | Compact-card presentation role. A visible field defaults to `metadata`; otherwise `hidden`. |
| `help_text` | `""` | Supporting editor text; for checkboxes it becomes the checkbox label. |
| `min`, `max` | unset | Inclusive numeric limits for `number` and `integer`. |
| `min_length`, `max_length` | unset | Inclusive character/item count limits for strings and lists. |
| `validator` | unset | Callable `(value, card) -> bool | str | None`; `False` gives a generic error and a string becomes the error message. |
| `formatter` | unset | Callable `(value, card) -> str` used only for compact-card display. |
| `colors` | `{}` | Mapping from exact field values to CustomTkinter-compatible pill/accent colors. |

Unknown definition options are rejected so spelling mistakes cannot silently
change behavior. `min` must not exceed `max`, length limits must be
nonnegative, and the lower length limit must not exceed the upper one.
Validators run in field order and should be fast and side-effect free because
they also run during load and schema replacement.

```python
def estimate_validator(value, card):
    if value is not None and card.get("blocked") and value > 8:
        return "Blocked work must be split into estimates of 8 or less"
    return True


fields = [
    {"key": "title", "label": "Title", "required": True},
    {"key": "blocked", "label": "Blocked", "type": "checkbox"},
    {
        "key": "estimate",
        "label": "Estimate",
        "type": "integer",
        "validator": estimate_validator,
        "formatter": lambda value, _card: "" if value is None else f"{value} pts",
        "show_on_card": True,
        "card_role": "metadata",
    },
]
```

### Compact-card roles

| Role | Presentation |
| --- | --- |
| `title` | Main heading. Exactly one field has this role and its key must be `title`. |
| `body` | Wrapped body line, truncated by `card_description_max_chars`. Multiple body fields are supported. |
| `badge` | Colored pill; the first non-empty visible badge also colors the card's accent strip. |
| `tags` | One `#value` pill per item, capped per field by `card_max_visible_tags`. |
| `metadata` | Pill formatted as `Label: value`. |
| `hidden` | No compact representation. |

Only fields with `show_on_card=True` render, regardless of role. Empty values
are omitted. `formatter` changes display text but never the normalized stored
value. A field's `colors` mapping takes precedence for its exact value; the
default `priority` field otherwise uses the priority theme colors.

`id`, `column`, and `column_id` are reserved structural keys. If `title` is
not supplied in `fields`, the default title definition is inserted. The title
must use `text` or `textarea`, is forced to `required=True` and
`show_on_card=True`, and must be the only field with `card_role="title"`.

Additional card keys that are not in the schema are deep-copied and preserved
in snapshots. This lets applications round-trip private integration metadata
without showing, validating, formatting, or searching it. Add a definition
whenever the board should understand such a value.

Use `get_fields()` to inspect the active definitions and `set_fields(fields)`
to replace them at runtime. `set_fields()` validates existing cards atomically,
rebuilds their compact views, and rebuilds an open editor with the new controls.
If schema normalization changes stored card values, one `fields_changed` event
is emitted so the host can persist the new snapshot.

`get_fields()` returns a detached copy. Mutating that copy has no effect until
it is passed back to `set_fields()`. A failed replacement leaves both the old
schema and every card unchanged. Changing a schema can add defaults, coerce
values, or reject existing data; plan schema migrations the same way you would
plan a database migration.

## Data contract and ordering

A snapshot is exactly one mapping with `columns` and `cards` keys:

```python
snapshot = {
    "columns": [
        {"id": "todo", "title": "To do"},
        {"id": "done", "title": "Done"},
    ],
    "cards": [
        {"id": 1, "column": "todo", "title": "Write docs"},
    ],
}
```

Extra top-level snapshot keys and extra column keys are rejected. A column has
only `id` and `title`; titles are trimmed and must remain nonblank. A card must
have `id`, a column reference, and a nonblank title. Input may use `column_id`
as an alias for `column`; output always uses `column`. Supplying both aliases
with different values is an error.

IDs must be unique within their record kind and must be a nonblank `str` or an
`int`; booleans, floats, `None`, and other objects are rejected. IDs are not
coerced, so `1` and `"1"` are distinct. Use only strings or integers when
serializing to JSON and keep the same type in related card/column values.

With the default field schema, cards normalize `title`, `description`,
`priority`, and `tags`. Priority is case-sensitive and must be empty, `Low`,
`Medium`, `High`, or `Critical`. A custom schema controls its configured keys;
all other card keys are preserved as application metadata.

### Snapshots, copies, and atomic replacement

`get_data()` and `BoardModel.snapshot()` return deep, detached state. The
record getters and returned mutation records are detached too, so changing
them never mutates the live board. Call a mutation method or `set_data()` to
apply a change.

`set_data(snapshot)` validates the entire replacement before changing the
model and redraws without emitting `on_change`. Invalid replacement data leaves
the old board intact. The snapshot shape must be complete; use empty lists to
clear a board. `BoardModel.load()` additionally supports the explicit form
`load(columns=..., cards=...)`, but snapshot and explicit arguments cannot be
mixed.

### Manual ordering

Column input order is retained. Card order is retained within each column and
global `get_cards()` output is grouped by current column order. `index` values
are zero-based insertion positions; `None` appends. Valid insertion positions
range from zero through the destination size, inclusive. An out-of-range or
non-integer index raises `BoardModelError`.

`update_card()` merges its mapping into the existing record; it does not
replace unspecified values. A changed `column` appends the card to that column,
while `move_card()` accepts an exact insertion index. `update_column()` only
accepts `title`. Non-empty columns require the explicit
`delete_cards=True` cascade flag before deletion.

## Change events and persistence

Pass one `on_change(event)` callback to observe successful board mutations.
Every event contains a detached `before` snapshot, the current complete `data`
snapshot, its `type`, and the operation payload:

| Event type | Additional payload |
| --- | --- |
| `card_added` | `card` |
| `card_updated` | `card`, `previous` |
| `card_deleted` | `card` (the removed record) |
| `card_moved` | `card`, `previous` |
| `column_added` | `column` |
| `column_updated` | `column`, `previous` |
| `column_deleted` | `column`; any cascaded cards remain available in `before` |
| `column_moved` | `column` |
| `fields_changed` | `fields` (the new definitions), emitted only if schema normalization changed stored cards |

No event is emitted for a no-op update or move, `set_data()`, a schema change
that leaves card data identical, search, selection, rendering, or loading-state
changes. The board state has already changed when the callback runs. Callback
exceptions are logged and do not roll back the mutation.

```python
def persist(event):
    try:
        repository.save_snapshot(event["data"])
    except Exception:
        # Optional application policy: restore the last detached state.
        board.set_data(event["before"])
        raise


board = CTkKanbanBoard(app, columns=columns, cards=cards, on_change=persist)
```

`on_change` runs on Tk's UI thread, so synchronous network or database work
will freeze the interface. For nontrivial persistence, enqueue `event["data"]`
to an application worker and decide how your application handles failures,
retries, coalescing, optimistic concurrency, and conflicts. CTkKanban does not
save, poll, page, retry, or resolve conflicts itself.

## Database rows

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

| Adapter | Behavior |
| --- | --- |
| `normalize_row(row)` | Copies a mapping, an object with `_mapping`, or a keys/index row to `dict[str, Any]`. Plain tuples have no names and raise `TypeError`. |
| `normalize_rows(rows)` | Applies `normalize_row()` to an iterable. |
| `rows_from_cursor(cursor)` | Requires an executed result with `description`, verifies unique column names, calls `fetchall()`, and zips each tuple to those names. |
| `snapshot_from_rows(columns, cards, *, fields=None)` | Normalizes rows, validates them through a temporary `BoardModel`, and returns its detached snapshot. |
| `snapshot_from_cursors(columns_cursor, cards_cursor, *, fields=None)` | Consumes two separately executed cursor results and delegates to `snapshot_from_rows()`. |

Pass the same `fields` used by the board so database values receive identical
normalization. SQL drivers may return JSON/array values in driver-specific
forms; convert them to the expected Python list, boolean, number, or string in
the query/repository layer when necessary. Neither adapter executes SQL,
commits, closes a cursor, nor owns a connection.

## Asynchronous loading

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

`load_async()` returns the started daemon `threading.Thread`. The fetch
callable receives no arguments and must return a complete snapshot mapping. It
runs off-thread and must not read or update Tk widgets. Validation uses the
board field schema; application of the validated snapshot plus `on_success` or
`on_error` happens on Tk's event loop. Successful loads use `set_data()` and
therefore do not emit `on_change`.

At the start of a load, `load_error` is cleared and `is_loading` becomes true.
On failure, the original exception is stored and passed to `on_error`; with
`clear_on_error=True`, the board is replaced with empty lists first. A newer
load invalidates delivery from older workers but does not forcibly stop their
Python threads. Destroying the board invalidates pending delivery, and starting
a load after destruction raises `RuntimeError`.

`set_loading(True)` is also public for application-owned tasks. It changes the
toolbar presentation and disables its search/add controls; it does not start a
worker, block public mutations, or alter data.

Pass `on_card_open` when the host application owns card editing. Its callback
receives the card snapshot and replaces the built-in drawer when a card opens.

## API reference

### `CTkKanbanBoard` constructor

```python
CTkKanbanBoard(
    master,
    columns=(),
    cards=(),
    *,
    on_change=None,
    on_card_open=None,
    theme=None,
    fields=None,
    config=None,
    show_toolbar=None,
    enable_drag=None,
    column_width=None,
    column_height=None,
    editor_width=None,
    confirm_delete=None,
    allow_card_deletion=None,
    allow_column_deletion=None,
    board_title=None,
    **kwargs,
)
```

`master` is the parent Tk widget. `columns` and `cards` provide initial state;
all other inputs are keyword-only. `theme`, `fields`, and `config` use the
contracts above. `on_change` receives event dictionaries, and `on_card_open`
receives a detached card record in place of the built-in existing-card editor.
Direct layout/text/deletion options take precedence over structured config.

### Board data, view, and schema methods

| Member | Return | Behavior |
| --- | --- | --- |
| `get_data()` | `BoardSnapshot` | Detached complete state. |
| `set_data(data)` | `None` | Atomically validate, replace, and redraw without an event. |
| `get_card(card_id)` | `CardRecord | None` | Detached record, or `None` for an invalid/unknown ID. |
| `get_cards(column_id=None)` | `list[CardRecord]` | Ordered detached records; an unknown explicit column raises. |
| `get_columns()` | `list[ColumnRecord]` | Ordered detached records. |
| `get_fields()` | `list[dict[str, Any]]` | Detached normalized definitions. |
| `set_fields(fields)` | `None` | Atomic schema replacement, redraw, and optional `fields_changed` event. |
| `get_selected_card()` | `CardRecord | None` | Current detached selection, if it still exists. |
| `search(query)` | `None` | Set case-insensitive local search; non-string values are converted with `str()`. |
| `refresh(preserve_scroll=True)` | `None` | Rebuild structural widgets from current model state. Ordinary public mutations already refresh what they need. |

### Board mutation methods

| Member | Return | Notes |
| --- | --- | --- |
| `add_card(card, *, index=None)` | `CardRecord` | Add to `card["column"]` at an insertion position. |
| `update_card(card_id, updates)` | `CardRecord` | Merge fields. Changing column additionally requires move permission. |
| `move_card(card_id, column_id, index=None)` | `CardRecord` | Move/reorder, appending when index is omitted. |
| `delete_card(card_id)` | `CardRecord` | Remove and return the old record; no confirmation prompt. |
| `add_column(column, *, index=None)` | `ColumnRecord` | Add at an insertion position. |
| `update_column(column_id, updates)` | `ColumnRecord` | Rename from `{"title": ...}`. |
| `move_column(column_id, index)` | `ColumnRecord` | Reorder to an exact position. |
| `delete_column(column_id, *, delete_cards=False)` | `ColumnRecord` | Empty-only unless cascade is explicit; no confirmation prompt. |

Each board mutation enforces its action setting and emits the corresponding
event only when data changes.

### Board editor and loading methods

| Member | Return | Behavior |
| --- | --- | --- |
| `open_add_card_editor(column_id=None)` | `None` | Open the generated drawer. If no column exists and adding columns is allowed, prompt for one first. |
| `open_edit_card_editor(card_id)` | `None` | Open the drawer or invoke `on_card_open`; invalid/unknown IDs are ignored. |
| `open_add_column_dialog()` | `None` | Prompt for a title and create a UUID-backed column. |
| `is_loading` | `bool` | Read-only property describing pending async delivery/manual presentation. |
| `load_error` | `Exception | None` | Most recent async load error; cleared when a new load starts. |
| `set_loading(loading)` | `None` | Toggle presentation; requires a real boolean. |
| `load_async(fetch_snapshot, *, on_success=None, on_error=None, clear_on_error=False)` | `threading.Thread` | Start validated background loading. |
| `destroy()` | `None` | Cancel scheduled delivery and editor motion, release menus/grabs/scroll bindings, and tear down widgets. Safe to call more than once. |

### `BoardModel`

The Tk-free `BoardModel(columns=(), cards=(), *, fields=None)` is useful in
repositories, tests, command-line tools, and preprocessing layers. It supplies:

```text
snapshot()
load(data=None, *, columns=None, cards=None)
get_card(card_id) / get_cards(column_id=None) / get_columns()
get_fields() / set_fields(fields)
add_card(card, *, index=None)
update_card(card_id, updates=None, **changes)
delete_card(card_id)
move_card(card_id, column_id, index=None)
reorder_card(card_id, index)
add_column(column, *, index=None)
update_column(column_id, updates=None, **changes)
delete_column(column_id, *, delete_cards=False)
move_column(column_id, index)
clear()
```

Unlike the widget's forgiving `get_card()`, `BoardModel.get_card()` raises
`BoardModelError` for an invalid or unknown ID. The model does not enforce
`BoardConfig` permissions or emit events. Its `update_card()` and
`update_column()` accept keyword changes in addition to an optional mapping;
model `update_column()` also accepts a title string directly.

### Public records and helpers

| Name | Kind and purpose |
| --- | --- |
| `Column` | Frozen dataclass with `id` and `title`; `from_definition()` validates and trims a mapping. |
| `Card` | Frozen compatibility dataclass for the four default fields; tags are a tuple. It is not a container for arbitrary schema fields. |
| `ColumnRecord` | `TypedDict` output with `id` and `title`. |
| `CardRecord` | `dict[str, Any]` because schema and private values are dynamic. |
| `BoardSnapshot` | `TypedDict` with `columns` and `cards` lists. |
| `FieldDefinition` | `TypedDict` describing a generated field. |
| `FieldType` | Literal union of supported field type strings. |
| `DEFAULT_FIELDS` | Tuple containing detached-compatible definitions for title, description, priority, and tags. |
| `ActionConfig`, `LayoutConfig`, `TextConfig`, `BoardConfig` | Frozen configuration dataclasses. |
| `DEFAULT_THEME` | Import-time dictionary of all theme defaults/tokens. |
| `merge_config()`, `merge_theme()` | Strict validation/merge helpers. |
| `normalize_row()`, `normalize_rows()`, `rows_from_cursor()` | Row-to-dictionary adapters. |
| `snapshot_from_rows()`, `snapshot_from_cursors()` | Schema-aware snapshot adapters. |
| `__version__` | Installed CTkKanban version string. |

`Card.from_definition()` intentionally uses the default schema and returns the
fixed dataclass. Use a `BoardModel(fields=...)` when custom keys must remain in
the result.

## Errors and lifecycle

`BoardModelError` subclasses `ValueError` and is raised for invalid records,
schemas, IDs, indices, relationships, updates, protected deletions, and board
actions disabled by configuration. Configuration helpers also use `TypeError`
for incorrect value kinds and `ValueError` for invalid names/ranges. Theme
helpers reject unknown token names with `ValueError`; CustomTkinter may report
invalid token values later while constructing a widget.

Editor validation errors are shown in the drawer and keep it open. Public
method errors are not swallowed. `on_change` and `on_card_open` callback
exceptions are logged so the Tk interaction can finish; async success/error
callbacks are application code and should handle their own failures.

All widget construction, mutations, and direct UI access should occur on the
Tk thread. `load_async()` is the provided exception: only its fetch callable
runs in a daemon worker, and that callable must stay independent of Tk.
Call `destroy()` during normal widget teardown; it invalidates outstanding
async delivery and cleans up window-level bindings and local drag state.

## Migrating from 1.x

Version 2 is intentionally breaking. Replace mutation-specific callbacks with
`on_change`, and import from `ctk_kanban` rather than `CTkKanBan`. The focused
2.0 API initially removed dynamic fields; the current schema API restores that
capability without restoring the former persistence, filtering, sorting, and
large constructor-flag frameworks. Custom record keys are now preserved.

| 1.x concept | Current replacement |
| --- | --- |
| `from CTkKanBan import ...` | `from ctk_kanban import ...` |
| Dynamic/generated fields | The smaller `fields` schema documented above. |
| Inline and popup editing modes | One embedded explicit-save drawer, or `on_card_open`. |
| Mutation-specific callbacks | One `on_change(event)` callback with before/current snapshots. |
| Built-in persistence/data sources | Application repositories plus snapshots, row adapters, and `load_async()`. |
| Advanced filters/sorts | Schema-aware local search and manual order; transform source data in the host. |
| Many constructor booleans | `BoardConfig` plus a small compatibility override set. |

Migrate stored records by aliasing each card's owning value to `column`, keep
IDs stable and type-consistent, and add field definitions for values that need
UI, validation, search, or compact display. Leave integration-only keys
undefined in the schema if they only need to round-trip.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy ctk_kanban
python -m build
```

Release maintainers should also read [`docs/publishing.md`](docs/publishing.md).
The changelog records user-visible behavior in [`CHANGELOG.md`](CHANGELOG.md).
