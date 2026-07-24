"""Data-source protocol and threaded persistence coordination."""

from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from time import sleep
from typing import Any, Callable, Protocol, runtime_checkable

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


def _mapped_identifier(value: Any, id_map: dict[Any, Any]) -> Any:
    """Return a canonical identifier without assuming arbitrary values are hashable."""

    try:
        return id_map[value] if value in id_map else value
    except TypeError:
        return value


def _rebase_card_record(value: Any, id_map: dict[Any, Any]) -> None:
    if isinstance(value, dict) and "id" in value:
        value["id"] = _mapped_identifier(value["id"], id_map)


def _rebase_event(event: MutationEvent, id_map: dict[Any, Any]) -> MutationEvent:
    """Clone an event and rewrite card-ID references resolved by earlier writes."""

    rebased = deepcopy(event)
    payload = rebased.payload
    for key in ("card_id", "old_card_id"):
        if key in payload:
            payload[key] = _mapped_identifier(payload[key], id_map)
    for key in ("card_data", "old_card_data"):
        _rebase_card_record(payload.get(key), id_map)
    for key in ("changed_cards", "affected_cards", "cards"):
        values = payload.get(key)
        if isinstance(values, list):
            for value in values:
                _rebase_card_record(value, id_map)
    return rebased


def _copy_pending_event(
    value: MutationEvent | list[MutationEvent],
    id_map: dict[Any, Any] | None = None,
    revisions: dict[str, int | str] | None = None,
) -> MutationEvent | list[MutationEvent]:
    """Create an adapter-owned event copy, optionally rebased for queue replay."""

    mapping = id_map or {}
    source = value if isinstance(value, list) else [value]
    copied = [_rebase_event(event, mapping) for event in source]
    if revisions:
        for event in copied:
            revision = revisions.get(event.metadata.board_id)
            if revision is not None:
                event.metadata.expected_revision = revision
    return copied if isinstance(value, list) else copied[0]


def _same_mutation_identity(
    left: MutationEvent | list[MutationEvent],
    right: MutationEvent | list[MutationEvent],
) -> bool:
    """Match a retry while allowing only concurrency metadata to change."""

    left_events = left if isinstance(left, list) else [left]
    right_events = right if isinstance(right, list) else [right]
    if len(left_events) != len(right_events):
        return False
    return all(
        first.metadata.event_id == second.metadata.event_id
        and first.metadata.board_id == second.metadata.board_id
        and first.type == second.type
        and first.payload == second.payload
        for first, second in zip(left_events, right_events)
    )


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
        self._flushing_offline = False
        self._queue_blocked = False
        self._offline_id_map: dict[Any, Any] = {}
        self._offline_revisions: dict[str, int | str] = {}
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
        if callback is not None:
            self._schedule_if_open(partial(callback, state, message))

    def _schedule_if_open(self, callback: Callable[[], None]) -> None:
        """Schedule a callback that becomes a no-op once the coordinator closes."""

        if self._closed:
            return

        def guarded() -> None:
            if not self._closed:
                callback()

        self.schedule(guarded)

    def _queue_pending(self, pending: PendingMutation, noun: str) -> bool:
        """Queue work when offline replay owns the FIFO ordering barrier."""

        start_flush = False
        with self._lock:
            if self._closed:
                raise RuntimeError("Persistence coordinator is closed")
            failed = self._last_failed
            is_failed_retry = (
                self._queue_blocked
                and failed is not None
                and _same_mutation_identity(failed.event, pending.event)
            )
            if is_failed_retry:
                self._last_failed = None
                self._queue_blocked = False
                self._online = True
                retry_events = pending.event if isinstance(pending.event, list) else [pending.event]
                for event in retry_events:
                    if event.metadata.expected_revision is not None:
                        self._offline_revisions[event.metadata.board_id] = (
                            event.metadata.expected_revision
                        )
                self._offline_queue.appendleft(pending)
                if not self._flushing_offline:
                    self._flushing_offline = True
                    start_flush = True
            elif (
                not self._online
                or self._flushing_offline
                or self._queue_blocked
                or bool(self._offline_queue)
            ):
                self._offline_queue.append(pending)
            else:
                return False
            state: PersistenceState = "offline" if not self._online else "saving"
            queued_count = len(self._offline_queue)
        self._status(state, f"Queued {queued_count} {noun}(s)")
        if start_flush:
            self._flush_next_offline()
        return True

    def submit(
        self,
        event: MutationEvent,
        *,
        on_success: Callable[[MutationResult], None],
        on_failure: Callable[[Exception | MutationResult], None],
    ) -> Future[MutationResult] | None:
        owned_event = _copy_pending_event(event)
        assert isinstance(owned_event, MutationEvent)
        pending = PendingMutation(owned_event, on_success, on_failure)
        if self._queue_pending(pending, "change"):
            return None
        self._status("saving", "Saving...")
        future = self._executor.submit(self._apply_with_retry, owned_event)
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
            self._schedule_if_open(lambda: on_success(MutationResult()))
            return None
        owned_events = _copy_pending_event(events)
        assert isinstance(owned_events, list)
        pending = PendingMutation(owned_events, on_success, on_failure)
        if self._queue_pending(pending, "change set"):
            return None
        self._status("saving", "Saving batch...")
        future = self._executor.submit(self._apply_with_retry, owned_events)
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
            self._schedule_if_open(partial(pending.on_failure, exc))
            return
        if result.conflict is not None:
            with self._lock:
                self._last_failed = pending
            self._status("conflict", result.conflict.message)
            self._schedule_if_open(partial(pending.on_failure, result))
            return
        if not result.accepted:
            with self._lock:
                self._last_failed = pending
            self._status("error", result.reason or "Save rejected")
            self._schedule_if_open(partial(pending.on_failure, result))
            return
        with self._lock:
            self._last_failed = None
            has_queued = bool(self._offline_queue)
            if has_queued:
                self._offline_id_map.update(self._created_id_map(pending.event, result))
                if result.board_revision is not None:
                    events = pending.event if isinstance(pending.event, list) else [pending.event]
                    for event in events:
                        self._offline_revisions[event.metadata.board_id] = result.board_revision
        self._status("saved", "Saved")

        def deliver_and_resume() -> None:
            try:
                pending.on_success(result)
            finally:
                with self._lock:
                    should_resume = self._online and bool(self._offline_queue)
                if has_queued and should_resume:
                    self.flush_offline_queue()

        self._schedule_if_open(deliver_and_resume)

    def set_online(self, online: bool) -> None:
        with self._lock:
            self._online = online
        if online:
            self.flush_offline_queue()
        else:
            self._status("offline", "Offline")

    def flush_offline_queue(self) -> None:
        """Replay queued writes in order, rebasing dependent temporary card IDs."""

        with self._lock:
            self._online = True
            if (
                self._closed
                or self._queue_blocked
                or self._flushing_offline
                or not self._offline_queue
            ):
                return
            self._flushing_offline = True
        self._flush_next_offline()

    def _flush_next_offline(self) -> None:
        with self._lock:
            if self._closed or not self._online:
                self._flushing_offline = False
                return
            if not self._offline_queue:
                self._flushing_offline = False
                self._queue_blocked = False
                self._offline_id_map.clear()
                self._offline_revisions.clear()
                self._last_failed = None
                self._status("saved", "Saved")
                return
            original = self._offline_queue.popleft()
            prepared_event = _copy_pending_event(
                original.event,
                self._offline_id_map,
                self._offline_revisions,
            )
        self._status("saving", "Saving queued change...")
        future = self._executor.submit(self._apply_with_retry, prepared_event)
        future.add_done_callback(
            lambda completed: self._complete_offline(completed, original, prepared_event)
        )

    @staticmethod
    def _created_id_map(
        event: MutationEvent | list[MutationEvent], result: MutationResult
    ) -> dict[Any, Any]:
        mapping = dict(result.id_map)
        if isinstance(event, MutationEvent) and event.type == "card_created" and result.card is not None:
            card_data = event.payload.get("card_data")
            if isinstance(card_data, dict) and "id" in card_data and "id" in result.card:
                local_id = card_data["id"]
                canonical_id = result.card["id"]
                if local_id != canonical_id:
                    mapping[local_id] = canonical_id
        return mapping

    def _complete_offline(
        self,
        future: Future[MutationResult],
        original: PendingMutation,
        prepared_event: MutationEvent | list[MutationEvent],
    ) -> None:
        """Finish one queued write before allowing the next dependent write."""

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
                self._flushing_offline = False
                if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                    self._last_failed = original
                    self._online = False
                    self._offline_queue.appendleft(original)
                else:
                    self._last_failed = original
                    self._queue_blocked = True
            state: PersistenceState = "offline" if not self._online else "error"
            self._status(state, str(exc) or exc.__class__.__name__)
            self._schedule_if_open(partial(original.on_failure, exc))
            return
        if result.conflict is not None or not result.accepted:
            with self._lock:
                self._last_failed = original
                self._flushing_offline = False
                self._queue_blocked = True
            if result.conflict is not None:
                self._status("conflict", result.conflict.message)
            else:
                self._status("error", result.reason or "Save rejected")
            self._schedule_if_open(partial(original.on_failure, result))
            return

        with self._lock:
            self._last_failed = None
            self._offline_id_map.update(self._created_id_map(prepared_event, result))
            if result.board_revision is not None:
                events = prepared_event if isinstance(prepared_event, list) else [prepared_event]
                for event in events:
                    self._offline_revisions[event.metadata.board_id] = result.board_revision
        self._status("saved", "Saved")

        def deliver_and_continue() -> None:
            try:
                original.on_success(result)
            finally:
                self._flush_next_offline()

        self._schedule_if_open(deliver_and_continue)

    def retry_last(self) -> bool:
        with self._lock:
            pending = self._last_failed
            self._last_failed = None
            self._queue_blocked = False
            self._online = True
            if pending is None:
                return False
            self._offline_queue = deque(
                item for item in self._offline_queue if item is not pending
            )
            self._offline_queue.appendleft(pending)
            if self._flushing_offline:
                return True
            self._flushing_offline = True
        self._flush_next_offline()
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
            if self._closed:
                return
            try:
                result = completed.result()
            except Exception as exc:
                self._status("error", str(exc) or exc.__class__.__name__)
                self._schedule_if_open(partial(on_failure, exc))
                return
            self._status("idle", None)
            self._schedule_if_open(partial(on_success, result))

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
            if self._closed:
                return
            try:
                page = completed.result()
            except Exception as exc:
                self._status("error", str(exc) or exc.__class__.__name__)
                self._schedule_if_open(partial(on_failure, exc))
                return
            self._status("idle", None)
            self._schedule_if_open(partial(on_success, page))

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
            if self._closed:
                return
            try:
                page = completed.result()
            except Exception as exc:
                self._schedule_if_open(partial(on_failure, exc))
                return
            self._schedule_if_open(partial(on_success, page))

        future.add_done_callback(complete)
        return future

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
