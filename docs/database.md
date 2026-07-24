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

## Bring Your Own CRUD

`CRUDKanbanDataSource` is the shortest route when your application already has a database connection,
ORM model, repository, document collection, or remote API. You provide four ordinary callbacks and the
bridge implements the board-specific data-source contract:

```python
from ctk_kanban import CRUDKanbanDataSource


def read_board(board_id):
    return {
        "columns": repository.list_columns(board_id),
        "cards": repository.list_cards(board_id),
        "revision": repository.get_revision(board_id),  # Optional
    }


def create(resource, board_id, record, context):
    # resource is "card" or "column".
    # Return the stored record so generated IDs/defaults reach the board.
    return repository.insert(
        resource,
        board_id,
        record,
        position=context.position,
        transaction=context.transaction,
    )


def update(resource, board_id, record_id, record, context):
    return repository.update(
        resource,
        board_id,
        record_id,
        record,
        position=context.position,
        transaction=context.transaction,
    )


def delete(resource, board_id, record_id, context):
    repository.delete(
        resource,
        board_id,
        record_id,
        transaction=context.transaction,
    )


source = CRUDKanbanDataSource(
    read=read_board,
    create=create,
    update=update,
    delete=delete,
)

board = CTkKanbanBoard(
    app,
    data_source=source,
    board_id="work",
    auto_load=True,
)
```

This works with relational, document, key-value, graph, cloud, or HTTP-backed storage because CTkKanban
does not open the connection or generate database-specific queries. The callbacks own that small part.
The bridge handles the rest:

- Card and column create, read, update, and delete dispatch.
- Card moves/reorders as focused updates.
- Column ordering through `context.position`.
- Column ID changes and their affected card records.
- Generated IDs when `create` returns a canonical stored record.
- Search, filters, sorting, paging, and per-column totals over `read_board`.
- Batch ID rebasing and an optional shared transaction.
- Revision-based polling, or an optional custom `changes` callback.

Write callbacks may return:

- A record mapping: successful write with canonical database values.
- `None` or `True`: successful write using the submitted record.
- `False`: rejected write; the board restores its prior UI state.
- `MutationResult`: advanced control over conflicts, revisions, changed records, and retryability.

Every callback receives `CRUDContext`. Its `metadata` property exposes the event ID, transaction ID,
actor, expected revision, source, and timestamp. Use `event_id` as an idempotency key and enforce
`expected_revision` inside the same transaction when concurrent writers matter.

### Optional Transactions

Pass a context-manager factory to make a board batch use one database transaction. The object yielded
by the context manager is available as `context.transaction` in every write callback:

```python
from contextlib import contextmanager


@contextmanager
def transaction(events):
    with repository.begin() as session:
        yield session


source = CRUDKanbanDataSource(
    read=read_board,
    create=create,
    update=update,
    delete=delete,
    transaction=transaction,
)
```

If any callback rejects a write, the bridge raises inside this context so its normal rollback behavior
runs, then returns the rejection to the board.

## Data-Source Contract

Implement `KanbanDataSource` directly when the backend should own server-side queries, native bulk
writes, durable event history, optimistic-conflict snapshots, or a change stream:

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
- With `CRUDKanbanDataSource`, provide `transaction` if multi-record writes must be atomic.
- In-memory boards accept hashable IDs; the built-in SQLite adapter requires non-empty string or integer IDs so they round-trip through durable storage.
- Test disconnect, retry, stale revision, duplicate submission, and remote-change paths.
