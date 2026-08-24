# CTkKanban examples

Install the project in editable mode, then run any example from the repository
root:

```bash
python -m pip install -e ".[dev]"
python examples/basic_board.py
```

| Example | Practical coverage |
| --- | --- |
| [`basic_board.py`](basic_board.py) | Minimal construction, equal-width columns, change events, search, editing, and dragging. |
| [`custom_fields.py`](custom_fields.py) | Fluent `Field` definitions, `CardField`, custom title key, every generated input type, card roles, validation, formatting, and field visibility. |
| [`sqlite_board.py`](sqlite_board.py) | A real in-memory SQLite schema, direct cursor loading, database-key mappings, typed database columns, and persistence after edits/moves. |
| [`custom_editor.py`](custom_editor.py) | A schema-driven host-owned form using `get_field_data()`, column choices, read-only controls, validation feedback, and bulk `update_card()`. |
| [`async_loading.py`](async_loading.py) | Background snapshot fetching, loading state, success/error handling, and safe Tk-thread delivery. |
| [`../example.py`](../example.py) | Advanced all-in-one showcase for raw schema mappings, runtime schema replacement, structured permissions/text/layout, theming, and snapshots. |

The examples deliberately use in-memory or local data. CTkKanban does not own
database connections, transactions, network retries, or application
authorization. Keep those policies in the host application.
