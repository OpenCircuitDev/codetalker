"""Brief-mode quiet-stretch trigger.

Most brief-mode narration fires at end-of-turn via the Stop hook
(see hooks.handle_stop). That's enough when Claude is finishing turns
at a normal cadence. But if a single turn drags on for many minutes
(long agentic loop, multi-file refactor, slow Bash command), the user
hears nothing between the user_prompt summary and the eventual Stop
brief — and worries the session went sideways.

This loop fills that gap: when a brief-mode session has produced
events but no narration in >N seconds, fire a brief mid-turn so the
user gets a "here's where we are" update.

Architecture: a single asyncio task started from the daemon boot
(autostart hook, alongside LiveMode.start). On each tick (default
30s) it walks state.sessions.list_active(), evaluates each session
via the pure _should_fire_for_session decision, and dispatches via
the same flow that tts_handle_stop uses (collect_turn → BriefMode
.build_async → AudioJob).

Config:
  cfg.briefs.quiet_stretch_seconds  default 120; 0 disables.
  cfg.briefs.quiet_stretch_tick     default 30; lower = more checks.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from claude_code_talker.audio import AudioJob
from claude_code_talker.hooks import handle_stop


log = logging.getLogger(__name__)


@dataclass
class QuietStretchFireDecision:
    """Result of evaluating one session at one tick.

    `fire` is the boolean outcome; `reason` names the gate that blocked
    it (or "fire" when fire is True) so we can surface it in the daemon
    log for diagnosis without a debugger attached. Pure data — no side
    effects. The dispatch is the caller's responsibility.
    """
    fire: bool
    reason: str


@dataclass
class HeartbeatFireDecision:
    """Result of evaluating one session for heartbeat trigger at one tick.

    Similar to QuietStretchFireDecision but for the heartbeat signal
    ("Still here.") that fires when:
      1. The session has been silent for >N seconds (no recent narration).
      2. BUT hooks have fired within the last M seconds (Claude is working,
         just not narrating).

    This distinguishes "daemon alive, Claude thinking" from "daemon dead"
    or "Claude stuck" during long quiet stretches.
    """
    fire: bool
    reason: str


def _resolved_active_mode(session_cfg: dict) -> str:
    """Pick the active_mode from a resolved session cfg.

    SessionRegistry.config_for returns the merged base+profile+overlay
    cfg. The active_mode lives at top level after resolution.
    """
    return str(session_cfg.get("active_mode") or "brief")


def _should_fire_for_session(
    *,
    now: float,
    last_brief_at: float,
    last_hook_at: float,
    session_cfg: dict,
    threshold_seconds: float,
) -> QuietStretchFireDecision:
    """Pure decision: should the quiet-stretch trigger fire for this session?

    Returns fire=True only when ALL of:

      1. threshold_seconds > 0 (feature enabled).
      2. session's active_mode resolves to 'brief'. We deliberately
         skip 'live' because live's cadence loop already produces
         continuous narration, and 'direct' is for raw tool output
         (no summarizing makes sense).
      3. There has been at least one hook fire since the last brief
         we produced. Without this, an idle session would emit a
         new brief every threshold seconds, even though nothing
         changed.
      4. (now - last_brief_at) >= threshold_seconds.

    The function is pure so unit tests don't need to spin up a daemon.
    """
    if threshold_seconds <= 0:
        return QuietStretchFireDecision(False, "feature_disabled")
    if _resolved_active_mode(session_cfg) != "brief":
        return QuietStretchFireDecision(False, "active_mode_not_brief")
    # last_brief_at == 0 means "we have never fired a brief for this
    # session". That's fine — the very first brief is still gated on
    # last_hook_at > 0 (so we don't fire for a session that was just
    # registered but produced no events yet).
    if last_hook_at <= 0:
        return QuietStretchFireDecision(False, "no_hooks_yet")
    if last_brief_at > 0 and last_hook_at <= last_brief_at:
        return QuietStretchFireDecision(False, "no_new_activity")
    elapsed = now - max(last_brief_at, 0.0)
    if elapsed < threshold_seconds:
        return QuietStretchFireDecision(False, "within_threshold")
    return QuietStretchFireDecision(True, "fire")


def _should_fire_heartbeat_for_session(
    *,
    now: float,
    last_narration_at: float,
    last_hook_at: float,
    session_cfg: dict,
    heartbeat_enabled: bool,
    silence_threshold_seconds: float,
    active_window_seconds: float,
) -> HeartbeatFireDecision:
    """Pure decision: should the heartbeat trigger fire for this session?

    The heartbeat is a one-syllable "Still here." signal that fires when:
      1. heartbeat_enabled is True (feature enabled).
      2. session's active_mode resolves to 'brief'.
      3. (now - last_narration_at) >= silence_threshold_seconds (user has
         heard silence for N seconds).
      4. last_hook_at is within active_window_seconds of now (daemon &
         Claude are actively working, just not narrating).
      5. NOT already briefed recently by quiet-stretch (avoid duplicate
         narration in the same tick).

    The heartbeat does NOT fire if last_hook_at is stale (>= 60s ago),
    because that means Claude really stopped — silence is correct.

    The function is pure so unit tests don't need to spin up a daemon.
    """
    if not heartbeat_enabled:
        return HeartbeatFireDecision(False, "heartbeat_disabled")
    if _resolved_active_mode(session_cfg) != "brief":
        return HeartbeatFireDecision(False, "active_mode_not_brief")
    if last_hook_at <= 0:
        return HeartbeatFireDecision(False, "no_hooks_yet")
    # Check if daemon/Claude are actively working (last_hook_at within window).
    hook_age = now - last_hook_at
    if hook_age > active_window_seconds:
        return HeartbeatFireDecision(False, "hooks_too_stale")
    # Check if user has been in silence long enough to warrant a heartbeat.
    silence_duration = now - last_narration_at
    if silence_duration < silence_threshold_seconds:
        return HeartbeatFireDecision(False, "silence_below_threshold")
    return HeartbeatFireDecision(True, "fire")


class BriefQuietStretchLoop:
    """Background asyncio task that fires brief-mode narration during long quiet stretches.

    The loop is cheap by design: each tick walks the active-session list
    once, runs the pure decision per session, and only does I/O
    (transcript read + LLM call + audio submit) for sessions that
    actually need to fire. Sessions in live/direct mode short-circuit
    at the decision step.

    Lifecycle mirrors LiveMode: instantiate with a reference to the
    daemon state, call .start() from the asyncio startup hook, .shutdown()
    on daemon stop.
    """

    def __init__(self, state):
        self.state = state
        self._task: Optional[asyncio.Task] = None
        # Per-session last-brief timestamps. dict[session_id, float].
        # Mirrors LiveMode._last_narrate_by_session so a future merge
        # can unify both into a single "last_audio_narration_at"
        # tracker keyed on session_id.
        self._last_brief_by_session: dict[str, float] = {}
        # Per-session last-heartbeat timestamps. dict[session_id, float].
        # Prevents spamming the same session with heartbeats every tick —
        # fires at most once per heartbeat_silence_seconds interval.
        self._last_heartbeat_by_session: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Config readers
    # ------------------------------------------------------------------

    def _threshold_seconds(self) -> float:
        briefs = (self.state.cfg or {}).get("briefs") or {}
        return float(briefs.get("quiet_stretch_seconds", 120.0))

    def _tick_seconds(self) -> float:
        briefs = (self.state.cfg or {}).get("briefs") or {}
        return float(briefs.get("quiet_stretch_tick", 30.0))

    def _heartbeat_enabled(self) -> bool:
        briefs = (self.state.cfg or {}).get("briefs") or {}
        return bool(briefs.get("heartbeat_enabled", True))

    def _heartbeat_silence_seconds(self) -> float:
        briefs = (self.state.cfg or {}).get("briefs") or {}
        return float(briefs.get("heartbeat_silence_seconds", 30.0))

    def _heartbeat_active_window_seconds(self) -> float:
        briefs = (self.state.cfg or {}).get("briefs") or {}
        return float(briefs.get("heartbeat_active_window_seconds", 60.0))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        # Small initial delay so we don't race the rest of the boot path.
        await asyncio.sleep(2.0)
        while True:
            try:
                await asyncio.sleep(self._tick_seconds())
                await self._tick_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("brief quiet-stretch loop: %s", e)

    async def _tick_once(self) -> None:
        """One tick: walk sessions, fire heartbeats or briefs where the gate says fire.

        Order: check heartbeat FIRST, then brief. Don't fire both for the same
        session in the same tick — heartbeat is a minimal signal and shouldn't
        crowd out a full brief on the same evaluation window.
        """
        threshold = self._threshold_seconds()
        if threshold <= 0:
            return
        now = time.time()
        sessions = self.state.sessions
        if sessions is None:
            return
        try:
            active = sessions.list_active()
        except Exception:
            return

        # Heartbeat config
        hb_enabled = self._heartbeat_enabled()
        hb_silence = self._heartbeat_silence_seconds()
        hb_window = self._heartbeat_active_window_seconds()

        for session in active:
            sid = session.session_id
            try:
                cfg = sessions.config_for(sid)
            except Exception:
                cfg = {}

            # Check heartbeat FIRST.
            if hb_enabled:
                hb_decision = _should_fire_heartbeat_for_session(
                    now=now,
                    last_narration_at=self._last_brief_by_session.get(sid, 0.0),
                    last_hook_at=float(getattr(session, "last_hook_at", 0.0) or 0.0),
                    session_cfg=cfg,
                    heartbeat_enabled=hb_enabled,
                    silence_threshold_seconds=hb_silence,
                    active_window_seconds=hb_window,
                )
                if hb_decision.fire:
                    await self._fire_heartbeat(session, cfg)
                    # Don't fire a brief for this session this tick.
                    continue

            # Check brief.
            decision = _should_fire_for_session(
                now=now,
                last_brief_at=self._last_brief_by_session.get(sid, 0.0),
                last_hook_at=float(getattr(session, "last_hook_at", 0.0) or 0.0),
                session_cfg=cfg,
                threshold_seconds=threshold,
            )
            if not decision.fire:
                continue
            await self._fire_brief(session, cfg)

    async def _fire_heartbeat(self, session, cfg: dict) -> None:
        """Fire a minimal heartbeat signal: "Still here." with no LLM call.

        The heartbeat is pure status — it's a brief "daemon alive, Claude thinking"
        signal. No transcript inspection, no LLM call; just dispatch the static text
        as a routine-priority AudioJob so fresher narrations can overtake it.
        """
        sid = session.session_id
        # Update tracking FIRST so a racing second tick doesn't re-fire.
        self._last_heartbeat_by_session[sid] = time.time()

        # Also advance last_brief_at so the main quiet-stretch gate waits
        # another full threshold window before firing a real brief.
        self._last_brief_by_session[sid] = time.time()

        # Audibility check — respect mute/master state.
        try:
            if not getattr(session, "enabled", True):
                log.debug("brief quiet-stretch: skip heartbeat sid=%s session_muted", sid[:12])
                return
            if not bool(self.state.cfg.get("enabled", True)):
                log.debug("brief quiet-stretch: skip heartbeat sid=%s master_disabled", sid[:12])
                return
        except Exception:
            pass

        # Dispatch heartbeat via audio_queue as routine priority.
        try:
            audio_queue = getattr(self.state, "audio_queue", None)
            if audio_queue is None:
                return
            voice_cfg = (cfg.get("voice") or {})
            engine_name = voice_cfg.get("engine") or "piper"
            engine = self.state.engines.get(engine_name) if self.state.engines else None
            audio_format = getattr(engine, "audio_format", "wav") if engine else "wav"
            audio_queue.submit(AudioJob(
                text="Still here.",
                voice=str(voice_cfg.get("model") or ""),
                rate=float(voice_cfg.get("rate", 1.0)),
                engine_name=engine_name,
                audio_format=audio_format,
                session_id=sid,
                priority="routine",  # Lower priority than brief (normal)
            ))
            log.info("brief quiet-stretch heartbeat fired sid=%s", sid[:12])
        except Exception as e:
            log.warning("brief quiet-stretch heartbeat sid=%s: submit failed: %s", sid[:12], e)

    async def _fire_brief(self, session, cfg: dict) -> None:
        """Run brief-mode against the session's current transcript turn and submit to audio."""
        sid = session.session_id
        transcript_path = getattr(session, "transcript_path", "")
        if not transcript_path or not Path(transcript_path).exists():
            log.debug("brief quiet-stretch: skip sid=%s (no transcript path)", sid[:12])
            return

        # Audibility check — mirrors tts_handle_stop. If the session
        # is muted or master is off, do not produce audio.
        try:
            from claude_code_talker.audio_decisions import is_session_audible
            from claude_code_talker.schemas import MasterConfig
            persistent_store = getattr(self.state, "persistent_sessions", None)
            persistent = persistent_store.get(sid) if persistent_store else None
            if persistent is not None:
                # The persistent dict may not roundtrip into a full Session
                # without extra work; rely on the SessionState.enabled flag
                # + master switch for a pragmatic gate here. The full Session
                # round-trip is the long-term home for this check.
                if not getattr(session, "enabled", True):
                    log.debug(
                        "brief quiet-stretch: skip sid=%s session_muted", sid[:12]
                    )
                    return
            if not bool(self.state.cfg.get("enabled", True)):
                log.debug(
                    "brief quiet-stretch: skip sid=%s master_disabled", sid[:12]
                )
                return
        except Exception:
            # Best-effort gate; if the import or call fails, fall through —
            # downstream audio_queue still has its own audibility wiring.
            pass

        # Build the brief from the current turn.
        brief = self.state.modes.get("brief")
        if brief is None:
            return
        try:
            text = await handle_stop(
                payload={"transcript_path": transcript_path, "cwd": getattr(session, "cwd", "")},
                cfg=cfg,
                mode_a=self.state.modes.get("direct"),
                mode_b=brief,
                # Force the brief path regardless of the daemon's global
                # active_mode — by definition, this loop only fires for
                # sessions whose RESOLVED active_mode is 'brief', and we
                # want the brief output even if the global default isn't.
                active_mode="brief",
            )
        except Exception as e:
            log.warning("brief quiet-stretch sid=%s: build failed: %s", sid[:12], e)
            return

        if not text:
            return

        # Mark as fired regardless of audio submit result, so we don't
        # spin re-firing the same empty turn each tick.
        self._last_brief_by_session[sid] = time.time()

        # Dispatch via audio_queue — voice resolution and routing happen
        # downstream in the audio worker.
        try:
            audio_queue = getattr(self.state, "audio_queue", None)
            if audio_queue is None:
                return
            voice_cfg = (cfg.get("voice") or {})
            engine_name = voice_cfg.get("engine") or "piper"
            engine = self.state.engines.get(engine_name) if self.state.engines else None
            audio_format = getattr(engine, "audio_format", "wav") if engine else "wav"
            audio_queue.submit(AudioJob(
                text=text,
                voice=str(voice_cfg.get("model") or ""),
                rate=float(voice_cfg.get("rate", 1.0)),
                engine_name=engine_name,
                audio_format=audio_format,
                session_id=sid,
            ))
            log.info(
                "brief quiet-stretch sid=%s fired (%d chars)", sid[:12], len(text)
            )
        except Exception as e:
            log.warning(
                "brief quiet-stretch sid=%s: audio submit failed: %s", sid[:12], e
            )
