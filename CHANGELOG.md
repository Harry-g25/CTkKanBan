# Changelog

Historical note: the existing `v1.0.0` Git tag contains package version
`0.3.0`. The older entries below describe repository milestones; they do not
confirm that matching distributions were published to PyPI.

## Unreleased

- Replaced the hard-coded blue board palette with the active CustomTkinter theme.
- Restored colored priority and tag pills on cards.
- Made dragging and manual category changes update only the affected UI state.
- Replaced the separate card editor window with an embedded right-side drawer.

## 2.0.0 - 2026-08-06

- Rebuilt the project around a small Tk-free board model and one predictable rendering path.
- Replaced inline editing with one explicit-save card editor.
- Restricted card dragging to a visible handle and added dependable menu-based movement.
- Replaced the callback and persistence framework with one `on_change` application boundary.
- Removed advanced persistence, querying, generated forms, the legacy rendering framework, and configuration machinery.
- Reduced the public package surface and made `ctk_kanban` the sole import name.

## 1.0.0 - 2026-07-24

- Added live, field-aware editing inside default cards, including empty-field placeholders, typed controls, keyboard save/cancel behavior, validation feedback, and persistence through the normal card update pipeline.
- Added `enable_inline_card_editing` and `start_inline_card_edit()` while retaining the explicit popup and side-panel form APIs for compatibility.
- Kept invalid inline edits from triggering release-driven host controls under CustomTkinter 6 while preserving CustomTkinter 5 behavior.

## 0.3.0 - 2026-07-24

- Added `CRUDKanbanDataSource`, a four-callback bridge for connecting existing SQL, NoSQL, ORM, and API repositories without implementing the full persistence protocol.
- Hardened SQLite mutation replay, schema migration, conflict snapshots, batch rollback, identifier validation, and offline queue ordering.
- Fixed paged-board totals, offsets, undo/redo persistence, column rename handling, timestamp sorting, dirty-form replacement, and style snapshots.
- Expanded supported CustomTkinter releases through 6.x and strengthened source/wheel validation, compatibility testing, documentation checks, and release smoke tests.
- Added cross-platform CI for Python 3.10 through 3.14, branch coverage, dependency auditing, installed-wheel smoke tests, and package validation.
- Added CodeQL scanning, Dependabot, workflow security linting, GitHub Pages deployment, and repository contribution templates.
- Added trusted TestPyPI and PyPI publishing with protected environments, artifact attestations, checksums, and automated GitHub releases.
- Added local tox environments and release preparation, validation, and installed-package smoke-test scripts.

## 0.2.0 - 2026-06-14

- Added typed mutation, result, conflict, query, paging, and load contracts.
- Added threaded data-source coordination, retries, offline queueing, polling, canonical IDs, and optimistic concurrency.
- Added a transactional SQLite adapter and runnable database example.
- Added sparse card ranking, atomic batches, undo/redo, immutable IDs, timestamps, and revisions.
- Added persistence status, filter chips, active sort and result summaries, search clearing and highlighting.
- Added responsive and adjustable columns, drag handles, WIP/lock indicators, and invalid-drop feedback.
- Added date picking, field-level validation, dirty-form protection, and normalized optional values.
- Redesigned the default light and dark appearance with layered surfaces, priority rails, metadata tiles, compact toolbar states, polished columns, and cohesive forms.
- Added visual-state regression coverage and light/dark/form showcase modes.
- Added integration, performance, reliability, and usability tests.

## 0.1.0

- Initial configurable CustomTkinter Kanban board.
