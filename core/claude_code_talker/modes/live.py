"""Mode C: live narration."""
from __future__ import annotations

import asyncio
import logging
import re

from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.event_buffer import Event, EventBuffer
from claude_code_talker.cadence.base import CadenceStrategy
from claude_code_talker.audio import AudioJob
from claude_code_talker.audio_streamer import AudioStreamer
from claude_code_talker.markup.pipeline import transform_for_live
from claude_code_talker.teacher_mode import merge_teacher_into_prompt, max_tokens_for
from claude_code_talker.event_render import summarize_tool_input, summarize_tool_response
from claude_code_talker.transcript import recent_assistant_prose, strip_urls
from claude_code_talker.triggers.parser import parse_blocks
from claude_code_talker.triggers.tags import TagLibrary


# ---------------------------------------------------------------------------
# Phase 13.8 R3: chunk sanitizer — strip artefacts before TTS
# ---------------------------------------------------------------------------

# Matches markdown code fences: ```optional_lang\n...\n```
_CODE_FENCE = re.compile(r"```[^\n]*\n?.*?```", re.DOTALL)

# Matches event-format prefixes: [T+0.0s], [T+1.5s tool→ Edit foo.py], etc.
# These bleed in when the LLM echoes the events block back in its output.
_T_PREFIX = re.compile(r"\[T\+[\d.]+s[^\]]*\]")


def _sanitize_chunk(chunk: str, cfg: dict | None = None) -> str:
    """Strip TTS-hostile artefacts from a raw LLM output chunk.

    Applied rules (in order):
    1. JSON bleed — chunk starts with ``{`` or ``[`` and contains ``":`` or
       ``,"``) → treat as structured data, return empty string.
    2. ``[T+Xs ...]`` event prefixes → removed (live-mode-specific artefact
       not part of normal markdown markup).
    3. Phase 26: structure-aware markup pipeline (code fences, file paths,
       inline code, long numerals, system reminders, etc.).

    Normal prose passes through unchanged. *cfg* is the active session cfg —
    when ``None``, the default direct preset applies, mirroring the legacy
    behavior of stripping code fences wholesale.
    """
    # Rule 1 first (cheapest guard): JSON bleed detection.
    stripped = chunk.strip()
    if stripped and stripped[0] in ("{", "["):
        if '":' in stripped or ',"' in stripped:
            return ""

    # Rule 2: [T+Xs ...] event prefixes — live-mode artefact, not markdown
    chunk = _T_PREFIX.sub("", chunk)

    # Rule 3: structure-aware markup transform
    if cfg is None:
        # Preserve legacy "strip code fences" behavior when no cfg threaded
        chunk = _CODE_FENCE.sub("", chunk)
    else:
        chunk = transform_for_live(chunk, cfg)

    return chunk


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
- Up to 2-3 sentences (max 60 words) of spoken English. Present or past tense.
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


def events_for_session(events: list[Event], session_id: str) -> list[Event]:
    """Pure helper: return only the events that belong to *session_id*.

    When *session_id* is empty, all events are returned unchanged so that
    callers that don't have session context still work.
    """
    if not session_id:
        return list(events)
    return [e for e in events if e.session_id == session_id]


class LiveMode(ModeStrategy):
    name = "live"

    def __init__(self, provider, cadence: CadenceStrategy, event_buffer: EventBuffer, audio_queue, cfg: dict, narration_log=None, sessions=None, session_focus=None, *, catalog=None):
        self.provider = provider
        self.cadence = cadence
        self.event_buffer = event_buffer
        self.audio_queue = audio_queue
        self.cfg = cfg
        self.narration_log = narration_log  # Phase 11: optional NarrationLog
        self.sessions = sessions  # Phase 8.6: SessionRegistry for per-session voice
        self.session_focus = session_focus  # Phase 13.5B: per-session WHY/CONTEXT block
        self.catalog = catalog  # Phase 13.7: SessionCatalog for assistant prose injection
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Per-session last-narration timestamps for the cadence loop.
        # dict[session_id, float] — avoids a singleton race on a mutable field.
        self._last_narrate_by_session: dict[str, float] = {}

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
        # session_id is now carried by the event itself (Task A)
        decision = self.cadence.on_event(event)
        if decision.fire_immediately and self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._narrate(decision.events, priority="alert",
                               session_id=event.session_id),
                self._loop,
            )

    # ------------------------------------------------------------------
    # Per-tick cadence decision — extracted for unit-testability
    # ------------------------------------------------------------------

    def _decide_cadence_per_session(
        self,
        events: list[Event],
        last_narrate_by_session: dict[str, float],
        import_time: float,
    ) -> list[tuple[str, list[Event]]]:
        """Pure-ish per-tick logic: return (session_id, events_to_narrate) pairs.

        *import_time* is the current wall time passed in by the caller (avoids
        time.time() inside the function so tests can control it).

        A session fires when:
        - it has events in *events* (already filtered to recent tick window
          by the cadence strategy), AND
        - the verbosity check on its slice is not "skip".

        The caller is responsible for dispatching the returned pairs.
        """
        # Group events by session_id.  Events with empty session_id are grouped
        # under "" and processed as a single unnamed session for backward compat.
        by_session: dict[str, list[Event]] = {}
        for ev in events:
            sid = ev.session_id or ""
            by_session.setdefault(sid, []).append(ev)

        result = []
        for sid, session_events in by_session.items():
            # Verbosity check: skip low-significance batches.
            verbosity = self._decide_verbosity_for_events(session_events)
            if verbosity == "skip":
                continue
            result.append((sid, session_events))

        return result

    async def _cadence_loop(self) -> None:
        import time as _time
        while True:
            try:
                await asyncio.sleep(0.5)
                decision = self.cadence.tick()
                if decision.fire_periodic:
                    now = _time.time()
                    per_session = self._decide_cadence_per_session(
                        decision.events, self._last_narrate_by_session, now
                    )
                    for sid, session_events in per_session:
                        self._last_narrate_by_session[sid] = now
                        await self._narrate(session_events, priority="normal",
                                            session_id=sid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning("live cadence loop: %s", e)

    # ------------------------------------------------------------------
    # Shared helpers: resolve per-session voice/token config
    # ------------------------------------------------------------------

    def _resolve_teacher_cfg(self, session_id: str = ""):
        """Return the teacher_mode cfg dict for *session_id* (or global)."""
        teacher_cfg = self.cfg.get("teacher_mode")
        if self.sessions is not None and session_id:
            try:
                session_cfg = self.sessions.config_for(session_id)
                teacher_cfg = session_cfg.get("teacher_mode") or teacher_cfg
            except Exception:
                pass
        return teacher_cfg

    def _resolve_voice_cfg(self, session_id: str = ""):
        """Return (voice, rate, engine_name) for *session_id*."""
        session_cfg = self.cfg
        if self.sessions is not None and session_id:
            try:
                session_cfg = self.sessions.config_for(session_id)
            except Exception:
                session_cfg = self.cfg
        voice_cfg = session_cfg.get("voice") or {}
        voice = voice_cfg.get("model")
        rate = float(voice_cfg.get("rate", 1.0))
        engine_name = voice_cfg.get("engine") or "piper"
        return voice, rate, engine_name

    def _append_narration_log(self, text: str, voice: str, engine_name: str,
                               priority: str, session_id: str = "",
                               mode: str = "live") -> None:
        """Best-effort append to the narration audit log."""
        if self.narration_log is None:
            return
        try:
            from claude_code_talker.narration_log import NarrationEntry
            self.narration_log.append(NarrationEntry(
                timestamp=__import__("time").time(),
                session_id=session_id,
                text=text,
                voice=voice or "",
                engine=engine_name or "",
                mode=mode,
                priority=priority,
            ))
        except Exception as _e:
            logging.debug("narration log append failed: %s", _e)

    # ------------------------------------------------------------------
    # Phase 14.5: trigger-mode handler — parse Audible * blocks, speak verbatim
    # ------------------------------------------------------------------

    def _trigger_handler(self, session_id: str, prose: str) -> None:
        """Parse Audible * blocks from incoming prose and queue them to TTS verbatim.

        Returns early when live.mode == 'llm' (legacy LLM-narration-only path).
        In 'trigger' or 'both' modes, each enabled Audible block found in *prose*
        is stripped of URLs and submitted as an AudioJob at normal priority.

        Phase 26: each block's body is also run through ``transform_for_live`` so
        per-form markup treatments (and any per-tag ``markup_overrides``) apply
        before the chunk reaches TTS.
        """
        mode = (self.cfg.get("live") or {}).get("mode", "llm")
        if mode == "llm":
            return
        tags_section = (self.cfg.get("triggers") or {}).get("tags") or {}
        lib = TagLibrary.from_cfg(tags_section)
        enabled = lib.enabled_ids()
        if not enabled:
            return
        blocks = parse_blocks(prose, enabled)
        if not blocks:
            return
        voice, rate, engine_name = self._resolve_voice_cfg(session_id)
        if not voice:
            return
        for b in blocks:
            clean = strip_urls(b.content)
            if not clean:
                continue
            # Phase 26: per-tag markup_overrides may reshape the block's body
            # (e.g. an audible_plan_entry tag forcing plan_block→read).
            tag = lib.get(b.tag_id) if getattr(b, "tag_id", None) else None
            tag_overrides = getattr(tag, "markup_overrides", None) if tag else None
            clean = transform_for_live(clean, self.cfg, tag_overrides) or clean
            if not clean.strip():
                continue
            self.audio_queue.submit(AudioJob(
                text=clean,
                voice=voice,
                rate=rate,
                engine_name=engine_name,
                priority="normal",
            ))
            self._append_narration_log(clean, voice, engine_name, "normal",
                                       session_id=session_id, mode="trigger")

    # ------------------------------------------------------------------
    # Streaming narration path (Sub-task 1.1)
    # ------------------------------------------------------------------

    async def _narrate_streaming(self, events, priority,
                                  session_id: str = "",
                                  verbosity_decision: str = "standard") -> None:
        """Stream LLM output through AudioStreamer, emitting one AudioJob per sentence.

        ``verbosity_decision`` is pre-computed by ``_narrate`` (caller already
        ran _decide_verbosity_for_events and skipped if "skip").
        """
        prompt = self._build_prompt(events, session_id=session_id)
        budget = float((self.cfg.get("live") or {}).get("llm_latency_budget_seconds", 8.0))
        teacher_cfg = self._resolve_teacher_cfg(session_id)
        # Override verbosity with cadence-aware decision (don't mutate original)
        if verbosity_decision in ("concise", "standard", "expanded"):
            teacher_cfg = dict(teacher_cfg) if teacher_cfg else {}
            teacher_cfg["verbosity"] = verbosity_decision
        max_tokens = max_tokens_for(teacher_cfg, default=150)
        voice, rate, engine_name = self._resolve_voice_cfg(session_id)

        if not voice:
            logging.debug("live narration skipped: no voice configured")
            return

        # Use 2× the configured budget for streaming (full completion takes longer),
        # capped at the hard ceiling.
        stream_budget = min(budget * 2.0, _STREAMING_TIMEOUT_CEILING)

        def _emit_chunk(chunk: str) -> None:
            # Phase 26: pass cfg so markup pipeline (code fences, paths, etc.)
            # runs against each streaming chunk before TTS.
            chunk = _sanitize_chunk(chunk, self.cfg)
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
            self._append_narration_log(chunk, voice, engine_name, priority,
                                        session_id=session_id, mode="live-stream")

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

    async def _narrate(self, events, priority, session_id: str = ""):
        if not events:
            return

        # Phase 13.6c: respect per-session disable toggle. Hook handlers
        # already gate event ingest, but the cadence loop can still fire
        # for events queued before the toggle. Re-check at narrate-time.
        if self.sessions is not None and session_id:
            s = self.sessions.get(session_id)
            if s is not None and not s.enabled:
                return

        # Filter events to only those belonging to this session.
        # When session_id is empty, all events are used (backward compat).
        scoped_events = events_for_session(events, session_id)
        if not scoped_events:
            return

        # Phase 13.5B: update session focus counter + trigger background header refresh
        if self.session_focus is not None and session_id:
            focus = self.session_focus.get_or_create(session_id)
            focus.narrations_since_refresh += 1
            if focus.should_refresh_header():
                # Fire-and-forget: refresh runs in background, never blocks this narration
                asyncio.create_task(focus.refresh_header(self.provider))
            # Phase 13.9c Task 8: narrative summary refresh (every 5 narrations or dirty)
            focus.summary_narrations_since += 1
            if focus.summary_narrations_since >= 5 or focus.dirty:
                # Gather recent prose from transcript watcher if available
                _recent_prose: list[str] = []
                _tw = getattr(self, "_transcript_watcher", None)
                if _tw is not None:
                    _recent_prose = _tw.get_cached_prose(session_id)
                asyncio.create_task(
                    focus.refresh_narrative_summary(self.provider, recent_prose=_recent_prose)
                )
            # Phase 13.9c Task 8: clear audible_summary_line after it is consumed
            # (captured into the prompt by render_block; clear so it isn't re-spoken)
            focus.audible_summary_line = ""

        # Sub-task 2.1: cadence-aware verbosity check (applied before provider dispatch)
        verbosity_decision = self._decide_verbosity_for_events(scoped_events)
        if verbosity_decision == "skip":
            logging.debug("live narration skipped: no significant events")
            return

        # Dispatch to streaming path when the provider supports it.
        # Use `is True` (strict) to avoid matching truthy mock objects in tests.
        if (
            self.provider is not None
            and getattr(self.provider, "supports_streaming", False) is True
        ):
            await self._narrate_streaming(scoped_events, priority,
                                           session_id=session_id,
                                           verbosity_decision=verbosity_decision)
            return

        # ---- Non-streaming (original) path ----
        prompt = self._build_prompt(scoped_events, session_id=session_id)
        budget = float((self.cfg.get("live") or {}).get("llm_latency_budget_seconds", 8.0))
        teacher_cfg = self._resolve_teacher_cfg(session_id)
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

        voice, rate, engine_name = self._resolve_voice_cfg(session_id)
        if not voice:
            logging.debug("live narration skipped: no voice configured")
            return

        self.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, priority=priority,
            engine_name=engine_name,
        ))
        self._append_narration_log(text, voice, engine_name, priority,
                                    session_id=session_id, mode="live")

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

    def _build_prompt(self, events, session_id: str = "") -> str:
        # Filter to session-scoped events before rendering.
        scoped_events = events_for_session(events, session_id)

        # --- Static prefix: system instructions + teacher directives (Sub-task 1.2) ---
        # The teacher block is appended to the system portion BEFORE the events so
        # the static prefix grows (and stays byte-identical) when teacher mode is on.
        # Events come LAST, after a fixed separator, so the dynamic tail never
        # disrupts the leading cache-eligible prefix.
        teacher_cfg = self._resolve_teacher_cfg(session_id)
        # Build the static section: system text + optional teacher block
        static_section = merge_teacher_into_prompt(LIVE_NARRATION_SYSTEM, teacher_cfg)

        # --- Dynamic suffix: events list ---
        lines = []
        if not scoped_events:
            lines.append("(no events)")
        else:
            t0 = scoped_events[0].timestamp
            for ev in scoped_events[-30:]:
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
        if self.session_focus is not None and session_id:
            focus_block = self.session_focus.get_or_create(session_id).render_block()

        # Phase 13.7: inject RECENT ASSISTANT REASONING from transcript
        prose_block = ""
        if self.catalog is not None and session_id:
            prose_lines = recent_assistant_prose(session_id, self.catalog,
                                                 max_messages=10, max_chars_per_message=1500)
            if prose_lines:
                prose_block = "\nRECENT ASSISTANT REASONING (most recent last):\n" + \
                              "\n".join(f'- "{p}"' for p in prose_lines)

        return (
            static_section
            + (("\n" + focus_block) if focus_block else "")
            + (prose_block if prose_block else "")
            + "\n\n"
            + _EVENTS_HEADER
            + "\n".join(lines)
            + "\n\nNARRATION:"
        )
