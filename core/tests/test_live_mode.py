"""Phase 13.6 Task B: session-scoped narration tests for LiveMode.

Verifies that narrations stay in their lane — events from session A never
contaminate a narration for session B, voices are per-session, and the
cadence loop fires independently per session.
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.modes.live import LiveMode, events_for_session
from claude_code_talker.event_buffer import EventBuffer, Event
from claude_code_talker.cadence.periodic import PeriodicCadence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(ts=0.0, ev_type="POST_TOOL", tool="Read",
                session_id="", significance=0.6) -> Event:
    return Event(
        timestamp=ts,
        type=ev_type,
        metadata={"tool_name": tool, "success": True},
        significance=significance,
        session_id=session_id,
    )


def _make_mode(provider, *, voice="jenny", sessions=None, session_focus=None,
               narration_log=None, budget=5.0) -> LiveMode:
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=60.0)
    cfg = {
        "live": {"llm_latency_budget_seconds": budget},
        "voice": {"model": voice, "rate": 1.0, "engine": "piper"},
    }
    return LiveMode(
        provider=provider,
        cadence=cadence,
        event_buffer=buf,
        audio_queue=MagicMock(),
        cfg=cfg,
        sessions=sessions,
        session_focus=session_focus,
        narration_log=narration_log,
    )


def _non_streaming_provider(return_text="Narrating the work."):
    provider = AsyncMock()
    provider.supports_streaming = False
    provider.complete = AsyncMock(return_value=return_text)
    return provider


# ---------------------------------------------------------------------------
# Test 1: _narrate filters events to the given session_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_filters_events_to_session_id():
    """When narrating session A, the prompt must contain ONLY session A's events.

    We embed sentinel strings in each event's tool name so we can assert
    which events made it into the prompt that was sent to the provider.
    """
    captured_prompts = []

    async def capturing_complete(prompt, max_tokens=150):
        captured_prompts.append(prompt)
        return "narrating session A"

    provider = MagicMock()
    provider.supports_streaming = False
    provider.complete = capturing_complete

    mode = _make_mode(provider)

    # 3 events for session A, 2 events for session B
    events = [
        _make_event(ts=0.0, tool="SENTINEL_A1", session_id="session-A"),
        _make_event(ts=0.1, tool="SENTINEL_A2", session_id="session-A"),
        _make_event(ts=0.2, tool="SENTINEL_B1", session_id="session-B"),
        _make_event(ts=0.3, tool="SENTINEL_A3", session_id="session-A"),
        _make_event(ts=0.4, tool="SENTINEL_B2", session_id="session-B"),
    ]

    await mode._narrate(events, priority="normal", session_id="session-A")

    assert len(captured_prompts) == 1, "Expected exactly one LLM call"
    prompt = captured_prompts[0]

    # Session A sentinels must appear
    assert "SENTINEL_A1" in prompt
    assert "SENTINEL_A2" in prompt
    assert "SENTINEL_A3" in prompt

    # Session B sentinels must NOT appear
    assert "SENTINEL_B1" not in prompt
    assert "SENTINEL_B2" not in prompt


# ---------------------------------------------------------------------------
# Test 2: _narrate uses session-specific voice cfg
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_uses_session_specific_voice_cfg():
    """When session A and B have different voices, narrating A uses A's voice."""
    session_a_voice = "aria-session-a"

    sessions = MagicMock()
    sessions.config_for = MagicMock(return_value={
        "voice": {"model": session_a_voice, "rate": 1.0, "engine": "piper"},
    })

    provider = _non_streaming_provider("narrating now")
    mode = _make_mode(provider, voice="default-global-voice", sessions=sessions)

    events = [_make_event(ts=0.0, tool="Edit", session_id="session-A")]
    await mode._narrate(events, priority="normal", session_id="session-A")

    assert mode.audio_queue.submit.call_count == 1
    job = mode.audio_queue.submit.call_args[0][0]
    assert job.voice == session_a_voice, (
        f"Expected '{session_a_voice}', got '{job.voice}'"
    )
    # Confirm sessions.config_for was called with the right session_id
    sessions.config_for.assert_called_with("session-A")


# ---------------------------------------------------------------------------
# Test 3: cadence loop fires per-session independently
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cadence_loop_fires_per_session_independently():
    """High-significance events in session A fire A's narration without
    touching session B (which has no events in this tick)."""
    narrate_calls: list[tuple] = []  # (session_id, events)

    # Patch _narrate to record calls without actually going to LLM
    async def mock_narrate(events, priority, session_id=""):
        if events:
            narrate_calls.append((session_id, list(events)))

    provider = _non_streaming_provider("narrating")
    mode = _make_mode(provider)
    mode._narrate = mock_narrate  # type: ignore[method-assign]

    # 5 high-significance events for session A only
    events_a = [
        _make_event(ts=float(i), tool="Edit", session_id="session-A", significance=0.7)
        for i in range(5)
    ]

    # Invoke the decision logic directly (avoids the asyncio.sleep in the loop)
    import time
    per_session = mode._decide_cadence_per_session(events_a, {}, time.time())

    # Dispatch the results
    for sid, session_events in per_session:
        await mock_narrate(session_events, priority="normal", session_id=sid)

    assert len(narrate_calls) == 1, (
        f"Expected exactly 1 narrate call (for session-A), got {len(narrate_calls)}"
    )
    sid_called, events_called = narrate_calls[0]
    assert sid_called == "session-A"
    assert len(events_called) == 5

    # session-B was never involved
    assert all(sid != "session-B" for sid, _ in narrate_calls)


# ---------------------------------------------------------------------------
# Test 4: events_for_session pure helper
# ---------------------------------------------------------------------------

def test_event_filtering_helper():
    """Pure helper: events_for_session(events, sid) returns only matching."""
    ev_a1 = _make_event(ts=0.0, tool="Edit", session_id="A")
    ev_a2 = _make_event(ts=0.1, tool="Write", session_id="A")
    ev_b1 = _make_event(ts=0.2, tool="Read", session_id="B")
    ev_empty = _make_event(ts=0.3, tool="Glob", session_id="")

    events = [ev_a1, ev_a2, ev_b1, ev_empty]

    result_a = events_for_session(events, "A")
    assert result_a == [ev_a1, ev_a2], f"Got {result_a}"

    result_b = events_for_session(events, "B")
    assert result_b == [ev_b1], f"Got {result_b}"

    # Empty session_id: all events returned unchanged (backward compat)
    result_all = events_for_session(events, "")
    assert result_all == events, f"Expected all events, got {result_all}"

    # Unknown session_id: empty
    result_unknown = events_for_session(events, "C")
    assert result_unknown == [], f"Expected [], got {result_unknown}"


# ---------------------------------------------------------------------------
# Test 5: no _current_session_id attribute exists on LiveMode
# ---------------------------------------------------------------------------

def test_live_mode_has_no_current_session_id_attribute():
    """Regression guard: the racy singleton field must not exist after Task B."""
    provider = _non_streaming_provider()
    mode = _make_mode(provider)
    assert not hasattr(mode, "_current_session_id"), (
        "_current_session_id still exists on LiveMode — "
        "the race condition refactor was not applied"
    )


# ---------------------------------------------------------------------------
# Test 6: _narrate respects per-session disable toggle (Phase 13.6c)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_skips_disabled_session():
    """When session.enabled=False, narrate must return immediately.

    Hook handlers gate event ingest, but the cadence loop can still fire
    for events queued before the toggle. This re-check at narrate-time
    is the second line of defense.
    """
    from claude_code_talker.sessions import SessionRegistry, SessionState

    sessions = SessionRegistry()
    sessions._sessions["sess-A"] = SessionState(session_id="sess-A", cwd="/x", enabled=False)
    sessions._sessions["sess-B"] = SessionState(session_id="sess-B", cwd="/y", enabled=True)

    provider = _non_streaming_provider()
    mode = _make_mode(provider, sessions=sessions)

    events_a = [_make_event(ts=1.0, session_id="sess-A")]
    events_b = [_make_event(ts=1.0, session_id="sess-B")]

    await mode._narrate(events_a, "normal", session_id="sess-A")
    await mode._narrate(events_b, "normal", session_id="sess-B")

    # Provider should have been called ONCE — only for the enabled session
    assert provider.complete.await_count == 1


# ---------------------------------------------------------------------------
# Test 7: _build_prompt includes RECENT ASSISTANT REASONING when catalog set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_prompt_includes_assistant_reasoning_when_catalog_set(tmp_path):
    """When LiveMode has a catalog, _build_prompt injects RECENT ASSISTANT REASONING."""
    transcript = tmp_path / "sess.jsonl"
    transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Categorizing 81 stubs into 30/17/10 buckets."},
    ]}}) + "\n", encoding="utf-8")

    class FakeEntry:
        transcript_path = transcript

    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()

    provider = _non_streaming_provider()
    mode = _make_mode(provider)
    mode.catalog = FakeCatalog()  # bypass constructor for test simplicity

    events = [_make_event(ts=1.0, session_id="sess-A")]
    prompt = mode._build_prompt(events, session_id="sess-A")
    assert "RECENT ASSISTANT REASONING" in prompt
    assert "Categorizing 81 stubs" in prompt


# ---------------------------------------------------------------------------
# Phase 13.8 R3: _sanitize_chunk unit tests
# ---------------------------------------------------------------------------

def test_sanitize_chunk_strips_code_fence():
    """Code fences ```...``` are stripped from chunks."""
    from claude_code_talker.modes.live import _sanitize_chunk
    out = _sanitize_chunk("```python\nprint('hello')\n```")
    assert "```" not in out


def test_sanitize_chunk_strips_t_plus_prefix_mid_text():
    """[T+1.5s tool→ Edit] prefixes in the middle of text are stripped."""
    from claude_code_talker.modes.live import _sanitize_chunk
    out = _sanitize_chunk("some text [T+1.5s tool→ Edit] more text")
    assert "[T+" not in out
    assert "some text" in out
    assert "more text" in out


def test_sanitize_chunk_strips_t_plus_prefix_at_start():
    """[T+0.0s] prefix at the start of a chunk is stripped."""
    from claude_code_talker.modes.live import _sanitize_chunk
    out = _sanitize_chunk("[T+0.0s] Claude is editing the file.")
    assert "[T+" not in out
    assert "Claude is editing" in out


def test_sanitize_chunk_json_bleed_returns_empty():
    """Chunks starting with { or [ that look like JSON are skipped (return empty)."""
    from claude_code_talker.modes.live import _sanitize_chunk
    assert _sanitize_chunk('{"tool": "Edit", "file": "foo.py"}') == ""
    assert _sanitize_chunk('[{"type": "result", "content": "x"}]') == ""


def test_sanitize_chunk_normal_prose_passthrough():
    """Normal prose is returned unchanged."""
    from claude_code_talker.modes.live import _sanitize_chunk
    text = "Claude is editing the auth module to fix the JWT bug."
    assert _sanitize_chunk(text) == text


# ---------------------------------------------------------------------------
# Phase 13.8 R4: verbosity defaults bump — prompt content check
# ---------------------------------------------------------------------------

def test_live_narration_system_has_appropriate_word_limit():
    """System prompt's word limit lives in the STYLE / BRIEFNESS block.

    Evolution of the cap:
      - Original verbose narrator: 30 words
      - 2026-05-18 interpreter-style rewrite: 70 words (room for decision-
        first + arc-link + agent-asks-user-special-shape rules)
      - 2026-05-21 briefness market-feedback tightening: 35 words (the
        primary persona complaint in iter1 was "too verbose, gets in the
        way of thinking" — the prompt was rewritten with BRIEFNESS IS
        PRIMARY as the first instruction block and a 35-word hard cap)
    """
    from claude_code_talker.modes.live import LIVE_NARRATION_SYSTEM
    # Current cap should be present in the prompt.
    assert "35-word" in LIVE_NARRATION_SYSTEM or "35 words" in LIVE_NARRATION_SYSTEM
    # Older caps should be gone (the briefness rewrite explicitly
    # dropped these in favor of tighter narration).
    assert "70 words" not in LIVE_NARRATION_SYSTEM
    assert "60 words" not in LIVE_NARRATION_SYSTEM
    assert "30 words" not in LIVE_NARRATION_SYSTEM


def test_build_prompt_uses_recent_messages_capped(tmp_path):
    """_build_prompt should call recent_assistant_prose with a small max_messages.

    2026-05-17 — cap lowered from 10 → 4 after the user explicitly flagged that
    the 10-message window was a major source of "narrator re-narrates stale
    assistant prose as if it were current news." With max_messages=4 we should
    see messages 8–11 (last 4 of 12), not 0..7. The interpreter-style prompt
    rewrite + BACKGROUND-tag on this block means the LLM uses these only as
    framing, never as narration material — so we need fewer of them.
    """
    import json as _json
    transcript = tmp_path / "sess.jsonl"
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": f"Message {i}"},
        ]}}
        for i in range(12)
    ]
    transcript.write_text("\n".join(_json.dumps(e) for e in entries), encoding="utf-8")

    class FakeEntry:
        transcript_path = transcript

    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()

    provider = _non_streaming_provider()
    mode = _make_mode(provider)
    mode.catalog = FakeCatalog()

    events = [_make_event(ts=1.0, session_id="sess-A")]
    prompt = mode._build_prompt(events, session_id="sess-A")
    # With max_messages=4 we should see messages 8–11 (last 4 of 12).
    assert '- "Message 11"' in prompt
    assert '- "Message 8"' in prompt
    # Older messages should be excluded.
    assert '- "Message 7"' not in prompt
    assert '- "Message 0"' not in prompt
    # And the BACKGROUND tag must be present so the LLM knows not to re-narrate.
    assert "BACKGROUND CONTEXT" in prompt
