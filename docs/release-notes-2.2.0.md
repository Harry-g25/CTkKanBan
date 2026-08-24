# CTkKanban 2.2.0

CTkKanban 2.2.0 makes database-backed cards and custom forms easier to build,
while improving layout, scrolling, and rendering responsiveness.

## Highlights

- Define card content concisely with the fluent `Field` builder, immutable
  `CardField` values, or string shorthand. A custom database key can now be the
  card title.
- Create a board directly from mappings, `sqlite3.Row`, SQLAlchemy rows, or
  executed DB-API cursors with `CTkKanbanBoard.from_rows()`. Use `card_keys`
  and `column_keys` to keep existing database column names.
- Handle card clicks with the simple `on_card_open(card)` callback. Set
  `use_builtin_editor=False` when the application should own the form.
- Use `fill_columns=True` to divide available horizontal space equally while
  retaining horizontal overflow on narrower windows.
- Keep columns vertically filled and centred when the editor opens and closes.
- Navigate with wider scrollbars, resize-aware horizontal scrolling, and
  axis-aware wheel behavior.
- Benefit from lower card/editor creation overhead and widget reuse during
  search.

## Try the focused examples

The [`examples`](../examples/README.md) directory includes runnable programs
for a basic board, all generated field controls, an in-memory SQLite workflow,
a custom editor, and asynchronous loading. The repository-root `example.py`
remains the complete visual showcase.

## Compatibility

This is a backward-compatible 2.x feature release. Existing boards can keep
using mapping field definitions and the built-in editor. The default title,
description, priority, and tags schema is unchanged when `fields` is omitted.

Install or upgrade with:

```bash
python -m pip install --upgrade CTkKanBan==2.2.0
```

See the [changelog](../CHANGELOG.md) for the exact change list and the
[documentation](index.html) for the full API and tutorials.
