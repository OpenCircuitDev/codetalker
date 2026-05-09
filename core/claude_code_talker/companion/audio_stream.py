"""CCT-31 — Per-session async audio frame fan-out."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator


class AudioStreamHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[bytes | None]]] = {}

    def subscribe(self, session_id: str) -> AsyncIterator[bytes]:
        q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(q)

        async def _gen() -> AsyncIterator[bytes]:
            try:
                while True:
                    frame = await q.get()
                    if frame is None:
                        return
                    yield frame
            finally:
                if session_id in self._subscribers and q in self._subscribers[session_id]:
                    self._subscribers[session_id].remove(q)

        return _gen()

    async def publish(self, session_id: str, frame: bytes) -> None:
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass

    async def close(self, session_id: str) -> None:
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
