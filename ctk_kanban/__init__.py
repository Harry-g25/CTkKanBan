"""Public API for the focused CTkKanban widget."""

from .adapters import (
    normalize_row,
    normalize_rows,
    rows_from_cursor,
    snapshot_from_cursors,
    snapshot_from_rows,
)
from .board import CTkKanbanBoard
from .config import ActionConfig, BoardConfig, LayoutConfig, TextConfig, merge_config
from .fields import DEFAULT_FIELDS, FieldDefinition, FieldType
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
    "ActionConfig",
    "BoardModel",
    "BoardModelError",
    "BoardSnapshot",
    "BoardConfig",
    "Card",
    "CardRecord",
    "Column",
    "ColumnRecord",
    "DEFAULT_FIELDS",
    "DEFAULT_THEME",
    "FieldDefinition",
    "FieldType",
    "LayoutConfig",
    "TextConfig",
    "merge_config",
    "merge_theme",
    "normalize_row",
    "normalize_rows",
    "rows_from_cursor",
    "snapshot_from_cursors",
    "snapshot_from_rows",
    "__version__",
]
