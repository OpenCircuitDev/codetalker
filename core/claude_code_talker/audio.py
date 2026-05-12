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
    # CCT-31 — session that produced this audio. Used for AudioStreamHub fan-out
    # so paired AR companions on a specific session receive only their session's
    # narration.  Empty string means "no specific session" (legacy callers).
    session_id: str = ""


_PRIORITY_RANK = {"alert": 0, "normal": 1, "routine": 2}


class AudioQueue:
    """Heap-based priority queue with a single worker thread.

    Three priority levels — alert | normal | routine — dispatched via heapq
    ordering on (priority_rank, sequence_number). An alert always overtakes
    pending normals/routines. FIFO within the same priority level.
    """

    def __init__(self, state, max_depth: int = 5, staleness_seconds: float = 20.0, narration_stream=None) -> None:
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
        self._narration_stream = narration_stream
        self._loop = None  # captured lazily — see _publish_event

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
        self._publish_event(job, "queued")

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

    def _publish_event(self, job, status: str) -> None:
        """Phase 23 — thread-safe NarrationStream publish. No-op if not wired.

        Uses state.audio_hub_loop (captured at daemon startup from uvicorn's
        running loop) so cross-loop scheduling is correct. The previous lazy
        ``asyncio.get_event_loop_policy().get_event_loop()`` capture could
        bind to the worker thread's loop, leaving subscriber queues stranded
        on uvicorn's loop and silently swallowing every event.
        """
        if self._narration_stream is None:
            return
        try:
            import asyncio
            import time
            from claude_code_talker.narration_stream import NarrationEvent
            loop = getattr(self._state, "audio_hub_loop", None)
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return
            ev = NarrationEvent(
                session_id=getattr(job, "session_id", "") or "",
                timestamp=time.time(),
                text=(job.text or "")[:200],
                voice=getattr(job, "voice", "") or "",
                mode=getattr(job, "mode", "") or "",
                status=status,
            )
            asyncio.run_coroutine_threadsafe(self._narration_stream.publish(ev), loop)
        except Exception:
            # Never let a narration error break audio playback.
            pass

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
                self._publish_event(job, "skipped")
                continue
            self._publish_event(job, "speaking")
            try:
                self._set_speaking(job, True)
                # Engine + voice resolution with cross-engine fallback.
                # If the configured engine doesn't know this voice, look
                # across all registered engines for one that does (handles
                # char-* clone voices routing to xtts, edge voices routing
                # away from piper, etc). When NO engine has the voice
                # (clone not yet generated, voice misnamed, etc.), fall
                # back to the first installed piper voice so the user
                # still hears the narration — better degraded audio than
                # silent skip on a misconfigured voice_ref.
                engine = self._state.engines.get(job.engine_name)
                voice = job.voice
                if engine is None or voice not in (engine.list_voices() or []):
                    found = False
                    for ename, e in self._state.engines.items():
                        try:
                            if voice in (e.list_voices() or []):
                                engine = e
                                job.engine_name = ename
                                found = True
                                break
                        except Exception:
                            continue
                    if not found:
                        piper = self._state.engines.get("piper")
                        piper_voices = piper.list_voices() if piper is not None else []
                        if piper_voices:
                            logging.warning(
                                "voice %r not found in any engine; falling back to piper %r",
                                voice, piper_voices[0],
                            )
                            engine = piper
                            job.engine_name = "piper"
                            voice = job.voice = piper_voices[0]
                        else:
                            raise ValueError(
                                f"voice {voice!r} not found in any engine and piper has no voices installed"
                            )
                # v0.1.0 unification — multi-select audio_outputs drives
                # routing. Set of {"desktop","phone","glasses"}.
                # • "desktop" present → daemon plays locally
                # • "phone" or "glasses" present → daemon publishes to audio_hub
                #   (the phone-side TTSPlayer picks the actual Android output
                #   device based on which is present + USB-Audio availability)
                # Empty set → nothing plays.
                outputs = self._resolve_audio_outputs(job)
                companion_wanted = "phone" in outputs or "glasses" in outputs
                desktop_wanted = "desktop" in outputs
                # 2026-05-11 backpressure: synth is the costly step (LLM-bound TTS).
                # Skip it when the work would be discarded — empty outputs, or
                # companion-only with no live audio_hub subscriber. Desktop play
                # has no subscribe handshake, so its presence always forces synth.
                if not desktop_wanted and not companion_wanted:
                    logging.debug("audio worker: skipping synth — no outputs (sid=%s)", (job.session_id or "")[:8])
                    self._publish_event(job, "skipped")
                    continue
                if companion_wanted and not desktop_wanted and not self._hub_has_subscribers(job):
                    # 2026-05-11 Tier-A.1 — WARN instead of DEBUG with action
                    # hint. Silent skips here cost ~30 min of diagnostic time
                    # because the daemon was correctly configured but the phone
                    # hadn't subscribed to the session's audio-stream. Surface
                    # the misalignment loudly so `tail -f codetalker.log` is
                    # the one-step diagnostic.
                    logging.warning(
                        "CCT-AUDIO: audio_outputs=%s configured for sid=%s but no audio-stream subscriber — "
                        "open this session on the phone (or tap 'Make active') to receive audio",
                        sorted(outputs), (job.session_id or "")[:8],
                    )
                    self._publish_event(job, "skipped")
                    continue
                # 2026-05-11 Tier-1: TTS-cache lookup before synth. Saves the
                # full LLM-bound TTS call when an identical (text, voice,
                # engine, rate, format) tuple was synthesized before. Cache
                # hits typically save 200ms–2s per playback. Misses fall
                # through to engine.synthesize and the bytes get cached for
                # next time.
                wav = self._cache_get(job, voice)
                cache_hit = wav is not None
                if wav is None:
                    wav = engine.synthesize(job.text, voice, job.rate)
                    self._cache_put(job, voice, wav)
                # 2026-05-11 backpressure: only dispatch the hub publish when
                # there is at least one open subscriber. The previous code
                # always dispatched on companion_wanted regardless of who's
                # listening, which (a) leaked the noisy "subscribers=0"
                # warning into the daemon log on every synth and (b) burned
                # asyncio scheduler cycles on no-op coroutines that could
                # accumulate behind a slow event loop. Late subscribers don't
                # get backfill; this matches the live-stream contract.
                if companion_wanted and self._hub_has_subscribers(job):
                    self._publish_to_audio_hub(job, wav)
                elif companion_wanted:
                    # Mixed-output case (desktop + companion, no subscribers).
                    # Desktop still plays, but companion silently misses the
                    # publish. Surface that so the user knows the phone is
                    # configured but not receiving.
                    logging.warning(
                        "CCT-AUDIO: companion sink in audio_outputs=%s for sid=%s but no subscriber — "
                        "desktop plays, phone/glasses silent. Open the session on the device to subscribe.",
                        sorted(outputs), (job.session_id or "")[:8],
                    )
                if desktop_wanted:
                    play_audio_bytes(wav, audio_format=job.audio_format, handle=self._handle)
                if cache_hit:
                    logging.debug("audio worker: cache hit for %r voice=%s engine=%s", job.text[:40], voice, job.engine_name)
                self._publish_event(job, "done")
            except Exception as e:
                logging.warning("audio job failed: %s", e)
                self._publish_event(job, "skipped")
            finally:
                self._set_speaking(job, False)

    def _resolve_audio_outputs(self, job) -> set[str]:
        """v0.1.0 unification — return the set of enabled audio outputs.

        Reads the session's persistent overlay's `audio_outputs` list when
        present (multi-select: {"desktop","phone","glasses"}). Falls back
        to the fleet default driven by the legacy `companion_suppress_desktop`
        cfg flag (True ⇒ {"phone","glasses"} — companion takes over; False
        ⇒ {"desktop","phone","glasses"} — play everywhere). Never raises.
        """
        sid = getattr(job, "session_id", "") or ""
        if sid:
            ps = getattr(self._state, "persistent_sessions", None)
            if ps is not None:
                try:
                    persistent = ps.get(sid)
                except Exception:
                    persistent = None
                if persistent and "audio_outputs" in persistent:
                    val = persistent.get("audio_outputs")
                    if isinstance(val, (list, tuple)):
                        return {str(v) for v in val if v in ("desktop", "phone", "glasses")}
        if bool(getattr(self._state, "cfg", {}).get("companion_suppress_desktop", False)):
            return {"phone", "glasses"}
        return {"desktop", "phone", "glasses"}

    def _set_speaking(self, job, val: bool) -> None:
        """v0.1.0 unification — flip the session's transient is_speaking flag
        so both surfaces' active-state flash can render a strong pulse."""
        sid = getattr(job, "session_id", "") or ""
        if not sid:
            return
        sessions = getattr(self._state, "sessions", None)
        if sessions is None:
            return
        try:
            s = sessions.get(sid)
        except Exception:
            return
        if s is not None:
            try:
                s.is_speaking = val
            except Exception:
                pass

    def _companion_owns_audio(self, job) -> bool:
        """CCT-32 v0.1.0 polish — is an AR companion actively subscribed to this session?

        Returns True when (a) the daemon has a `companion_active_session`
        equal to the job's session_id, AND (b) the audio_hub has at least
        one open subscriber queue for that session. Both checks together
        ensure we only suppress local playback when the companion is
        actually listening — never when it's disconnected.
        """
        sid = getattr(job, "session_id", "") or ""
        if not sid:
            return False
        # 2026-05-11 — multi-active: check membership in the set rather than
        # equality with the single-slot field. The legacy single field is
        # still populated for callers that haven't migrated, but the source
        # of truth is now the set.
        active_set = getattr(self._state, "companion_active_sessions", None)
        if active_set:
            if sid not in active_set:
                return False
        else:
            active = getattr(self._state, "companion_active_session", None)
            if active != sid:
                return False
        hub = getattr(self._state, "audio_hub", None)
        if hub is None:
            return False
        subscribers = getattr(hub, "_subscribers", {})
        return bool(subscribers.get(sid))

    def _cache_get(self, job, voice: str) -> bytes | None:
        """2026-05-11 Tier-1: lookup synthesized audio in state.tts_cache.
        Returns ``None`` on miss or any error so the caller falls through
        to live synthesis. Logs but never raises."""
        cache = getattr(self._state, "tts_cache", None)
        if cache is None:
            return None
        try:
            from claude_code_talker.tts_cache import CacheKey
            key = CacheKey(
                text=job.text,
                voice=voice,
                engine_name=job.engine_name,
                rate=float(job.rate),
                audio_format=job.audio_format,
            )
            return cache.get(key)
        except Exception as e:
            logging.debug("tts_cache.get failed: %s", e)
            return None

    def _cache_put(self, job, voice: str, wav: bytes) -> None:
        """2026-05-11 Tier-1: store freshly-synthesized audio in
        state.tts_cache for future lookup. Best-effort; never raises."""
        if not wav:
            return
        cache = getattr(self._state, "tts_cache", None)
        if cache is None:
            return
        try:
            from claude_code_talker.tts_cache import CacheKey
            key = CacheKey(
                text=job.text,
                voice=voice,
                engine_name=job.engine_name,
                rate=float(job.rate),
                audio_format=job.audio_format,
            )
            cache.put(key, wav)
        except Exception as e:
            logging.debug("tts_cache.put failed: %s", e)

    def _hub_has_subscribers(self, job) -> bool:
        """2026-05-11 backpressure: return True iff audio_hub has at least one
        open subscriber queue for this job's session. Used to short-circuit
        synthesis when the only configured output is companion-side but no
        AR/phone client is currently listening — saves an LLM-bound TTS call
        per dead-letter narration."""
        sid = getattr(job, "session_id", "") or ""
        if not sid:
            return False
        hub = getattr(self._state, "audio_hub", None)
        if hub is None:
            return False
        subs = getattr(hub, "_subscribers", {}).get(sid, [])
        return bool(subs)

    def _publish_to_audio_hub(self, job, wav: bytes) -> None:
        """CCT-31 — best-effort fan-out of synthesized audio to AudioStreamHub.

        Runs in the worker thread; uses run_coroutine_threadsafe to dispatch
        publish() onto the hub's owning event loop. Logs the dispatch result
        so v0.1.0 polish diagnostics can trace why a phone subscriber might
        not be receiving bytes (silent failures here are why early Phase 2
        audio tests came back empty).
        """
        if not wav:
            logging.warning("CCT-31: skipping audio_hub publish — empty wav")
            return
        hub = getattr(self._state, "audio_hub", None)
        if hub is None:
            logging.warning("CCT-31: state.audio_hub is None; cannot fan out")
            return
        sid = getattr(job, "session_id", "") or ""
        if not sid:
            logging.info("CCT-31: AudioJob has no session_id; skipping fan-out")
            return
        loop = getattr(self._state, "audio_hub_loop", None)
        if loop is None:
            logging.warning("CCT-31: state.audio_hub_loop is None; cannot fan out (no async loop)")
            try:
                import asyncio
                loop = asyncio.get_event_loop_policy().get_event_loop()
            except Exception:
                return
        subs = getattr(hub, "_subscribers", {}).get(sid, [])
        logging.warning(
            "CCT-31: publishing %d bytes to audio_hub sid=%s subscribers=%d",
            len(wav), sid[:8], len(subs),
        )
        try:
            import asyncio
            asyncio.run_coroutine_threadsafe(hub.publish(sid, wav), loop)
        except Exception as e:
            logging.warning("CCT-31: hub.publish dispatch failed: %s", e)
