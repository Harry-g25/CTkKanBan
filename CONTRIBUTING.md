# Contributing

Thanks for helping improve CTkKanban. Keep changes focused on a predictable,
reusable CustomTkinter widget rather than application-specific project
management behavior.

## Set up a development environment

1. Create and activate a virtual environment with Python 3.10 or newer.
2. Install the package and development tools:

   ```bash
   python -m pip install -e ".[dev]"
   ```

3. Run `python example.py` once to confirm Tk and CustomTkinter can open a
   window. Linux environments without a display can run the test suite under
   Xvfb instead.

## Architecture and scope

- `ctk_kanban/model.py` owns validation, relationships, snapshots, and manual
  ordering without importing Tk.
- `ctk_kanban/fields.py` owns field-schema validation, value normalization, and
  compact-display formatting.
- `ctk_kanban/config.py` owns strict action, layout, and text configuration.
- `ctk_kanban/board.py` coordinates the model, UI, permissions, events, and
  Tk-thread delivery.
- `card.py`, `column.py`, and `editor.py` render focused components; keep their
  state derived from the model and field schema.
- `adapters.py` converts already-fetched rows. It must stay independent of any
  particular database driver.
- `themes.py` defines the closed visual-token surface.

Schema-generated card controls are a supported core feature. Add a new field
type only when its normalization, editor behavior, compact rendering, search,
typing, documentation, and tests form one coherent contract.

Keep persistence, connections, network clients, retries, polling, paging,
authentication, authorization, and application-specific workflows in host
applications. Small format-neutral row/snapshot helpers and safe async snapshot
delivery are within scope. Keep gestures attached to explicit controls and
avoid window-wide interaction bindings.

## Make a change

1. Add focused tests for the behavior before or with the implementation. Model
   behavior should normally have Tk-free tests; widget interaction belongs in
   GUI tests.
2. Preserve atomicity for full-data and field-schema replacement. Public
   getters and callbacks must continue to expose detached records/snapshots.
3. Preserve action-config enforcement in both visible controls and the
   corresponding public board methods. Remember that configuration is not an
   authorization boundary.
4. Update both `README.md` and `docs/index.html` for public API or behavior
   changes. `tests/test_documentation.py` checks exports, methods, constructor
   options, field/config/theme/event coverage, links, navigation, and HTML
   structure.
5. Add a concise user-visible entry under `## Unreleased` in `CHANGELOG.md`.
6. Do not commit build outputs from `build/`, `dist/`, or egg-info directories.

## Validate before opening a pull request

Run:

```bash
python -m pytest -q
python -m ruff check ctk_kanban tests scripts example.py
python -m mypy ctk_kanban
python -m build
python -m twine check dist/*.whl dist/*.tar.gz
```

`tox` runs the standard test and quality environments. On Linux without an
active display, use `xvfb-run -a python -m pytest -q` for GUI tests. Also open
`docs/index.html` locally after changing its layout or navigation and manually
exercise `example.py` after user-visible widget changes.

Pull requests should explain the user problem, the chosen behavior, any
compatibility impact, and how the change was verified. Keep unrelated cleanup
separate so review remains clear.
