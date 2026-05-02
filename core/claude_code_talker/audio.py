"""WAV playback utilities. Phase 1 is synchronous; Phase 2 adds the async queue."""
from __future__ import annotations

import logging
import os
import queue
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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


class AudioQueue:
    """FIFO queue with a single worker thread that synthesizes and plays.

    Phase 2A: simple, unbounded, log-and-continue on errors. Phase 2B will
    add priority, drop policy, and interruption handling for Mode C.
    """

    def __init__(self, state) -> None:
        self._state = state
        self._queue: "queue.Queue[Optional[AudioJob]]" = queue.Queue()
        self._worker = threading.Thread(
            target=self._run, daemon=True, name="codetalker-audio"
        )
        self._stopped = False

    def start(self) -> None:
        if not self._worker.is_alive():
            self._worker.start()

    def submit(self, job: AudioJob) -> None:
        self._queue.put(job)

    def shutdown(self, drain_timeout: float = 5.0) -> None:
        self._stopped = True
        self._queue.put(None)  # poison pill
        self._worker.join(timeout=drain_timeout)

    def _run(self) -> None:
        # Stub for Task 3 — completes immediately on poison pill so lifecycle tests pass.
        while not self._stopped:
            job = self._queue.get()
            if job is None:
                break
            self._queue.task_done()
