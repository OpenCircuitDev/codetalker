"""WAV playback utilities. Phase 1 is synchronous; Phase 2 adds the async queue."""
from __future__ import annotations

import heapq
import logging
import os
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path


def _play_file(wav_path: str) -> None:
    """Platform-specific synchronous WAV playback."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["afplay", wav_path], check=False)
    else:
        import subprocess
        subprocess.run(["aplay", "-q", wav_path], check=False)


def play_wav_bytes(wav: bytes) -> None:
    """Play WAV-encoded audio synchronously (blocks until playback completes)."""
    if not wav:
        return
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="claude_tts_play_")
    os.close(fd)
    try:
        Path(wav_path).write_bytes(wav)
        _play_file(wav_path)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


@dataclass
class AudioJob:
    """One unit of work for the audio worker thread."""
    text: str
    voice: str
    rate: float
    engine_name: str = "piper"
    priority: str = "normal"  # alert | normal | routine
    enqueued_at: float = 0.0


_PRIORITY_RANK = {"alert": 0, "normal": 1, "routine": 2}


class AudioQueue:
    """Heap-based priority queue with a single worker thread.

    Three priority levels — alert | normal | routine — dispatched via heapq
    ordering on (priority_rank, sequence_number). An alert always overtakes
    pending normals/routines. FIFO within the same priority level.
    """

    def __init__(self, state) -> None:
        self._state = state
        self._queue: list[tuple] = []  # heap of (priority_rank, seq, job)
        self._cv = threading.Condition()
        self._seq = 0
        self._worker = threading.Thread(
            target=self._run, daemon=True, name="codetalker-audio"
        )
        self._stopped = False
        self._poison = False

    def start(self) -> None:
        if not self._worker.is_alive():
            self._worker.start()

    def submit(self, job: AudioJob) -> None:
        if not job.enqueued_at:
            import time
            job.enqueued_at = time.time()
        with self._cv:
            self._seq += 1
            rank = _PRIORITY_RANK.get(job.priority, 1)
            heapq.heappush(self._queue, (rank, self._seq, job))
            self._cv.notify()

    def shutdown(self, drain_timeout: float = 5.0) -> None:
        with self._cv:
            self._poison = True
            self._cv.notify_all()
        self._worker.join(timeout=drain_timeout)
        self._stopped = True

    def join(self) -> None:
        """Block until queue is empty (for tests)."""
        import time
        while True:
            with self._cv:
                if not self._queue:
                    return
            time.sleep(0.05)

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._queue and not self._poison:
                    self._cv.wait()
                if self._poison and not self._queue:
                    break
                if not self._queue:
                    continue
                rank, seq, job = heapq.heappop(self._queue)
            try:
                engine = self._state.engines[job.engine_name]
                wav = engine.synthesize(job.text, job.voice, job.rate)
                play_wav_bytes(wav)
            except Exception as e:
                logging.warning("audio job failed: %s", e)
