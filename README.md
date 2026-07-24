# CTkKanban

[![CI](https://github.com/Harry-g25/CTkKanBan/actions/workflows/ci.yml/badge.svg)](https://github.com/Harry-g25/CTkKanBan/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Harry-g25/CTkKanBan/actions/workflows/codeql.yml/badge.svg)](https://github.com/Harry-g25/CTkKanBan/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/ctk-kanban.svg)](https://pypi.org/project/ctk-kanban/)
[![Python](https://img.shields.io/pypi/pyversions/ctk-kanban.svg)](https://pypi.org/project/ctk-kanban/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/Harry-g25/CTkKanBan/blob/main/LICENSE)

CTkKanban is a configurable Kanban widget for CustomTkinter desktop applications. It ships with a polished adaptive light/dark design, generated forms, drag and drop, search, advanced filters, sorting, undo/redo, responsive columns, and database-backed operation.

The built-in design uses layered surfaces, priority-accented cards, responsive metadata tiles, column color rails, active filter treatments, and database status pills. Every visual token remains overridable through `style` or `theme`.

## Install

```bash
python -m pip install ctk-kanban
```

## In-memory board

```python
import customtkinter as ctk
from ctk_kanban import CTkKanbanBoard

app = ctk.CTk()
board = CTkKanbanBoard(
    app,
    columns=[{"id": "todo", "title": "To Do"}, {"id": "done", "title": "Done"}],
    cards=[{"id": 1, "column": "todo", "title": "Try CTkKanban"}],
    completed_columns=["done"],
)
board.pack(fill="both", expand=True)
app.mainloop()
```

## SQLite board

```python
import customtkinter as ctk
from ctk_kanban import CTkKanbanBoard, SQLiteKanbanDataSource

app = ctk.CTk()
source = SQLiteKanbanDataSource("kanban.db")
source.seed_board("work", [{"id": "todo", "title": "To Do"}], [])

board = CTkKanbanBoard(
    app,
    data_source=source,
    board_id="work",
    auto_load=True,
    server_side_query=True,
    poll_interval_ms=2000,
)
board.pack(fill="both", expand=True)
app.mainloop()
```

Database work runs outside Tk's UI thread. Mutations carry event, transaction, actor, board, and expected-revision metadata. Adapters may return canonical records with generated IDs, timestamps, versions, and defaults. Failed network writes can be retried or held in the process-local offline queue until connectivity returns.

The built-in SQLite adapter provides transactional writes, optimistic revisions, atomic batches, server-side search/filter/sort, paging, change polling, generated IDs, and automatic timestamps. The board shows saving, saved, offline, conflict, and error states; duplicate submissions are blocked while a mutation is pending.

Use only one durable writer: configure either `data_source` or the legacy `on_data_changed` callback, never both.

See the [database integration guide](https://github.com/Harry-g25/CTkKanBan/blob/main/docs/database.md) for the adapter contract, event shape, conflict policies, paging, polling, and a production integration checklist.

The example programs are included in the source repository and source distribution, not the installed wheel. From a [source checkout](https://github.com/Harry-g25/CTkKanBan), run `python example_all_features.py` for the UI showcase or `python example_sqlite.py` for the transactional database example.

Use `python example_all_features.py --light`, `--dark`, or `--form` to inspect specific appearance and form states. Add `--diagnose` to print the exact package path and version being rendered.

## Development

```bash
python -m pip install -e ".[dev]"
tox -e lint,type,py314,ctk-min,ctk-current,package
```

CI tests Python 3.10 through 3.14 on Linux and the oldest/latest supported versions on Windows and macOS. It also checks branch coverage, installed-wheel behavior, SQLite persistence, dependency vulnerabilities, package metadata, and workflow security.

See the [changelog](https://github.com/Harry-g25/CTkKanBan/blob/main/CHANGELOG.md), [contribution guide](https://github.com/Harry-g25/CTkKanBan/blob/main/CONTRIBUTING.md), [publishing runbook](https://github.com/Harry-g25/CTkKanBan/blob/main/docs/publishing.md), and [project documentation](https://harry-g25.github.io/CTkKanBan/).
