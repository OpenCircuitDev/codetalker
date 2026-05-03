"""Mode C: live narration."""
from __future__ import annotations

import asyncio
import logging

from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.event_buffer import Event, EventBuffer
from claude_code_talker.cadence.base import CadenceStrategy
from claude_code_talker.audio import AudioJob
from claude_code_talker.teacher_mode import merge_teacher_into_prompt, max_tokens_for


LIVE_NARRATION_PROMPT = """\
You are narrating Claude Code's work in real time for an audio listener.

Default behavior is play-by-play: report what Claude is doing right now —
which tools are firing, what files are being touched, which steps just
completed, any findings or errors. Lean factual.

Rules:
- ONE short sentence (max 30 words) of spoken English. Present or past tense.
- Mention tool actions and file targets briefly ("editing auth.py", "running
  tests", "reading the spec").
- Surface findings, errors, and decisions when they appear in the events.
- Skip pure noise (long stretches of identical reads); compress them
  ("scanning a few config files") rather than enumerate.
- No markdown, no lists. Just spoken English.

If TEACHER MODE directives appear below, follow them — they will reshape this
narration to also explain WHY the actions matter, anchored to the user's
most recent USER_PROMPT.

RECENT EVENTS (most recent last; USER lines = what the user asked for):
{events}

NARRATION:"""


class LiveMode(ModeStrategy):
    name = "live"

    def __init__(self, provider, cadence: CadenceStrategy, event_buffer: EventBuffer, audio_queue, cfg: dict, narration_log=None, sessions=None):
        self.provider = provider
        self.cadence = cadence
        self.event_buffer = event_buffer
        self.audio_queue = audio_queue
        self.cfg = cfg
        self.narration_log = narration_log  # Phase 11: optional NarrationLog
        self.sessions = sessions  # Phase 8.6: SessionRegistry for per-session voice
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_session_id = ""  # set by hook handler before submitting

    # build() satisfies ModeStrategy; not used in production
    def build(self, prose_entries, tool_uses, todos, cfg):
        return ""

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self.event_buffer.subscribe(self._on_event)
        self._task = asyncio.create_task(self._cadence_loop())

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _on_event(self, event: Event) -> None:
        # runs in EventBuffer's caller's thread (the MCP tool handler)
        decision = self.cadence.on_event(event)
        if decision.fire_immediately and self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._narrate(decision.events, priority="alert"),
                self._loop,
            )

    async def _cadence_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(0.5)
                decision = self.cadence.tick()
                if decision.fire_periodic:
                    await self._narrate(decision.events, priority="normal")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning("live cadence loop: %s", e)

    async def _narrate(self, events, priority):
        if not events:
            return
        prompt = self._build_prompt(events)
        budget = float((self.cfg.get("live") or {}).get("llm_latency_budget_seconds", 8.0))
        # Token budget driven by teacher.verbosity (concise/standard/expanded).
        # Resolve from the active session's cfg so per-session verbosity wins.
        teacher_cfg_for_tokens = self.cfg.get("teacher_mode")
        if self.sessions is not None and self._current_session_id:
            try:
                session_cfg = self.sessions.config_for(self._current_session_id)
                teacher_cfg_for_tokens = session_cfg.get("teacher_mode") or teacher_cfg_for_tokens
            except Exception:
                pass
        max_tokens = max_tokens_for(teacher_cfg_for_tokens, default=150)
        try:
            text = await asyncio.wait_for(
                self.provider.complete(prompt, max_tokens=max_tokens),
                timeout=budget,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logging.debug("live narration skipped: %s", e)
            return

        text = (text or "").strip()
        if not text:
            return

        # Per-session voice: look up the resolved cfg for the session that
        # most recently fired a hook. Each session keeps its own voice/
        # engine/rate via profile or live_overlay; this lets multiple live
        # sessions narrate with distinct voices.
        session_cfg = self.cfg
        if self.sessions is not None and self._current_session_id:
            try:
                session_cfg = self.sessions.config_for(self._current_session_id)
            except Exception:
                session_cfg = self.cfg
        voice_cfg = session_cfg.get("voice") or {}
        voice = voice_cfg.get("model")
        rate = float(voice_cfg.get("rate", 1.0))
        # Default engine to piper when the resolved cfg doesn't set one
        # (happens when a profile sets voice.model but not voice.engine).
        engine_name = voice_cfg.get("engine") or "piper"
        if not voice:
            logging.debug("live narration skipped: no voice configured")
            return

        self.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, priority=priority,
            engine_name=engine_name,
        ))
        # Phase 11: append to narration audit log (best-effort, non-blocking).
        if self.narration_log is not None:
            try:
                from claude_code_talker.narration_log import NarrationEntry
                self.narration_log.append(NarrationEntry(
                    timestamp=__import__("time").time(),
                    session_id=self._current_session_id,
                    text=text,
                    voice=voice or "",
                    engine=engine_name or "",
                    mode="live",
                    priority=priority,
                ))
            except Exception as _e:
                logging.debug("narration log append failed: %s", _e)

    def _build_prompt(self, events) -> str:
        lines = []
        if not events:
            lines.append("(no events)")
        else:
            t0 = events[0].timestamp
            for ev in events[-15:]:
                dt = ev.timestamp - t0
                meta = ev.metadata
                if ev.type == "USER_PROMPT":
                    snippet = (meta.get("text") or "")[:200]
                    lines.append(f"[T+{dt:.1f}s USER asked] {snippet}")
                elif ev.type == "PROSE":
                    snippet = (meta.get("text") or "")[:160]
                    lines.append(f"[T+{dt:.1f}s ASSISTANT said] {snippet}")
                elif ev.type == "NOTIFICATION":
                    lines.append(f"[T+{dt:.1f}s NOTIFICATION] {meta.get('message', '')[:120]}")
                elif ev.type == "PRE_TOOL":
                    lines.append(f"[T+{dt:.1f}s tool→ {meta.get('tool_name', '?')}]")
                elif ev.type == "POST_TOOL":
                    ok = "ok" if meta.get('success', True) else "FAILED"
                    lines.append(f"[T+{dt:.1f}s tool← {meta.get('tool_name', '?')} {ok}]")
        # Resolved cfg for the most recent active session — its teacher_mode
        # overlay should drive narration shape (per-session control).
        teacher_cfg = self.cfg.get("teacher_mode")
        if self.sessions is not None and self._current_session_id:
            try:
                session_cfg = self.sessions.config_for(self._current_session_id)
                teacher_cfg = session_cfg.get("teacher_mode") or teacher_cfg
            except Exception:
                pass
        base = LIVE_NARRATION_PROMPT.format(events="\n".join(lines))
        return merge_teacher_into_prompt(base, teacher_cfg)
