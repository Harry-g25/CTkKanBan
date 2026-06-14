"""Exceptions raised by :mod:`ctk_kanban`."""


class KanbanError(Exception):
    """Base class for all CTkKanban errors."""


class KanbanValidationError(KanbanError, ValueError):
    """Raised when board, column, card, or field data is invalid."""


class KanbanDuplicateIDError(KanbanValidationError):
    """Raised when a card or column ID is already in use."""


class KanbanUnknownColumnError(KanbanValidationError):
    """Raised when a card references a column that does not exist."""


class KanbanMoveCancelledError(KanbanError):
    """Raised by callers that choose to treat a cancelled move as an error."""


class KanbanPersistenceError(KanbanError):
    """Raised when a durable mutation cannot be saved."""


class KanbanConflictError(KanbanPersistenceError):
    """Raised for optimistic-concurrency conflicts."""
