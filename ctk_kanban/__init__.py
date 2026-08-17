"""Public API for the focused CTkKanban widget."""

from .adapters import (
    normalize_row,
    normalize_rows,
    rows_from_cursor,
    snapshot_from_cursors,
    snapshot_from_rows,
)
from .board import CTkKanbanBoard
from .model import (
    BoardModel,
    BoardModelError,
    BoardSnapshot,
    Card,
    CardRecord,
    Column,
    ColumnRecord,
)
from .themes import DEFAULT_THEME, merge_theme
from .version import __version__

__all__ = [
    "CTkKanbanBoard",
    "BoardModel",
    "BoardModelError",
    "BoardSnapshot",
    "Card",
    "CardRecord",
    "Column",
    "ColumnRecord",
    "DEFAULT_THEME",
    "merge_theme",
    "normalize_row",
    "normalize_rows",
    "rows_from_cursor",
    "snapshot_from_cursors",
    "snapshot_from_rows",
    "__version__",
]
