"""
EventBus — async pub/sub for the Phase 4 SSE channel.

Replaces eight polling loops with a single push channel:

  Pro Android   SessionListScreen      3s poll
  Pro Android   SessionDetailScreen    3s poll
  Pro Android   PreferencesScreen      5s poll
  Pro Android   AutoSubscribe scan     3s poll
  webui         useSessions            5s poll
  webui         useSessionConfig       5s poll
  webui         useDaemonHealth        5s poll
  webui         master-enabled query   5s poll

All eight serve one purpose: detect daemon-side state changes within a
few seconds. Phase 4's EventBus pushes those changes within ~50ms via
SSE so each polling loop can be deleted in Phase 6.

Design choices (intentional, documented for future readers):

  * **One queue per subscriber, bounded.** Slow subscribers can't
    backpressure the publisher. When a subscriber's queue fills, the
    oldest event drops and an `__overflow__` sentinel is enqueued so
    the consumer knows to re-fetch state from REST. This mirrors the
    NarrationStream pattern already in use.

  * **Filter by topic at the subscriber, not the publisher.** A
    publisher emits Event objects; the subscriber decides which
    `event_type` strings it cares about. Keeps the publish path
    O(subscribers) without per-topic indexing.

  * **No persistence.** Events are ephemeral. A client that
    disconnects + reconnects re-fetches state from REST. This is the
    standard "snapshot + diff" pattern: REST gives you the truth at
    one moment, SSE gives you the deltas going forward.

  * **Cross-loop publish via asyncio.run_coroutine_threadsafe**.
    The audio worker runs in a thread; it can't `await publish()`.
    Wrappers in audio.py + companion/api.py call
    `bus.publish_threadsafe(...)` which schedules onto the daemon's
    uvicorn loop. Synchronous callers just call publish_threadsafe.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Iterable, Optional, Set

from claude_code_talker.schemas import Event


DEFAULT_MAX_QUEUE = 200


class _Subscriber:
    """One consumer's queue + filter."""

    __slots__ = ("queue", "topics")

    def __init__(self, max_queue: int, topics: Optional[Set[str]]) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue)
        # None = subscribe to every event_type. Set = filter to these.
        self.topics: Optional[Set[str]] = topics


class EventBus:
    """
    Bounded fan-out pub/sub. One instance lives on ServerState; every
    emitter writes through it, every SSE subscription reads from it.

    Thread-safety: publish_threadsafe is the cross-thread entry point.
    It captures the bus's owning event loop the first time a subscriber
    arrives and schedules publish coroutines onto it via
    run_coroutine_threadsafe. async publishers can just call publish().
    """

    def __init__(self, max_queue: int = DEFAULT_MAX_QUEUE) -> None:
        self._max_queue = max_queue
        self._subscribers: list[_Subscriber] = []
        self._lock = asyncio.Lock()
        # Captured lazily on first subscribe — the loop the daemon's
        # uvicorn server is running on. Cross-thread publishers schedule
        # onto this loop.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Subscribe — async iterator that yields Event objects.
    # ------------------------------------------------------------------

    def subscribe(
        self, topics: Optional[Iterable[str]] = None
    ) -> AsyncIterator[Event]:
        """
        Return an async iterator that yields every event the
        subscriber cares about. Pass topics=None to receive everything;
        pass an iterable of event_type strings to filter.

        Lifecycle: the iterator's queue is registered when the iterator
        is first awaited and deregistered when the consumer breaks out
        of the loop (either by `return` or by exception). Slow
        consumers get __overflow__ sentinels rather than blocking the
        publisher.
        """
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                # No loop yet — subscriber didn't await anything before
                # asking for the iterator. We'll capture on the first
                # iteration instead (see _gen below).
                pass
        topics_set: Optional[Set[str]] = set(topics) if topics is not None else None
        sub = _Subscriber(self._max_queue, topics_set)
        self._subscribers.append(sub)

        async def _gen() -> AsyncIterator[Event]:
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
            try:
                while True:
                    ev = await sub.queue.get()
                    yield ev
            finally:
                if sub in self._subscribers:
                    self._subscribers.remove(sub)

        return _gen()

    # ------------------------------------------------------------------
    # Publish — async (same loop) and threadsafe (cross-thread) variants.
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """
        Broadcast `event` to every subscriber whose topic filter
        matches. Slow subscribers get an overflow sentinel rather than
        blocking the publisher.
        """
        # No lock during fan-out — we're on the single loop and the
        # subscriber list is only mutated under the gen's finally.
        # The lock is only needed for the rare case where subscribe()
        # races with publish() but Python's GIL + list semantics make
        # that benign here.
        for sub in list(self._subscribers):
            if sub.topics is not None and event.event_type not in sub.topics:
                continue
            try:
                if sub.queue.full():
                    # Drop oldest, push an overflow sentinel — the
                    # consumer should re-fetch state from REST.
                    try:
                        sub.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        sub.queue.put_nowait(_overflow_event())
                    except asyncio.QueueFull:
                        pass
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Subscriber is so backed up even the overflow sentinel
                # didn't fit. Drop silently — the consumer will
                # eventually time out and reconnect.
                pass

    def publish_threadsafe(self, event: Event) -> None:
        """
        Schedule `publish(event)` onto the bus's owning event loop.
        Safe to call from any thread (audio worker, hook handler,
        anything synchronous). No-op when no loop has been captured
        yet (no subscribers) — the event simply isn't observed,
        consistent with "no listener = no notification."
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.publish(event), loop)
        except RuntimeError:
            # Loop may have shut down between the .is_closed check and
            # the schedule attempt. Drop silently — graceful shutdown
            # is more important than every event landing.
            logging.debug("event_bus: publish_threadsafe drop (loop closed)")

    # ------------------------------------------------------------------
    # Introspection (used by tests + diagnostics).
    # ------------------------------------------------------------------

    def subscriber_count(self) -> int:
        return len(self._subscribers)


def _overflow_event() -> Event:
    """Sentinel event indicating the subscriber missed events. Receivers
    should re-fetch state from REST when they see this."""
    return Event(event_type="__overflow__", at=time.time())
