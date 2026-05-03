"""Mode C: live narration."""
from __future__ import annotations

import asyncio
import logging

from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.event_buffer import Event, EventBuffer
from claude_code_talker.cadence.base import CadenceStrategy
from claude_code_talker.audio import AudioJob
from claude_code_talker.audio_streamer import AudioStreamer
from claude_code_talker.teacher_mode import merge_teacher_into_prompt, max_tokens_for
from claude_code_talker.event_render import summarize_tool_input, summarize_tool_response


# The system portion is kept constant so that Google Gemini's implicit prefix
# caching (>=1024-token prefix) can kick in across cadence calls with the same
# teacher_cfg. Dynamic content (events) is appended AFTER this block via
# _build_prompt so the static prefix is byte-identical across calls.
LIVE_NARRATION_SYSTEM = """\
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
most recent USER_PROMPT."""

# Separator before the dynamic events block. Presence of this exact string is
# used by tests to locate the boundary between static prefix and dynamic suffix.
_EVENTS_HEADER = "---\nRECENT EVENTS (most recent last; USER lines = what the user asked for):\n"

# For backward-compat: the old LIVE_NARRATION_PROMPT constant is kept so
# external code that imported it won't break. It is no longer used internally.
LIVE_NARRATION_PROMPT = (
    LIVE_NARRATION_SYSTEM
    + "\n\n"
    + _EVENTS_HEADER
    + "{events}\n\nNARRATION:"
)

# Hard ceiling on streaming timeout to avoid runaway waits.
_STREAMING_TIMEOUT_CEILING = 30.0


class LiveMode(ModeStrategy):
    name = "live"

    def __init__(self, provider, cadence: CadenceStrategy, event_buffer: EventBuffer, audio_queue, cfg: dict, narration_log=None, sessions=None, session_focus=None):
        self.provider = provider
        self.cadence = cadence
        self.event_buffer = event_buffer
        self.audio_queue = audio_queue
        self.cfg = cfg
        self.narration_log = narration_log  # Phase 11: optional NarrationLog
        self.sessions = sessions  # Phase 8.6: SessionRegistry for per-session voice
        self.session_focus = session_focus  # Phase 13.5B: per-session WHY/CONTEXT block
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

    # ------------------------------------------------------------------
    # Shared helpers: resolve per-session voice/token config
    # ------------------------------------------------------------------

    def _resolve_teacher_cfg(self):
        """Return the teacher_mode cfg dict for the current session (or global)."""
        teacher_cfg = self.cfg.get("teacher_mode")
        if self.sessions is not None and self._current_session_id:
            try:
                session_cfg = self.sessions.config_for(self._current_session_id)
                teacher_cfg = session_cfg.get("teacher_mode") or teacher_cfg
            except Exception:
                pass
        return teacher_cfg

    def _resolve_voice_cfg(self):
        """Return (voice, rate, engine_name) for the current session."""
        session_cfg = self.cfg
        if self.sessions is not None and self._current_session_id:
            try:
                session_cfg = self.sessions.config_for(self._current_session_id)
            except Exception:
                session_cfg = self.cfg
        voice_cfg = session_cfg.get("voice") or {}
        voice = voice_cfg.get("model")
        rate = float(voice_cfg.get("rate", 1.0))
        engine_name = voice_cfg.get("engine") or "piper"
        return voice, rate, engine_name

    def _append_narration_log(self, text: str, voice: str, engine_name: str, priority: str, mode: str = "live") -> None:
        """Best-effort append to the narration audit log."""
        if self.narration_log is None:
            return
        try:
            from claude_code_talker.narration_log import NarrationEntry
            self.narration_log.append(NarrationEntry(
                timestamp=__import__("time").time(),
                session_id=self._current_session_id,
                text=text,
                voice=voice or "",
                engine=engine_name or "",
                mode=mode,
                priority=priority,
            ))
        except Exception as _e:
            logging.debug("narration log append failed: %s", _e)

    # ------------------------------------------------------------------
    # Streaming narration path (Sub-task 1.1)
    # ------------------------------------------------------------------

    async def _narrate_streaming(self, events, priority, verbosity_decision: str = "standard") -> None:
        """Stream LLM output through AudioStreamer, emitting one AudioJob per sentence.

        ``verbosity_decision`` is pre-computed by ``_narrate`` (caller already
        ran _decide_verbosity_for_events and skipped if "skip").
        """
        prompt = self._build_prompt(events)
        budget = float((self.cfg.get("live") or {}).get("llm_latency_budget_seconds", 8.0))
        teacher_cfg = self._resolve_teacher_cfg()
        # Override verbosity with cadence-aware decision (don't mutate original)
        if verbosity_decision in ("concise", "standard", "expanded"):
            teacher_cfg = dict(teacher_cfg) if teacher_cfg else {}
            teacher_cfg["verbosity"] = verbosity_decision
        max_tokens = max_tokens_for(teacher_cfg, default=150)
        voice, rate, engine_name = self._resolve_voice_cfg()

        if not voice:
            logging.debug("live narration skipped: no voice configured")
            return

        # Use 2× the configured budget for streaming (full completion takes longer),
        # capped at the hard ceiling.
        stream_budget = min(budget * 2.0, _STREAMING_TIMEOUT_CEILING)

        def _emit_chunk(chunk: str) -> None:
            chunk = chunk.strip()
            if not chunk:
                return
            self.audio_queue.submit(AudioJob(
                text=chunk,
                voice=voice,
                rate=rate,
                priority=priority,
                engine_name=engine_name,
            ))
            self._append_narration_log(chunk, voice, engine_name, priority, mode="live-stream")

        streamer = AudioStreamer(emit=_emit_chunk)
        try:
            await asyncio.wait_for(
                streamer.consume(self.provider.stream(prompt, max_tokens=max_tokens)),
                timeout=stream_budget,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logging.debug("live streaming narration skipped: %s", e)

    # ------------------------------------------------------------------
    # Main narration entry point — dispatches to streaming or non-streaming
    # ------------------------------------------------------------------

    async def _narrate(self, events, priority):
        if not events:
            return

        # Phase 13.5B: update session focus counter + trigger background header refresh
        if self.session_focus is not None and self._current_session_id:
            focus = self.session_focus.get_or_create(self._current_session_id)
            focus.narrations_since_refresh += 1
            if focus.should_refresh_header():
                # Fire-and-forget: refresh runs in background, never blocks this narration
                asyncio.create_task(focus.refresh_header(self.provider))

        # Sub-task 2.1: cadence-aware verbosity check (applied before provider dispatch)
        verbosity_decision = self._decide_verbosity_for_events(events)
        if verbosity_decision == "skip":
            logging.debug("live narration skipped: no significant events")
            return

        # Dispatch to streaming path when the provider supports it.
        # Use `is True` (strict) to avoid matching truthy mock objects in tests.
        if (
            self.provider is not None
            and getattr(self.provider, "supports_streaming", False) is True
        ):
            await self._narrate_streaming(events, priority, verbosity_decision=verbosity_decision)
            return

        # ---- Non-streaming (original) path ----
        prompt = self._build_prompt(events)
        budget = float((self.cfg.get("live") or {}).get("llm_latency_budget_seconds", 8.0))
        teacher_cfg = self._resolve_teacher_cfg()
        # Override verbosity with cadence-aware decision (don't mutate original)
        if verbosity_decision in ("concise", "standard", "expanded"):
            teacher_cfg = dict(teacher_cfg) if teacher_cfg else {}
            teacher_cfg["verbosity"] = verbosity_decision
        max_tokens = max_tokens_for(teacher_cfg, default=150)
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

        voice, rate, engine_name = self._resolve_voice_cfg()
        if not voice:
            logging.debug("live narration skipped: no voice configured")
            return

        self.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, priority=priority,
            engine_name=engine_name,
        ))
        self._append_narration_log(text, voice, engine_name, priority, mode="live")

    # ------------------------------------------------------------------
    # Cadence-aware verbosity (Sub-task 2.1)
    # ------------------------------------------------------------------

    def _decide_verbosity_for_events(self, events) -> str:
        """Determine the verbosity level for a batch of events.

        Returns one of: "skip", "concise", "standard", "expanded".

        When cfg.live.cadence_aware_verbosity is False, always returns the
        teacher-configured verbosity (no skip, no override).
        """
        live_cfg = self.cfg.get("live") or {}
        cadence_aware = live_cfg.get("cadence_aware_verbosity", True)

        # When the feature is disabled, return the teacher's verbosity unchanged.
        if not cadence_aware:
            teacher_cfg = self._resolve_teacher_cfg() or {}
            verbosity = teacher_cfg.get("verbosity", "standard")
            if verbosity not in ("concise", "standard", "expanded"):
                verbosity = "standard"
            return verbosity

        if not events:
            return "skip"

        max_sig = max(
            (e.significance for e in events if e.significance is not None),
            default=0.0,
        )
        event_count = len(events)

        if max_sig < 0.3 and event_count <= 2:
            return "skip"
        if max_sig < 0.5:
            return "concise"
        if max_sig >= 0.8 and event_count >= 5:
            return "expanded"
        return "standard"

    def _build_prompt(self, events) -> str:
        # --- Static prefix: system instructions + teacher directives (Sub-task 1.2) ---
        # The teacher block is appended to the system portion BEFORE the events so
        # the static prefix grows (and stays byte-identical) when teacher mode is on.
        # Events come LAST, after a fixed separator, so the dynamic tail never
        # disrupts the leading cache-eligible prefix.
        teacher_cfg = self._resolve_teacher_cfg()
        # Build the static section: system text + optional teacher block
        static_section = merge_teacher_into_prompt(LIVE_NARRATION_SYSTEM, teacher_cfg)

        # --- Dynamic suffix: events list ---
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
                    tool = meta.get('tool_name', '?')
                    arg_summary = summarize_tool_input(tool, meta.get('input', ''))
                    if arg_summary:
                        lines.append(f"[T+{dt:.1f}s tool→ {tool} {arg_summary}]")
                    else:
                        lines.append(f"[T+{dt:.1f}s tool→ {tool}]")
                elif ev.type == "POST_TOOL":
                    tool = meta.get('tool_name', '?')
                    success = meta.get('success', True)
                    out_summary = summarize_tool_response(tool, meta.get('response', ''), success)
                    lines.append(f"[T+{dt:.1f}s tool← {tool} {out_summary}]")

        # Phase 13.5B: inject per-session SESSION FOCUS block (WHY/CONTEXT)
        focus_block = ""
        if self.session_focus is not None and self._current_session_id:
            focus_block = self.session_focus.get_or_create(self._current_session_id).render_block()

        return (
            static_section
            + (("\n" + focus_block) if focus_block else "")
            + "\n\n"
            + _EVENTS_HEADER
            + "\n".join(lines)
            + "\n\nNARRATION:"
        )
