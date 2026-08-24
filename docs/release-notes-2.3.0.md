# CTkKanban 2.3.0

CTkKanban 2.3.0 makes application-owned card forms schema-aware, completes the
move to CustomTkinter 6, and substantially reduces unnecessary widget and
snapshot work during normal board interaction.

## Schema-aware custom forms

- `get_field_data(card_id)` returns each configured field definition together
  with that card's detached, editor-ready value. Results follow schema order
  and are keyed by the stable field key.
- `update_field(card_id, field_key, value)` validates and updates one configured
  value through the existing `update_card()` boundary, retaining permissions,
  redraw, normalization, and `card_updated` event behavior.
- The exported `CardFieldData` `TypedDict` describes the normalized
  definition-plus-value result for typed integrations.
- The custom-editor example and guides now cover dynamic controls, read-only
  presentation, column IDs, validation feedback, and one-call bulk form saves;
  the guides also show targeted single-field updates.

## CustomTkinter-native interaction

- Card and column actions now use compact, text-only CustomTkinter popup menus
  with right-click access and nested move choices.
- Card-size and generated select controls use a shared theme-aware dropdown.
- Compact, normal, and large card presets are available in configuration, the
  toolbar, and `set_card_size()`.
- The generated editor opens immediately over the exact right half of the
  board and uses DPI-aware CustomTkinter labels, sections, pills, fonts, and
  control dimensions.
- Column headers and card static content have been reworked for consistent
  high-DPI appearance while retaining anti-aliased interactive controls.

## Runtime efficiency

- Column add, rename, move, and delete operations retain unaffected column and
  card widgets instead of rebuilding the complete board.
- Mutations avoid full snapshots and deep copies when no change callback needs
  them, and revision tracking skips no-op rendering and events.
- One root-level wheel router replaces per-column global callbacks. Scrollbar
  work, search text, scroll restoration, and drag target lookup are also
  cached or coalesced.

## Compatibility

Python 3.10 or newer remains required. CustomTkinter 6.0.0 is now the minimum
supported release, with major version 7 excluded. Applications using
CustomTkinter 5 must upgrade it before installing CTkKanban 2.3.0.

Existing card data, field mappings, `Field`/`CardField` definitions,
`on_card_open(card)`, `on_change(event)`, and built-in editor behavior remain
compatible. The four-field default schema is unchanged when `fields` is
omitted.

Install or upgrade with:

```bash
python -m pip install --upgrade CTkKanBan==2.3.0
```

See the [changelog](../CHANGELOG.md) for the exact change list and the
[documentation](index.html) for the complete API and custom-editor guide.
