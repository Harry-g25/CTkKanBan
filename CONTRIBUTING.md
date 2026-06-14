# Contributing

1. Create a virtual environment with Python 3.10 or newer.
2. Install the project in editable mode: `python -m pip install -e ".[dev]"`.
3. Keep public mutations database-neutral and operation-first.
4. Add focused tests for behavior, rollback, thread boundaries, and widget identity.
5. Run `tox -e lint,type,py314,package` before opening a change.

Tk widgets must only be touched by Tk's owning thread. Persistence adapters may block because the coordinator runs them on a dedicated worker.

Do not introduce a second persistence writer into a board. Use a `KanbanDataSource` or the legacy `on_data_changed` callback.

User-visible changes belong under `## Unreleased` in `CHANGELOG.md`. See [docs/publishing.md](docs/publishing.md) for TestPyPI and production release steps.
