"""Phase 23 — fan-out narration event pub/sub used by /api/narration-stream.

Each subscriber gets a bounded asyncio.Queue. When the queue is full the
oldest events drop and an overflow sentinel is enqueued so the subscriber
knows it lost data.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Literal


NarrationStatus = Literal["queued", "speaking", "done", "skipped", "overflow"]


@dataclass
class NarrationEvent:
    session_id: str
    timestamp: float
    text: str
    voice: str
    mode: str
    status: NarrationStatus
    confidence: str = "normal"  # "normal" or "low" (hedged)


class NarrationStream:
    """Async fan-out for narration events. Each subscriber receives every published event via a bounded `asyncio.Queue`; if the queue overflows, the oldest event is dropped and a sentinel with `status="overflow"` is enqueued so the consumer can detect data loss."""

    def __init__(self, max_queue: int = 200):
        self._max_queue = max_queue
        self._subscribers: list[asyncio.Queue[NarrationEvent]] = []
        self._lock = asyncio.Lock()

    def subscribe(self) -> AsyncIterator[NarrationEvent]:
        """Return an async iterator yielding NarrationEvents until the consumer breaks/finishes."""
        q: asyncio.Queue[NarrationEvent] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.append(q)

        async def _gen() -> AsyncIterator[NarrationEvent]:
            try:
                while True:
                    yield await q.get()
            finally:
                if q in self._subscribers:
                    self._subscribers.remove(q)

        return _gen()

    async def publish(self, event: NarrationEvent) -> None:
        """Broadcast `event` to every subscriber. Slow subscribers see a dropped-oldest + overflow sentinel rather than blocking the publisher."""
        async with self._lock:
            for q in list(self._subscribers):
                if q.full():
                    # Drop oldest, enqueue overflow sentinel
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    sentinel = NarrationEvent(
                        session_id=event.session_id,
                        timestamp=event.timestamp,
                        text="",
                        voice=event.voice,
                        mode=event.mode,
                        status="overflow",
                    )
                    try:
                        q.put_nowait(sentinel)
                    except asyncio.QueueFull:
                        pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass
