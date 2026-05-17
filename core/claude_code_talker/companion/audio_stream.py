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
        # Each entry is (publish_ts, wav_bytes). Drained into NEW
        # subscribers' queues at subscribe time IFF there's been an
        # actual gap (no subscribers for >REPLAY_GAP_THRESHOLD_SEC).
        # This catches genuine disconnects (Wi-Fi roam, Doze, daemon
        # restart) without replaying on every routine 55s long-poll
        # cycle, which would cause the same narration to play over
        # and over each time the phone's poller re-subscribed.
        self._replay: dict[str, deque[tuple[float, bytes]]] = {}
        # 2026-05-17 — track per-sid the timestamp of the LAST FRAME
        # delivered (either via live publish or replay). On new
        # subscribe, only replay frames newer than this — guarantees
        # at-most-once delivery per frame per sid. Without this the
        # buffer replayed on every routine poll cycle.
        self._last_delivered_ts: dict[str, float] = {}

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
        # Replay frames published since this sid's last successful
        # delivery. Tracking last_delivered_ts gives at-most-once
        # delivery: a poller cycling through routine 55s long-polls
        # gets fresh frames via the live publish path, and only
        # genuinely-missed frames (published when no subscriber
        # existed) get replayed on the next connect.
        self._trim_replay(session_id)
        last_delivered = self._last_delivered_ts.get(session_id, 0.0)
        for ts, wav in self._replay.get(session_id, ()):
            if ts > last_delivered:
                try:
                    q.put_nowait(wav)
                    self._last_delivered_ts[session_id] = ts
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
        ts = time.time()
        buf = self._replay.setdefault(session_id, deque(maxlen=_REPLAY_MAX_COUNT * 2))
        buf.append((ts, frame))
        self._trim_replay(session_id)
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(frame)
                # Update last-delivered on each live-publish enqueue
                # so the next subscribe doesn't re-replay this frame.
                self._last_delivered_ts[session_id] = ts
            except asyncio.QueueFull:
                pass

    async def close(self, session_id: str) -> None:
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
