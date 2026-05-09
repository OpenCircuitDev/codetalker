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


class NarrationStream:
    def __init__(self, max_queue: int = 200):
        self._max_queue = max_queue
        self._subscribers: list[asyncio.Queue[NarrationEvent]] = []
        self._lock = asyncio.Lock()

    def subscribe(self) -> AsyncIterator[NarrationEvent]:
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
