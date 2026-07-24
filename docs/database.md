# Database Integration

`CTkKanbanBoard` can run in memory, use the legacy snapshot callback, or connect to one `KanbanDataSource`. Database-backed applications should use the data-source API because it keeps blocking work off Tk's UI thread and persists focused operations instead of rewriting the whole board.

## SQLite Quick Start

```python
import customtkinter as ctk
from ctk_kanban import CTkKanbanBoard, SQLiteKanbanDataSource

app = ctk.CTk()
source = SQLiteKanbanDataSource("kanban.db")
source.seed_board(
    "work",
    [{"id": "todo", "title": "To Do"}, {"id": "done", "title": "Done"}],
    replace=False,
)

board = CTkKanbanBoard(
    app,
    data_source=source,
    board_id="work",
    actor_id="desktop-user-17",
    auto_load=True,
    server_side_query=True,
    page_size=100,
    poll_interval_ms=2000,
    completed_columns=["done"],
    timezone_name="Europe/London",
    locale_name="en_GB",
)
board.pack(fill="both", expand=True)
app.mainloop()
```

The SQLite adapter creates its schema automatically. Writes are transactional, batches are atomic, and each board has a monotonically increasing revision.

## Data-Source Contract

Implement `KanbanDataSource` for PostgreSQL, SQL Server, REST, or another backend:

```python
class KanbanDataSource(Protocol):
    def load_board(self, board_id, query=None): ...
    def apply_mutation(self, event): ...
    def apply_batch(self, events): ...
    def query_cards(self, board_id, query): ...
    def get_changes(self, board_id, since_revision): ...
```

Return the typed contracts exported from `ctk_kanban`: `BoardLoadResult`, `CardPage`, `MutationResult`, `ConflictDetails`, and `ChangePage`.

## Mutation Metadata

Every write includes:

- `event_id`: unique mutation identifier for idempotency and logs.
- `transaction_id`: groups related operations and atomic batches.
- `board_id`: durable board identity.
- `actor_id`: user, process, or device responsible for the change.
- `expected_revision`: optimistic concurrency check.
- `timestamp`: UTC timestamp.
- `source`: UI, drag, API, undo, redo, or another caller-defined source.

Create operations may start with temporary IDs. Return a canonical card in `MutationResult.card` or an `id_map`; the board remaps selection and widgets without duplicating the card.

## Conflicts

The SQLite adapter rejects stale `expected_revision` values and returns current server state. Configure `conflict_strategy` as `"server_wins"`, `"local_wins"`, or `"callback"`. Use `on_conflict` with callback mode for a domain-specific merge UI.

Immutable card and column IDs are enabled by default. This avoids accidental primary-key changes; use the explicit remapping APIs only when a backend replaces a temporary ID.

## Reliability

The persistence coordinator uses one worker so mutation order is preserved. Transient connection failures use bounded exponential retry, then remain in an in-memory offline queue. Call `board.set_online(True)` after connectivity returns or use the toolbar Retry action. The local board remains visible while offline, but queued operations are process-local and are lost if the application exits; use a durable outbox in the application or adapter when crash recovery is required.

`disable_while_saving=True` prevents duplicate writes. Persistence callbacks expose saving, saved, offline, conflict, and error states. Application logs receive structured event, transaction, board, actor, and revision context.

## Querying and Scale

With `server_side_query=True`, search, advanced filters, sort, paging, and per-column totals are delegated to the adapter. `load_next_page()` appends the next page. Sparse numeric ranks let one moved card be persisted without renumbering every sibling.

Polling uses `get_changes()` and `poll_interval_ms`; it refreshes when another client advances the board revision. For push-based systems, call `refresh_from_source()` from your notification handler.

## Production Checklist

- Use one persistence writer per board.
- Treat `event_id` as an idempotency key in remote systems.
- Enforce `expected_revision` in the same transaction as the write.
- Return canonical IDs, timestamps, defaults, and versions from the backend.
- Keep adapter methods blocking and thread-safe; the coordinator owns threading.
- Store UTC timestamps and configure `timezone_name` and `locale_name` for display.
- Implement `apply_batch(events)` as one transaction and reject the entire list if any event cannot be applied.
- In-memory boards accept hashable IDs; the built-in SQLite adapter requires non-empty string or integer IDs so they round-trip through durable storage.
- Test disconnect, retry, stale revision, duplicate submission, and remote-change paths.
