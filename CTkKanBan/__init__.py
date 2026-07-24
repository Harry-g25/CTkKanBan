"""Public compatibility import for the CTkKanBan distribution.

The implementation lives in :mod:`ctk_kanban`; this package preserves the
project's branded import spelling for applications that prefer ``import
CTkKanBan``.
"""

from ctk_kanban import *  # noqa: F401,F403
from ctk_kanban import __all__, __version__

