"""WAV playback utilities. Phase 1 is synchronous; Phase 2 adds the async queue."""
from __future__ import annotations

import heapq
import logging
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path


class _PlaybackHandle:
    """Tracks the currently-playing audio so it can be stopped."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._is_winsound: bool = False
        self._lock = threading.Lock()

    def start_winsound(self) -> None:
        with self._lock:
            self._is_winsound = True

    def start_subprocess(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._proc = proc

    def stop(self) -> None:
        with self._lock:
            if self._is_winsound:
                try:
                    import winsound
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass
                self._is_winsound = False
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None

    def clear(self) -> None:
        with self._lock:
            self._proc = None
            self._is_winsound = False


def _play_file(wav_path: str) -> None:
    """Platform-specific synchronous WAV playback (no interrupt support)."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        subprocess.run(["afplay", wav_path], check=False)
    else:
        subprocess.run(["aplay", "-q", wav_path], check=False)


def _play_file_interruptible(wav_path: str, handle: _PlaybackHandle) -> None:
    """Platform-specific WAV playback with stop() support via the handle."""
    if sys.platform == "win32":
        import winsound
        handle.start_winsound()
        try:
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        finally:
            handle.clear()
    elif sys.platform == "darwin":
        proc = subprocess.Popen(["afplay", wav_path])
        handle.start_subprocess(proc)
        try:
            proc.wait()
        finally:
            handle.clear()
    else:
        proc = subprocess.Popen(["aplay", "-q", wav_path])
        handle.start_subprocess(proc)
        try:
            proc.wait()
        finally:
            handle.clear()


def play_wav_bytes(wav: bytes, handle: _PlaybackHandle | None = None) -> None:
    """Play WAV-encoded audio synchronously (blocks until playback completes).

    If a _PlaybackHandle is supplied, playback is interruptible via handle.stop().
    Without a handle, a throwaway one is used so behavior is unchanged for
    callers that don't need interruption.
    """
    if not wav:
        return
    h = handle if handle is not None else _PlaybackHandle()
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="claude_tts_play_")
    os.close(fd)
    try:
        Path(wav_path).write_bytes(wav)
        _play_file_interruptible(wav_path, h)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def play_audio_bytes(audio: bytes, audio_format: str = "wav", handle: _PlaybackHandle | None = None) -> None:
    """Play audio bytes synchronously. Format is "wav" or "mp3".

    On Windows, MP3 is transcoded to WAV via pydub (requires ffmpeg).
    On macOS/Linux, MP3 plays directly via afplay/mpg123.
    The optional `handle` is forwarded to the WAV playback path so interruption works.
    """
    if not audio:
        return
    if audio_format == "wav":
        return play_wav_bytes(audio, handle)
    if audio_format == "mp3":
        return _play_mp3_bytes(audio)
    raise ValueError(f"unknown audio format: {audio_format}")


def _play_mp3_bytes(audio: bytes) -> None:
    # Note: MP3 playback does not support interruption via _PlaybackHandle (rare in live narration path).
    if sys.platform == "win32":
        # Transcode to WAV via pydub
        try:
            from pydub import AudioSegment
            import io
            seg = AudioSegment.from_mp3(io.BytesIO(audio))
            buf = io.BytesIO()
            seg.export(buf, format="wav")
            return play_wav_bytes(buf.getvalue())
        except ImportError:
            logging.warning("pydub not installed; cannot play MP3 on Windows")
            return
    elif sys.platform == "darwin":
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="claude_tts_play_")
        os.close(fd)
        try:
            Path(path).write_bytes(audio)
            subprocess.run(["afplay", path], check=False)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    else:
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="claude_tts_play_")
        os.close(fd)
        try:
            Path(path).write_bytes(audio)
            subprocess.run(["mpg123", "-q", path], check=False)
        finally:
            try:
                os.unlink(path)
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
    audio_format: str = "wav"  # wav (Piper) or mp3 (cloud engines)


_PRIORITY_RANK = {"alert": 0, "normal": 1, "routine": 2}


class AudioQueue:
    """Heap-based priority queue with a single worker thread.

    Three priority levels — alert | normal | routine — dispatched via heapq
    ordering on (priority_rank, sequence_number). An alert always overtakes
    pending normals/routines. FIFO within the same priority level.
    """

    def __init__(self, state, max_depth: int = 5, staleness_seconds: float = 20.0) -> None:
        self._state = state
        self._queue: list[tuple] = []  # heap of (priority_rank, seq, job)
        self._cv = threading.Condition()
        self._seq = 0
        self._handle = _PlaybackHandle()
        self._worker = threading.Thread(
            target=self._run, daemon=True, name="codetalker-audio"
        )
        self._stopped = False
        self._poison = False
        self._max_depth = max_depth
        self._staleness = staleness_seconds

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
            self._enforce_depth_locked()
            self._cv.notify()
        if job.priority == "alert":
            self._handle.stop()  # interrupt current playback

    def _enforce_depth_locked(self) -> None:
        """Caller holds self._cv. Drops non-alert items if over max_depth."""
        if len(self._queue) <= self._max_depth:
            return
        # Find non-alert items, drop the oldest ones until under cap.
        # Sort by (rank desc, seq asc) — drop normals/routines first, oldest first.
        # Iterate copy; reconstruct the heap.
        to_drop = len(self._queue) - self._max_depth
        items = list(self._queue)
        # Keep original tuples (don't unpack) so id() comparison works correctly.
        non_alerts = [t for t in items if t[2].priority != "alert"]
        non_alerts.sort(key=lambda x: (-x[0], x[1]))  # least-priority + oldest first
        drop_set = set(id(t) for t in non_alerts[:to_drop])
        kept = [t for t in items if id(t) not in drop_set]
        self._queue.clear()
        for t in kept:
            heapq.heappush(self._queue, t)

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
        import time
        while True:
            with self._cv:
                while not self._queue and not self._poison:
                    self._cv.wait()
                if self._poison and not self._queue:
                    break
                if not self._queue:
                    continue
                rank, seq, job = heapq.heappop(self._queue)
            # Drop stale non-alert jobs
            if job.priority != "alert" and (time.time() - job.enqueued_at) > self._staleness:
                logging.debug("dropping stale audio job: %s", job.text[:40])
                continue
            try:
                engine = self._state.engines[job.engine_name]
                wav = engine.synthesize(job.text, job.voice, job.rate)
                play_audio_bytes(wav, audio_format=job.audio_format, handle=self._handle)
            except Exception as e:
                logging.warning("audio job failed: %s", e)
