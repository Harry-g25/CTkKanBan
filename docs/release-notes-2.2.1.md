# CTkKanban 2.2.1

CTkKanban 2.2.1 is the corrective release for the 2.2 feature update. It
contains the concise field API, database-key mappings, custom card callbacks,
responsive columns, scrolling improvements, performance work, and focused
examples introduced for 2.2.

## Compatibility fix

CustomTkinter 6.0 removed the private `check_if_master_is_canvas()` method that
its 5.x scrollable frame exposed. CTkKanban's improved wheel routing called that
method, which caused scrollbar tests and release validation to fail whenever a
fresh environment resolved CustomTkinter 6.0.

CTkKanban now performs its own safe widget-ancestry check. Wheel routing no
longer depends on either the 5.x or 6.x private containment implementation, and
the behavior is covered by a dedicated regression test.

The release is validated against Python 3.10 and 3.14 with both the minimum
CustomTkinter 5.2.2 dependency and CustomTkinter 6.0.0.

Install or upgrade with:

```bash
python -m pip install --upgrade CTkKanBan==2.2.1
```

See the [2.2.0 release notes](release-notes-2.2.0.md) for the complete feature
tour, the [changelog](../CHANGELOG.md) for the exact history, and the
[documentation](index.html) for the full API and tutorials.
