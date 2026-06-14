"""Data-source protocol and threaded persistence coordination."""

from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from time import sleep
from typing import Callable, Protocol, runtime_checkable

from .contracts import (
    BoardLoadResult,
    CardPage,
    CardQuery,
    ChangePage,
    MutationEvent,
    MutationResult,
    PersistenceState,
    coerce_mutation_result,
)


@runtime_checkable
class KanbanDataSource(Protocol):
    """Database-neutral storage interface used by :class:`CTkKanbanBoard`."""

    def load_board(self, board_id: str, query: CardQuery | None = None) -> BoardLoadResult:
        ...

    def apply_mutation(self, event: MutationEvent) -> MutationResult:
        ...

    def apply_batch(self, events: list[MutationEvent]) -> MutationResult:
        ...

    def query_cards(self, board_id: str, query: CardQuery) -> CardPage:
        ...

    def get_changes(self, board_id: str, since_revision: int | str | None) -> ChangePage:
        ...


@dataclass(slots=True)
class RetryPolicy:
    """Retry settings for transient storage failures."""

    attempts: int = 3
    initial_delay: float = 0.25
    multiplier: float = 2.0
    max_delay: float = 3.0


@dataclass(slots=True)
class PendingMutation:
    event: MutationEvent | list[MutationEvent]
    on_success: Callable[[MutationResult], None]
    on_failure: Callable[[Exception | MutationResult], None]


class PersistenceCoordinator:
    """Serialize storage work away from Tk's main thread.

    The coordinator deliberately uses one worker. This preserves mutation order,
    makes database transactions predictable, and keeps optimistic rollback safe.
    """

    def __init__(
        self,
        data_source: KanbanDataSource,
        *,
        schedule: Callable[[Callable[[], None]], None],
        on_status: Callable[[PersistenceState, str | None], None] | None = None,
        retry_policy: RetryPolicy | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.data_source = data_source
        self.schedule = schedule
        self.on_status = on_status
        self.retry_policy = retry_policy or RetryPolicy()
        self.logger = logger or logging.getLogger("ctk_kanban.persistence")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ctk-kanban-db")
        self._offline_queue: deque[PendingMutation] = deque()
        self._last_failed: PendingMutation | None = None
        self._online = True
        self._closed = False
        self._lock = threading.RLock()

    @property
    def online(self) -> bool:
        return self._online

    @property
    def queued_count(self) -> int:
        with self._lock:
            return len(self._offline_queue)

    def _status(self, state: PersistenceState, message: str | None = None) -> None:
        callback = self.on_status
        if callback is not None and not self._closed:
            self.schedule(partial(callback, state, message))

    def submit(
        self,
        event: MutationEvent,
        *,
        on_success: Callable[[MutationResult], None],
        on_failure: Callable[[Exception | MutationResult], None],
    ) -> Future[MutationResult] | None:
        pending = PendingMutation(event, on_success, on_failure)
        with self._lock:
            if not self._online:
                self._offline_queue.append(pending)
                self._status("offline", f"Queued {len(self._offline_queue)} change(s)")
                return None
        self._status("saving", "Saving...")
        future = self._executor.submit(self._apply_with_retry, event)
        future.add_done_callback(lambda completed: self._complete(completed, pending))
        return future

    def submit_batch(
        self,
        events: list[MutationEvent],
        *,
        on_success: Callable[[MutationResult], None],
        on_failure: Callable[[Exception | MutationResult], None],
    ) -> Future[MutationResult] | None:
        """Persist multiple operations atomically through the adapter."""

        if not events:
            self.schedule(lambda: on_success(MutationResult()))
            return None
        pending = PendingMutation(events, on_success, on_failure)
        with self._lock:
            if not self._online:
                self._offline_queue.append(pending)
                self._status("offline", f"Queued {len(self._offline_queue)} change set(s)")
                return None
        self._status("saving", "Saving batch...")
        future = self._executor.submit(self._apply_with_retry, events)
        future.add_done_callback(lambda completed: self._complete(completed, pending))
        return future

    def _apply_with_retry(self, event: MutationEvent | list[MutationEvent]) -> MutationResult:
        delay = self.retry_policy.initial_delay
        last_error: Exception | None = None
        for attempt in range(max(1, self.retry_policy.attempts)):
            try:
                operation = (
                    self.data_source.apply_batch(event)
                    if isinstance(event, list)
                    else self.data_source.apply_mutation(event)
                )
                return coerce_mutation_result(operation)
            except (ConnectionError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 >= self.retry_policy.attempts:
                    break
                self._status("retrying", f"Retrying save ({attempt + 2}/{self.retry_policy.attempts})")
                sleep(delay)
                delay = min(self.retry_policy.max_delay, delay * self.retry_policy.multiplier)
        assert last_error is not None
        raise last_error

    def _complete(self, future: Future[MutationResult], pending: PendingMutation) -> None:
        if self._closed:
            return
        try:
            result = future.result()
        except Exception as exc:
            if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                self.logger.warning("Kanban persistence is offline: %s", exc)
            else:
                self.logger.exception("Kanban persistence failed", exc_info=exc)
            with self._lock:
                self._last_failed = pending
                if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                    self._online = False
                    self._offline_queue.appendleft(pending)
            state: PersistenceState = "offline" if not self._online else "error"
            self._status(state, str(exc) or exc.__class__.__name__)
            self.schedule(partial(pending.on_failure, exc))
            return
        if result.conflict is not None:
            with self._lock:
                self._last_failed = pending
            self._status("conflict", result.conflict.message)
            self.schedule(partial(pending.on_failure, result))
            return
        if not result.accepted:
            with self._lock:
                self._last_failed = pending
            self._status("error", result.reason or "Save rejected")
            self.schedule(partial(pending.on_failure, result))
            return
        with self._lock:
            self._last_failed = None
        self._status("saved", "Saved")
        self.schedule(partial(pending.on_success, result))

    def set_online(self, online: bool) -> None:
        with self._lock:
            self._online = online
        if online:
            self.flush_offline_queue()
        else:
            self._status("offline", "Offline")

    def flush_offline_queue(self) -> None:
        with self._lock:
            pending = list(self._offline_queue)
            self._offline_queue.clear()
            self._online = True
        for index, item in enumerate(pending):
            if index > 0:
                if isinstance(item.event, list):
                    for event in item.event:
                        event.metadata.expected_revision = None
                else:
                    item.event.metadata.expected_revision = None
            if isinstance(item.event, list):
                self.submit_batch(item.event, on_success=item.on_success, on_failure=item.on_failure)
            else:
                self.submit(item.event, on_success=item.on_success, on_failure=item.on_failure)

    def retry_last(self) -> bool:
        with self._lock:
            pending = self._last_failed
            self._last_failed = None
            self._online = True
        if pending is None:
            return False
        if isinstance(pending.event, list):
            self.submit_batch(pending.event, on_success=pending.on_success, on_failure=pending.on_failure)
        else:
            self.submit(pending.event, on_success=pending.on_success, on_failure=pending.on_failure)
        return True

    def load(
        self,
        board_id: str,
        query: CardQuery | None,
        *,
        on_success: Callable[[BoardLoadResult], None],
        on_failure: Callable[[Exception], None],
    ) -> Future[BoardLoadResult]:
        self._status("loading", "Loading...")
        future = self._executor.submit(self.data_source.load_board, board_id, query)

        def complete(completed: Future[BoardLoadResult]) -> None:
            try:
                result = completed.result()
            except Exception as exc:
                self._status("error", str(exc) or exc.__class__.__name__)
                self.schedule(partial(on_failure, exc))
                return
            self._status("idle", None)
            self.schedule(partial(on_success, result))

        future.add_done_callback(complete)
        return future

    def query(
        self,
        board_id: str,
        query: CardQuery,
        *,
        on_success: Callable[[CardPage], None],
        on_failure: Callable[[Exception], None],
    ) -> Future[CardPage]:
        self._status("loading", "Loading cards...")
        future = self._executor.submit(self.data_source.query_cards, board_id, query)

        def complete(completed: Future[CardPage]) -> None:
            try:
                page = completed.result()
            except Exception as exc:
                self._status("error", str(exc) or exc.__class__.__name__)
                self.schedule(partial(on_failure, exc))
                return
            self._status("idle", None)
            self.schedule(partial(on_success, page))

        future.add_done_callback(complete)
        return future

    def changes(
        self,
        board_id: str,
        since_revision: int | str | None,
        *,
        on_success: Callable[[ChangePage], None],
        on_failure: Callable[[Exception], None],
    ) -> Future[ChangePage]:
        future = self._executor.submit(self.data_source.get_changes, board_id, since_revision)

        def complete(completed: Future[ChangePage]) -> None:
            try:
                page = completed.result()
            except Exception as exc:
                self.schedule(partial(on_failure, exc))
                return
            self.schedule(partial(on_success, page))

        future.add_done_callback(complete)
        return future

    def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
