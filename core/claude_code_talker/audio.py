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
    # Phase 2 — id of the AudioJobRegistry entry tracking this job's
    # state_history. Populated by AudioQueue.submit() when the daemon
    # has wired a registry; remains empty on test fixtures that
    # construct an AudioQueue without one.
    registry_job_id: str = ""


_PRIORITY_RANK = {"alert": 0, "normal": 1, "routine": 2}


class AudioQueue:
    """Heap-based priority queue with a single worker thread.

    Three priority levels — alert | normal | routine — dispatched via heapq
    ordering on (priority_rank, sequence_number). An alert always overtakes
    pending normals/routines. FIFO within the same priority level.
    """

    def __init__(self, state, max_depth: int = 5, staleness_seconds: float = 8.0, narration_stream=None) -> None:
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

    def skip_current(self, session_id: str | None = None) -> dict:
        """User-initiated skip: stop current playback + drain pending jobs.

        2026-05-21 — closes a real user need ("I've got it, stop talking";
        "wait, that's wrong — I need to jump in"). Reuses the same
        _PlaybackHandle.stop() mechanism that alert-priority jobs use
        to interrupt current playback, then drains the queue of pending
        jobs so the next narration is genuinely fresh instead of catching
        up through a backlog of stale ones.

        Args:
            session_id: when set, drops only pending jobs for that
                session and only interrupts current playback if the
                in-flight job is from that session. When None, drops
                everything and interrupts unconditionally. Most UI taps
                of the global skip button pass None.

        Returns:
            {"interrupted": bool, "dropped": int} — for the UI to
            confirm the skip actually changed state.
        """
        # Interrupt current playback. The handle's stop() is idempotent —
        # safe to call when nothing is playing.
        self._handle.stop()
        # Drain the queue. The drop-on-overlap pattern below mirrors
        # AudioQueue.submit's existing drop logic; we just filter on
        # session_id when one is provided.
        dropped: list[AudioJob] = []
        with self._cv:
            kept: list[tuple] = []
            for tup in self._queue:
                _, _, job = tup
                if session_id is None or job.session_id == session_id:
                    dropped.append(job)
                else:
                    kept.append(tup)
            if dropped:
                self._queue = kept
                heapq.heapify(self._queue)
        for job in dropped:
            logging.info(
                "CCT-AUDIO: dropped by user skip sid=%s text=%r",
                (job.session_id or "")[:8], (job.text or "")[:60],
            )
            self._registry_transition(
                job, "skipped", gate="user_skip", reason="user_initiated",
            )
            self._publish_event(job, "skipped")
        return {"interrupted": True, "dropped": len(dropped)}

    def submit(self, job: AudioJob) -> None:
        if not job.enqueued_at:
            import time
            job.enqueued_at = time.time()
        self._register_job(job)
        # 2026-05-17 — drop-on-overlap for currency. When a non-alert job
        # for session X arrives, drop any pending (not-yet-popped) non-alert
        # jobs already in the queue for the same session. Rationale: with
        # 12s cadence + multi-session pressure, the queue accumulated 5+
        # narrations deep, and the user heard event commentary from 60s+
        # ago — by the time it played, the events were ancient news. The
        # newer narration supersedes the older one because each LLM call
        # already covers the most-recent event window for its session.
        # Alerts never get dropped (errors, notifications, etc.).
        dropped_for_freshness: list[AudioJob] = []
        with self._cv:
            self._seq += 1
            rank = _PRIORITY_RANK.get(job.priority, 1)
            if job.priority != "alert" and job.session_id:
                kept: list[tuple] = []
                for tup in self._queue:
                    _, _, existing = tup
                    if (
                        existing.priority != "alert"
                        and existing.session_id == job.session_id
                    ):
                        dropped_for_freshness.append(existing)
                    else:
                        kept.append(tup)
                if dropped_for_freshness:
                    self._queue = kept
                    heapq.heapify(self._queue)
            heapq.heappush(self._queue, (rank, self._seq, job))
            self._enforce_depth_locked()
            self._cv.notify()
        if job.priority == "alert":
            self._handle.stop()  # interrupt current playback
        # Audit each drop so the daemon log explains why prior narrations
        # never reached the user. Without this the silent supersede looks
        # identical to a stuck queue.
        for stale in dropped_for_freshness:
            logging.info(
                "CCT-AUDIO: dropped stale-by-overlap sid=%s text=%r (superseded by newer job)",
                (stale.session_id or "")[:8], (stale.text or "")[:60],
            )
            self._registry_transition(
                stale, "skipped",
                gate="overlap", reason="superseded_by_newer",
            )
            self._publish_event(stale, "skipped")
        self._registry_transition(job, "queued", gate="dispatch")
        self._publish_event(job, "queued")

    def _register_job(self, job: AudioJob) -> None:
        """Phase 2 — create the AudioJobRegistry entry that owns this
        job's state_history. No-op when state has no registry wired."""
        if job.registry_job_id:
            return
        registry = getattr(self._state, "audio_job_registry", None)
        if registry is None:
            return
        try:
            from claude_code_talker.schemas import VoiceConfig
            voice = VoiceConfig(
                engine=job.engine_name if job.engine_name in (
                    "piper", "edge", "elevenlabs", "openai", "xtts"
                ) else "piper",
                model=job.voice or "",
                rate=float(job.rate) if 0.5 <= float(job.rate) <= 2.0 else 1.0,
            )
            entry = registry.create(
                session_id=job.session_id or "",
                text=job.text or "",
                voice=voice,
            )
            job.registry_job_id = entry.job_id
        except Exception:
            # Registry failure is diagnostic-only — never block audio.
            pass

    def _registry_transition(
        self,
        job: AudioJob,
        to_state: str,
        *,
        gate: str,
        reason: str | None = None,
        publish_key: str | None = None,
        bytes_synthesized: int | None = None,
        error: str | None = None,
    ) -> None:
        """Phase 2 — append a StateTransition to this job's audit trail.
        Phase 4 — also emit AudioJobStateChanged so SSE subscribers see
        gate decisions live. No-op when state has no registry or the
        job was never registered."""
        if not job.registry_job_id:
            return
        registry = getattr(self._state, "audio_job_registry", None)
        if registry is None:
            return
        try:
            updated = registry.transition(
                job.registry_job_id,
                to_state=to_state,
                gate=gate,
                reason=reason,
                publish_key=publish_key,
                bytes_synthesized=bytes_synthesized,
                error=error,
            )
        except Exception:
            return
        # Phase 4 — emit AudioJobStateChanged. publish_threadsafe is
        # required: the worker runs in a thread, not the daemon loop.
        bus = getattr(self._state, "event_bus", None)
        if bus is None or updated is None:
            return
        try:
            from claude_code_talker.schemas import AudioJobStateChanged
            import time as _t
            from_state = (
                updated.state_history[-1].from_state
                if updated.state_history else "created"
            )
            bus.publish_threadsafe(AudioJobStateChanged(
                at=_t.time(),
                job_id=job.registry_job_id,
                session_id=job.session_id or "",
                from_state=from_state,
                to_state=to_state,
                gate=gate,
                reason=reason,
            ))
        except Exception:
            pass

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
            # Drop stale non-alert jobs.
            # 2026-05-17 — the staleness default tightened to 8s (server.py)
            # so this becomes the per-job currency floor: even if a job
            # survived overlap-dedup at submit time, it gets killed at
            # pop-time if more than 8s have elapsed since enqueue.
            # Kept at DEBUG (not INFO) so unit tests with sub-second
            # staleness don't slow down under synchronous stderr handlers.
            # The audit trail captures the drop via registry_transition.
            if job.priority != "alert" and (time.time() - job.enqueued_at) > self._staleness:
                age = time.time() - job.enqueued_at
                logging.debug(
                    "CCT-AUDIO: dropped stale-by-age sid=%s age=%.1fs text=%r",
                    (job.session_id or "")[:8], age, (job.text or "")[:60],
                )
                self._registry_transition(
                    job, "skipped", gate="staleness", reason="stale"
                )
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
                # v0.1.0 unification — multi-session round-robin routing.
                # When companion is wanted, decide which hub key receives
                # the audio (typically companion_active_session, so the
                # phone — subscribed to that one stream — hears every
                # opted-in session in turn) and whether to prepend an
                # intro tag identifying the speaker.
                route_key = ""
                synth_text = job.text
                if companion_wanted:
                    route = self._decide_multi_session(job)
                    route_key = route.publish_to_session_id
                    if route.intro_text:
                        synth_text = route.intro_text + job.text
                    if not route_key:
                        # Strategy says drop the companion path (e.g., no
                        # companion-active session paired). Treat the same
                        # as if companion wasn't requested.
                        companion_wanted = False
                # Record the routing decision in the audit trail.
                self._registry_transition(
                    job,
                    "routing",
                    gate="route",
                    publish_key=route_key or None,
                )
                # 2026-05-11 backpressure: synth is the costly step (LLM-bound TTS).
                # Skip it when the work would be discarded — empty outputs, or
                # companion-only with no live audio_hub subscriber. Desktop play
                # has no subscribe handshake, so its presence always forces synth.
                if not desktop_wanted and not companion_wanted:
                    logging.debug("audio worker: skipping synth — no outputs (sid=%s)", (job.session_id or "")[:8])
                    self._registry_transition(
                        job,
                        "skipped",
                        gate="output_check",
                        reason="no_audio_outputs",
                    )
                    self._publish_event(job, "skipped")
                    continue
                # 2026-05-17 — desktop fallback. The previous behavior dropped
                # the WAV entirely when the user's audio_outputs was companion-
                # only AND the phone subscriber was momentarily absent (long-
                # poll race, Wi-Fi blip, Doze). That caused multi-day silence
                # for any session whose audio_outputs got set to ['phone']
                # by the SessionDetailScreen audio destination picker — every
                # missed subscriber moment lost a real narration.
                #
                # Desktop has no subscriber handshake (winsound.PlaySound goes
                # to the default audio output) and is a reliable last-mile
                # delivery channel. When the configured-companion path has
                # no subscriber, opt into desktop fallback for THIS job so
                # the user always hears their narration on the PC, even if
                # the phone happened to be between polls. The audio_outputs
                # setting is honored on the next job (where the phone may
                # again be subscribed); this only adds a fallback per-job,
                # not a permanent state change.
                if companion_wanted and not self._hub_has_subscribers_for_key(route_key):
                    if not desktop_wanted:
                        logging.warning(
                            "CCT-AUDIO: audio_outputs=%s configured for sid=%s but no audio-stream "
                            "subscriber on key=%s — falling back to DESKTOP for this job so the user "
                            "still hears the narration",
                            sorted(outputs), (job.session_id or "")[:8], (route_key or "")[:8],
                        )
                        desktop_wanted = True
                # 2026-05-11 Tier-1: TTS-cache lookup before synth.
                self._registry_transition(job, "synthesizing", gate="synth")
                wav = self._cache_get(job, voice)
                cache_hit = wav is not None
                if wav is None:
                    # Use synth_text (with optional intro prefix) so the
                    # voice tag is part of the rendered audio.
                    wav = engine.synthesize(synth_text, voice, job.rate)
                    self._cache_put(job, voice, wav)
                self._registry_transition(
                    job,
                    "publishing",
                    gate="hub",
                    bytes_synthesized=len(wav) if wav else 0,
                )
                if companion_wanted and self._hub_has_subscribers_for_key(route_key):
                    self._publish_to_audio_hub_keyed(route_key, wav)
                    # Track last-played source session so the routing
                    # strategy can suppress redundant intros for chatty
                    # back-to-back jobs from the same workspace.
                    try:
                        setattr(self._state, "_last_played_session_id", job.session_id)
                    except Exception:
                        pass
                elif companion_wanted:
                    logging.warning(
                        "CCT-AUDIO: companion sink in audio_outputs=%s for sid=%s but no subscriber on key=%s — "
                        "desktop plays, phone/glasses silent. Open the session on the device to subscribe.",
                        sorted(outputs), (job.session_id or "")[:8], (route_key or "")[:8],
                    )
                if desktop_wanted:
                    play_audio_bytes(wav, audio_format=job.audio_format, handle=self._handle)
                if cache_hit:
                    logging.debug("audio worker: cache hit for %r voice=%s engine=%s", job.text[:40], voice, job.engine_name)
                self._registry_transition(job, "played", gate="hub")
                self._publish_event(job, "done")
            except Exception as e:
                logging.warning("audio job failed: %s", e)
                self._registry_transition(
                    job, "errored", gate="synth", error=str(e)
                )
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
        open subscriber queue for this job's session."""
        return self._hub_has_subscribers_for_key(getattr(job, "session_id", "") or "")

    def _hub_has_subscribers_for_key(self, key: str) -> bool:
        """v0.1.0 unification — same as _hub_has_subscribers but for an
        arbitrary hub key (not necessarily the job's source session). Used
        when multi-session routing fans audio into the active session's
        stream rather than the source session's stream."""
        if not key:
            return False
        hub = getattr(self._state, "audio_hub", None)
        if hub is None:
            return False
        subs = getattr(hub, "_subscribers", {}).get(key, [])
        return bool(subs)

    def _decide_multi_session(self, job):
        """v0.1.0 unification — consult the routing strategy for this job.

        Returns a RoutingDecision telling the worker which hub key to
        publish to and whether to prepend a spoken intro tag identifying
        the speaker. Strategy lives in
        claude_code_talker.companion.multi_session_routing — replace it
        there to change behavior without touching audio.py.
        """
        import time as _t
        from claude_code_talker.companion.multi_session_routing import (
            decide_multi_session_route,
            RoutingDecision,
        )
        try:
            # Build the inputs the strategy needs.
            #
            # 2026-05-16 root-cause fix — `opted_in` was previously
            # computed by intersecting in-memory live sessions
            # (state.sessions.list_active()) with persistent overlay
            # entries that had phone/glasses in audio_outputs. That made
            # routing fragile: after a daemon restart, state.sessions is
            # empty until each session's hook fires, so opted_in stayed
            # empty and Strategy C dropped every WAV via its
            # `job_session_id not in opted_in_sessions` guard. The phone
            # had hub subscribers (audio_misaligned reported 0!) but
            # those subscribers received nothing because the publish
            # never happened.
            #
            # Persistent overlay is the canonical opt-in signal — a user
            # sets audio_outputs=[phone] on a session and that fact
            # survives daemon restart, in-memory eviction, etc. Use it
            # directly. The downstream `_hub_has_subscribers_for_key`
            # check already prevents synth for sessions with no live
            # subscriber, so reading all opted-in sessions from
            # persistent overlay can't cause spurious work.
            ps = getattr(self._state, "persistent_sessions", None)
            opted_in: list[str] = []
            if ps is not None:
                try:
                    sids = ps.list()
                except Exception:
                    sids = []
                for sid in sids:
                    persistent = ps.get(sid)
                    if not persistent:
                        continue
                    outs = persistent.get("audio_outputs") or []
                    if isinstance(outs, (list, tuple)) and (
                        "phone" in outs or "glasses" in outs
                    ):
                        opted_in.append(sid)
            companion_active = getattr(self._state, "companion_active_session", None)
            workspace_group = None
            # 2026-05-18 — resolve display_name via the same priority chain
            # the UI uses (views._resolve_display_name): persistent override
            # → CC custom_title → VS Code label → slug → catalog title →
            # project_slug → UUID prefix. The raw persistent.display_name
            # is the UUID-prefix placeholder for unmodified sessions, so
            # using it directly would speak "87b24267-c8f:" — the priority
            # chain falls back to catalog data for those cases.
            display_name = None
            sid = getattr(job, "session_id", "") or ""
            persistent_for_sid = None
            if ps is not None:
                try:
                    persistent_for_sid = ps.get(sid)
                    if persistent_for_sid:
                        workspace_group = persistent_for_sid.get("workspace_group")
                except Exception:
                    persistent_for_sid = None
            try:
                from claude_code_talker.views import _resolve_display_name
                catalog = getattr(self._state, "catalog", None)
                catalog_entry = None
                if catalog is not None and sid:
                    try:
                        catalog_entry = catalog.entry_for(sid)
                    except Exception:
                        catalog_entry = None
                display_name = _resolve_display_name(
                    persistent=persistent_for_sid,
                    catalog_entry=catalog_entry,
                    fallback_sid=sid,
                )
                # _resolve_display_name returns sid[:12] as last-resort;
                # treat that as "no real name" for the intro-tag purposes.
                if display_name == sid[:12]:
                    display_name = None
            except Exception:
                display_name = None
            # Evidence-gathering log so the routing decision is visible
            # in the daemon's stderr for every audio job. Keeps the
            # debugging cycle short the next time a "no audio" report
            # comes in -- one log line shows opted_in size, job sid,
            # active sid, and the resolved publish key.
            decision = decide_multi_session_route(
                job_session_id=sid,
                job_workspace_group=workspace_group,
                job_display_name=display_name,
                opted_in_sessions=opted_in,
                companion_active_session=companion_active,
                last_played_session_id=getattr(self._state, "_last_played_session_id", None),
                now=_t.time(),
            )
            logging.warning(
                "CCT-AUDIO route: job_sid=%s opted_in=%d active=%s -> publish_key=%s intro=%r",
                (getattr(job, "session_id", "") or "")[:8],
                len(opted_in),
                (companion_active or "<none>")[:8],
                (decision.publish_to_session_id or "<DROP>")[:8],
                decision.intro_text,
            )
            return decision
        except Exception as e:
            logging.warning("CCT-AUDIO: multi-session route decision failed: %s; "
                            "falling back to per-session publish", e)
            return RoutingDecision(
                publish_to_session_id=getattr(job, "session_id", "") or "",
            )

    def _publish_to_audio_hub_keyed(self, key: str, wav: bytes) -> None:
        """v0.1.0 unification — publish to an arbitrary hub key.

        Like _publish_to_audio_hub but lets the worker choose a different
        hub key from the source session_id, so the multi-session strategy
        can fan all opted-in sessions into one stream.
        """
        if not wav or not key:
            return
        hub = getattr(self._state, "audio_hub", None)
        if hub is None:
            return
        loop = getattr(self._state, "audio_hub_loop", None)
        if loop is None:
            try:
                import asyncio
                loop = asyncio.get_event_loop_policy().get_event_loop()
            except Exception:
                return
        subs = getattr(hub, "_subscribers", {}).get(key, [])
        logging.info(
            "CCT-AUDIO: publish keyed → %d bytes to key=%s subscribers=%d",
            len(wav), key[:8], len(subs),
        )
        try:
            import asyncio
            asyncio.run_coroutine_threadsafe(hub.publish(key, wav), loop)
        except Exception as e:
            logging.warning("CCT-AUDIO: keyed publish dispatch failed: %s", e)

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
