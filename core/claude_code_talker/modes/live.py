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
from claude_code_talker.event_render import (
    redact_paths, summarize_tool_input, summarize_tool_response,
)
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
You narrate a Claude Code session by voice for a user who stepped
away. Your job is to keep them oriented in the fewest words possible.

BRIEFNESS IS PRIMARY.
Default output: ONE SENTENCE, 12-18 words. Use a second sentence ONLY
when a decision-point is genuinely emerging (a new choice the user
must make, a divergence from their plan, or a milestone landing).
NEVER use a third sentence. Hard cap: 35 words.

Lead with the VERB of what just happened. Not "Claude is working on
the auth refactor" — "Refactored the auth middleware to handle the
new role check." Past tense for completed work, present continuous
only when something IS in flight and there's no news yet to report.

WARMTH IN ONE WORD.
A colleague's tone — not a logger's. Each narration should carry
ONE short word of human texture: an interjection ("Solid.", "Ouch.",
"Interesting."), an evaluation ("Clean.", "Messy.", "Risky."), or a
gut reaction ("Hmm.", "Nice.", "Tricky."). Place it at the start or
end of the sentence — never in the middle. ONE word, not a phrase.
NEVER use the same texture word twice in a row across consecutive
narrations.

Skip the warmth word when:
  - The narration is a question Claude is asking (the question
    speaks for itself).
  - The narration is a hard alert / error (urgency replaces warmth).
  - You're forced to choose between warmth and the word cap —
    briefness wins every time.

Examples:
  - "Refactored the auth middleware to handle the new role check. Clean."
  - "Hmm. Hand-resolving the conflict on the shared config file."
  - "Tests pass. Nice."
  - "Ouch — the migration touched the production constraint."

DECISION-CHECKPOINT MARKER.
When Claude commits to an ARCHITECTURALLY-SIGNIFICANT choice (a
schema decision, a service boundary, an API shape, a security
trade-off, a dependency add, a migration approach), prefix your
narration with [CHECKPOINT] followed by a single space. The daemon
strips the prefix before TTS, marks the narration log entry
specially, and may emit an audible cue. Examples of checkpoint
moments:
  - Choosing between SQL and NoSQL for a new feature
  - Picking REST vs websocket for a real-time path
  - Adding a third-party library to lock-in
  - A migration that changes the prod table schema
  - A security model decision (who can do what)
Routine edits, test runs, formatting changes, and obvious bugfixes
are NOT checkpoints — don't dilute the marker.

HEDGE WHEN UNCERTAIN.
If your live narration is summarizing INFERENCE (you're guessing at
intent from incomplete events) rather than DIRECT OBSERVATION (a file
edit landed, a test passed, a command ran), prefix your output
with [UNSURE] followed by a single space. Examples of uncertain:
  - You're inferring what Claude is "about to" do from prep-work
    tool calls that haven't committed to an action yet.
  - The assistant prose is hedging itself ("I think", "this might",
    "let me see if") and you're reflecting that.
  - The events show a result but the prior decision-point is
    ambiguous — you're not sure whether this is the OUTCOME the
    user wanted or a sidequest.
Direct observations never get [UNSURE].

MULTI-SESSION DEPENDENCY CLAUSE.
When narrating about a session that is WAITING on output from a
DIFFERENT session (e.g. this session is consuming an API that another
session is building, or rebasing onto another session's branch),
include a ONE-CLAUSE callout. Examples:
  - "Still on the rebase — waiting for the migration session to land."
  - "Caching the response from the schema session; ready to test."
  - "Skipping — the auth session needs to finish first."
The cross-session reference comes from the SESSION FOCUS background
block or the BACKGROUND CONTEXT — never invent dependencies. If you
don't see one in the context, don't mention one.

IMPACT CLAUSE.
When you state what happened, add ONE short clause about what it
MEANS for the user's active goal. Not the technical change — the
goal-relevance. Examples:
  - "Refactored the auth middleware to handle the new role check
    — your role-rollout plan is unblocked."
  - "Tests pass. Ready to ship if you say go."
  - "Migration ran clean — the new column is live in prod."
  - "Hand-resolving the conflict — slower than the earlier branches
    but no data loss risk."
The impact clause is OPTIONAL but PREFERRED. Skip it when:
  - The narration is purely status ("still on the build cycle").
  - The impact would force you over the word cap (35 live / 45 brief).
  - The active goal isn't clear from SESSION FOCUS.

WHAT TO INCLUDE (in priority order — stop as soon as one applies):
  1. A CHOICE the user must make → state it + options + your one-word
     recommendation. Two sentences max. ("Conflict on the shared
     config file. Option A keeps the safer path; B is faster but
     risks the issue from yesterday. Lean A.")
  2. A DIVERGENCE from the plan → flag it. ("Slower than the earlier
     branches — hand-resolving instead of auto-merging.")
  3. A MILESTONE landed → say it. ("Refactor done; wiring next.")
  4. A continuation update → ONLY if >1 narration has passed in
     silence AND something genuinely changed. Otherwise stay silent
     this tick. ("Still on the rebase cascade — fourth branch green.")
  5. None of the above → emit nothing. Better to skip a tick than to
     fill it with "Claude is working" filler.

THE ACTIVE-GOAL CLAUSE IS CONDITIONAL.
Only append a "...on your X goal" clause when:
  - This is the FIRST narration in a stretch of >60 seconds of silence, OR
  - A milestone genuinely advances the goal, OR
  - A divergence threatens the goal.
Skip it on routine ticks. Repeating the same goal every 12s is filler.

NEVER DO:
- Speak file paths or absolute file names. Only the file's function
  (e.g. "the auth config", "the build manifest").
- Echo BACKGROUND CONTEXT or SESSION FOCUS material as narration —
  it's frame, not content.
- Enumerate every tool call. Group small steps into one beat.
- Pad with "Claude is working on...", "still processing", "standing
  by", "(silent tick)", or "Claude is still doing X".
- Use bare continuation phrases like "Still on the same task." If
  you say "still", you must say what. If you can't say what
  meaningfully, stay silent this tick.
- Speak ISO timestamps or dates. Always relative time only.
- Speculate about Claude's future intent ("Claude is preparing to",
  "will likely"). Report what HAPPENED.
- Emit parenthetical stage directions.

VOICE: A colleague glancing at your screen for you. Terse with a beat
of warmth. Plain spoken English. Tense flows with the moment.

If TEACHER MODE directives appear below, apply them within these
constraints — they may add ONE clause of subject-matter explanation
when it would meaningfully help the user grasp what's happening,
but they DO NOT override briefness or the 35-word cap."""

# Separator before the dynamic events block. Presence of this exact string is
# used by tests to locate the boundary between static prefix and dynamic suffix.
# 2026-05-17 — relabeled to "CURRENT EVENTS — NARRATE THESE" to pair with the
# new "BACKGROUND CONTEXT" tags on focus/prose blocks. The contrast makes the
# narrate-vs-frame distinction unambiguous in the prompt.
_EVENTS_HEADER = (
    "---\nCURRENT EVENTS — NARRATE THESE (most recent last; USER lines = what "
    "the user just asked for; these events are strictly newer than your prior "
    "narration):\n"
)

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
                        # 2026-05-18 — only advance the cutoff when _narrate
                        # actually dispatched audio. Previously the cutoff
                        # advanced unconditionally, eating any tick whose
                        # LLM returned empty / errored / produced only
                        # filler content; the NEXT tick then filtered those
                        # events out of its prompt entirely, creating dead
                        # zones in live-mode where the user expected
                        # continuous narration. With this guard, silent
                        # ticks roll their events forward into the next
                        # cadence fire instead of getting lost.
                        produced = await self._narrate(
                            session_events, priority="normal", session_id=sid,
                        )
                        if produced:
                            self._last_narrate_by_session[sid] = now
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
                               mode: str = "live", confidence: str = "normal") -> None:
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
                confidence=confidence,
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
                session_id=session_id,
            ))
            self._append_narration_log(clean, voice, engine_name, "normal",
                                       session_id=session_id, mode="trigger")

    # ------------------------------------------------------------------
    # Streaming narration path (Sub-task 1.1)
    # ------------------------------------------------------------------

    async def _narrate_streaming(self, events, priority,
                                  session_id: str = "",
                                  verbosity_decision: str = "standard") -> bool:
        """Stream LLM output through AudioStreamer, emitting one AudioJob per sentence.

        ``verbosity_decision`` is pre-computed by ``_narrate`` (caller already
        ran _decide_verbosity_for_events and skipped if "skip").

        Returns True iff at least one non-empty chunk was successfully emitted
        to the audio queue. Used by ``_narrate``'s return-value contract so the
        cadence loop knows whether to advance ``_last_narrate_by_session``.
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
            return False

        # Use 2× the configured budget for streaming (full completion takes longer),
        # capped at the hard ceiling.
        stream_budget = min(budget * 2.0, _STREAMING_TIMEOUT_CEILING)

        # Track whether any chunk actually made it to the audio queue. The
        # streamer may consume the LLM output and find every chunk empty
        # (e.g. when the LLM returns only whitespace or only sanitized-away
        # content); in that case we want to report "no narration produced"
        # so the caller doesn't advance the since-last cutoff.
        emitted_any = False
        _hedge_seen = False  # Track if we've stripped [UNSURE] from first chunk

        def _emit_chunk(chunk: str) -> None:
            nonlocal emitted_any, _hedge_seen
            # Phase 26: pass cfg so markup pipeline (code fences, paths, etc.)
            # runs against each streaming chunk before TTS.
            chunk = _sanitize_chunk(chunk, self.cfg)
            chunk = chunk.strip()
            if not chunk:
                return
            # Strip [UNSURE] prefix from the first chunk only (where it appears)
            confidence = "normal"
            if not _hedge_seen:
                from claude_code_talker.narration_log import parse_hedge_prefix
                chunk, confidence = parse_hedge_prefix(chunk)
                chunk = chunk.strip()
                if confidence == "low":
                    _hedge_seen = True
            if not chunk:
                return
            self.audio_queue.submit(AudioJob(
                text=chunk,
                voice=voice,
                rate=rate,
                priority=priority,
                engine_name=engine_name,
                session_id=session_id,
                confidence=confidence,
            ))
            self._append_narration_log(chunk, voice, engine_name, priority,
                                        session_id=session_id, mode="live-stream",
                                        confidence=confidence)
            emitted_any = True

        streamer = AudioStreamer(emit=_emit_chunk)
        try:
            await asyncio.wait_for(
                streamer.consume(self.provider.stream(prompt, max_tokens=max_tokens)),
                timeout=stream_budget,
            )
        except (asyncio.TimeoutError, Exception) as e:
            # 2026-05-17 — promoted DEBUG → WARNING. Silent drops here were
            # the reason multi-day silence kept "looking like" a routing
            # bug. With WARNING the daemon log captures the failure mode
            # (LLM timeout, provider error, network blip) per-sid so the
            # next "I don't hear narrations for session X" report can be
            # diagnosed in one grep instead of a fresh debugging session.
            logging.warning(
                "CCT-LIVE: streaming narration dropped for sid=%s: %s",
                (session_id or "")[:8], e,
            )
            return emitted_any  # may be partially-emitted before exception
        return emitted_any

    # ------------------------------------------------------------------
    # Main narration entry point — dispatches to streaming or non-streaming
    # ------------------------------------------------------------------

    async def _narrate(self, events, priority, session_id: str = "") -> bool:
        """Run one narration round-trip for *session_id*.

        Returns True iff narration was actually dispatched to TTS (the prompt
        was built, the LLM produced text/chunks, and AudioJobs were submitted).
        Returns False on any of: no events, disabled session, no
        post-since-last-filter events, verbosity-skip, LLM failure, no voice,
        empty LLM output.

        2026-05-18 — return value added so the cadence loop can avoid
        updating ``_last_narrate_by_session`` on no-op narrations. Previous
        behavior unconditionally advanced the cutoff timestamp; that ate
        the events from any silent tick so the NEXT cadence fire never
        re-narrated them. Net result: dead zones in live-mode feed where
        the user expected continuous narration.
        """
        if not events:
            return False

        # Phase 13.6c: respect per-session disable toggle. Hook handlers
        # already gate event ingest, but the cadence loop can still fire
        # for events queued before the toggle. Re-check at narrate-time.
        if self.sessions is not None and session_id:
            s = self.sessions.get(session_id)
            if s is not None and not s.enabled:
                return False

        # Filter events to only those belonging to this session.
        # When session_id is empty, all events are used (backward compat).
        scoped_events = events_for_session(events, session_id)
        if not scoped_events:
            return False

        # 2026-05-18 — since-last filter moved here from _build_prompt so:
        # (a) we can early-return when no new events exist post-filter,
        #     avoiding a wasted LLM call on "(no events)" that produces
        #     meta-comment outputs like "(silent tick no new messages)"
        # (b) the caller can use the return value to keep
        #     _last_narrate_by_session unchanged when narration was a no-op
        last_narrate_ts = (
            self._last_narrate_by_session.get(session_id) if session_id else None
        )
        if last_narrate_ts is not None:
            scoped_events = [
                ev for ev in scoped_events if ev.timestamp > last_narrate_ts
            ]
            if not scoped_events:
                logging.debug(
                    "CCT-LIVE: no events newer than last narrate for sid=%s — skipping",
                    (session_id or "")[:8],
                )
                return False

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
            return False

        # Dispatch to streaming path when the provider supports it.
        # Use `is True` (strict) to avoid matching truthy mock objects in tests.
        if (
            self.provider is not None
            and getattr(self.provider, "supports_streaming", False) is True
        ):
            return await self._narrate_streaming(
                scoped_events, priority,
                session_id=session_id,
                verbosity_decision=verbosity_decision,
            )

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
            logging.warning(
                "CCT-LIVE: non-streaming narration dropped for sid=%s: %s",
                (session_id or "")[:8], e,
            )
            return False

        text = (text or "").strip()
        if not text:
            logging.warning(
                "CCT-LIVE: provider returned empty text for sid=%s",
                (session_id or "")[:8],
            )
            return False

        # Strip [UNSURE] hedge prefix from the response
        from claude_code_talker.narration_log import parse_hedge_prefix
        text, confidence = parse_hedge_prefix(text)
        text = text.strip()
        if not text:
            logging.warning(
                "CCT-LIVE: narration was only the hedge prefix for sid=%s",
                (session_id or "")[:8],
            )
            return False

        voice, rate, engine_name = self._resolve_voice_cfg(session_id)
        if not voice:
            logging.warning(
                "CCT-LIVE: narration dropped for sid=%s: no voice configured",
                (session_id or "")[:8],
            )
            return False

        self.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, priority=priority,
            engine_name=engine_name,
            session_id=session_id,
            confidence=confidence,
        ))
        self._append_narration_log(text, voice, engine_name, priority,
                                    session_id=session_id, mode="live",
                                    confidence=confidence)
        return True

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

        # 2026-05-18 — since-last filtering moved upstream to _narrate so the
        # cadence loop can early-return when no new events exist post-filter
        # (avoids "(silent tick no new messages)" meta-comment outputs and
        # avoids advancing the cutoff timestamp on empty narrations). Here
        # we only need to detect is_first_narration to pick the right
        # directive variant below.
        last_narrate_ts = (
            self._last_narrate_by_session.get(session_id) if session_id else None
        )
        is_first_narration = last_narrate_ts is None

        # --- Static prefix: system instructions + teacher directives (Sub-task 1.2) ---
        # The teacher block is appended to the system portion BEFORE the events so
        # the static prefix grows (and stays byte-identical) when teacher mode is on.
        # Events come LAST, after a fixed separator, so the dynamic tail never
        # disrupts the leading cache-eligible prefix.
        teacher_cfg = self._resolve_teacher_cfg(session_id)
        # Build the static section: system text + optional teacher block
        static_section = merge_teacher_into_prompt(LIVE_NARRATION_SYSTEM, teacher_cfg)

        # 2026-05-17 — "since-last" directive + explicit BACKGROUND framing.
        # The interpreter-style prompt needs to make this distinction crystal
        # clear: the focus block + assistant-prose block are PAST CONTEXT,
        # they were what the user already heard or what Claude was thinking
        # one or more cadence ticks ago. Without strong tagging the LLM
        # treats those blocks as fair material for the current narration
        # and re-narrates them — including stale reasoning that is no
        # longer valid by the time the cadence fires (a real failure mode
        # the user explicitly flagged).
        since_directive = ""
        if not is_first_narration and scoped_events:
            import time as _t
            secs_ago = max(0.0, _t.time() - (last_narrate_ts or 0.0))
            since_directive = (
                f"\n\nCONTINUITY DIRECTIVE: You last narrated this session "
                f"{secs_ago:.0f}s ago. The BACKGROUND sections below are PAST "
                "context — the listener has already heard about that material, "
                "and some of it may be stale by now (decisions already executed, "
                "reasoning already acted on). Use it ONLY to FRAME what's new. "
                "Cover ONLY the events listed in CURRENT EVENTS below — they are "
                "strictly newer than your prior narration. Do NOT restate, "
                "paraphrase, or even quietly recap older events. If nothing in "
                "CURRENT EVENTS is substantive, return a SHORT continuation "
                "sentence that NAMES the active task in plain terms (pulled from "
                "SESSION FOCUS) — e.g. \"Still on the rebase cascade you set "
                "up\" or \"Still working through the schema migration — running "
                "the post-migration checks now.\" Never return the bare phrase "
                "\"Still on the same task\" — always anchor it to WHAT the task "
                "is so the listener gets useful context. If you literally cannot "
                "identify the active task from the background, return an empty "
                "string instead of a naked continuation."
            )
        elif is_first_narration and scoped_events:
            # First narration of a session: no prior context to frame against;
            # explicitly tell the LLM this so it gives a fuller opener than
            # the steady-state interpreter would.
            since_directive = (
                "\n\nFIRST-NARRATION DIRECTIVE: This is the first time you are "
                "narrating this session. Give a 1-3 sentence orientation — what "
                "the user appears to be working on (from the events + recent "
                "prose) and what just happened. Subsequent narrations will be "
                "incremental updates against this opener."
            )

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
                    snippet = redact_paths((meta.get("text") or "")[:160])
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

        # Phase 13.5B: inject per-session SESSION FOCUS block (WHY/CONTEXT).
        # 2026-05-17 — wrapped in an explicit BACKGROUND CONTEXT header.
        # 2026-05-18 — also drop narrative_summary when older than 90s.
        # narrative_summary is an LLM-generated paragraph that refreshes every
        # 5 narrations OR when "dirty"; in a fast-moving session that's
        # several minutes of staleness, and the LLM treats it as authoritative
        # current state, then narrates it as if it were now. Stripping past
        # the 90s freshness window keeps the block useful for first-narration
        # opener context while preventing 5-minute-old "Session arc" lines
        # from polluting the live feed.
        focus_block = ""
        if self.session_focus is not None and session_id:
            import time as _t
            focus_obj = self.session_focus.get_or_create(session_id)
            stashed_summary = ""
            try:
                summary_age = _t.time() - float(getattr(focus_obj, "summary_last_refreshed_at", 0.0) or 0.0)
                if summary_age > 90.0 and getattr(focus_obj, "narrative_summary", ""):
                    stashed_summary = focus_obj.narrative_summary
                    focus_obj.narrative_summary = ""
            except Exception:
                pass
            raw_focus = focus_obj.render_block()
            # Restore the stashed value so the next narration sees it
            # if it has refreshed in between (or so subsequent ticks
            # render it again if the LLM hasn't refreshed it yet — the
            # block-time elision is for THIS prompt only).
            if stashed_summary:
                try:
                    focus_obj.narrative_summary = stashed_summary
                except Exception:
                    pass
            if raw_focus:
                focus_block = (
                    "\n=== BACKGROUND CONTEXT — SESSION FOCUS (already-heard "
                    "context; use to frame, NEVER narrate) ===\n"
                    f"{raw_focus}"
                )

        # Phase 13.7: inject RECENT ASSISTANT REASONING from transcript.
        # 2026-05-17 — reduced from 10 → 4 messages and explicitly tagged as
        # BACKGROUND. The 10-message window was a major source of "narrator
        # re-narrates stale assistant prose as if it were current news" —
        # the user explicitly flagged that the reasoning fed in here was
        # often stale by the time the cadence fired (e.g. Claude said "PR
        # #412 merged" in its prose, that became prior reasoning, the
        # narrator then re-announced "PR #412 has merged" four times across
        # consecutive cadence ticks). 4 messages still gives the LLM enough
        # to identify "what the user appears to be working on" without
        # creating that re-narration vector.
        prose_block = ""
        if self.catalog is not None and session_id:
            prose_lines = recent_assistant_prose(
                session_id, self.catalog,
                max_messages=4, max_chars_per_message=600,
            )
            if prose_lines:
                # 2026-05-18 — redact full paths from each prose line so the
                # LLM can't read filesystem paths from Claude's own prose
                # straight into TTS output.
                prose_lines = [redact_paths(p) for p in prose_lines]
                prose_block = (
                    "\n=== BACKGROUND CONTEXT — RECENT ASSISTANT REASONING "
                    "(already-heard; use ONLY to frame what the user is "
                    "working on, NEVER restate or recap) ===\n"
                    + "\n".join(f'- "{p}"' for p in prose_lines)
                )

        return (
            static_section
            + since_directive
            + (("\n" + focus_block) if focus_block else "")
            + (prose_block if prose_block else "")
            + "\n\n"
            + _EVENTS_HEADER
            + "\n".join(lines)
            + "\n\nNARRATION:"
        )
