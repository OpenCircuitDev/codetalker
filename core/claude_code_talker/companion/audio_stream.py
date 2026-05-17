"""CCT-31 — Per-session async audio frame fan-out."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import AsyncIterator


# 2026-05-16 — replay buffer tuning. With long-poll subscriptions
# (55-second window) on intermittent mobile networks, subscribers
# regularly disconnect briefly (NAT timeout, Wi-Fi roam, Doze, app
# backgrounding). Without replay, every WAV published in that gap is
# lost forever because audio_hub.publish() is fire-and-forget. With
# replay, a subscriber that reconnects within the retention window
# receives the WAVs it missed.
#
# 60 seconds covers typical poller backoff sequences (250ms → 5s
# capped, ~10 retries to span a minute). 10 WAVs caps memory growth
# (a session in flagrant narration mode at ~500 KB/WAV = 5 MB worst
# case per sid).
_REPLAY_RETENTION_SEC = 60.0
_REPLAY_MAX_COUNT = 10


class AudioStreamHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[bytes | None]]] = {}
        # 2026-05-16 — per-sid bounded ring of recently-published WAVs.
        # Each entry is (publish_ts, wav_bytes). Drained into every new
        # subscriber's queue at subscribe time so reconnects after a
        # network blip don't drop audio.
        self._replay: dict[str, deque[tuple[float, bytes]]] = {}

    def _trim_replay(self, session_id: str) -> None:
        """Evict entries older than retention window or beyond max count."""
        buf = self._replay.get(session_id)
        if not buf:
            return
        cutoff = time.time() - _REPLAY_RETENTION_SEC
        while buf and buf[0][0] < cutoff:
            buf.popleft()
        while len(buf) > _REPLAY_MAX_COUNT:
            buf.popleft()

    def subscribe(self, session_id: str) -> AsyncIterator[bytes]:
        q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(q)
        # Replay any recently-published WAVs into the new queue so a
        # subscriber that reconnects after a brief outage immediately
        # receives the audio it missed (rather than waiting for the
        # next publish, which may not come for minutes).
        self._trim_replay(session_id)
        for _ts, wav in self._replay.get(session_id, ()):
            try:
                q.put_nowait(wav)
            except asyncio.QueueFull:
                break

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
        # Record into the replay buffer BEFORE fanning out so any
        # subscriber that joins between publish-time and the next
        # subscribe() call still gets this frame on connect.
        buf = self._replay.setdefault(session_id, deque(maxlen=_REPLAY_MAX_COUNT * 2))
        buf.append((time.time(), frame))
        self._trim_replay(session_id)
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
