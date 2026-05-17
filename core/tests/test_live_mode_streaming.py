"""Tests for LiveMode streaming path (Sub-task 1.1)."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.modes.live import LiveMode
from claude_code_talker.event_buffer import EventBuffer, Event
from claude_code_talker.cadence.periodic import PeriodicCadence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(ts=0.0, ev_type="POST_TOOL", tool="Read", session_id="test-session"):
    return Event(
        timestamp=ts,
        type=ev_type,
        metadata={"tool_name": tool, "success": True},
        significance=0.3,
        session_id=session_id,
    )


def _make_mode(provider, *, voice="jenny", sessions=None, narration_log=None, budget=5.0):
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
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
        narration_log=narration_log,
        sessions=sessions,
    )


def _streaming_provider(*chunks):
    """Build a mock provider with supports_streaming=True that yields chunks."""

    async def _stream(prompt, max_tokens):
        for c in chunks:
            yield c

    provider = MagicMock()
    provider.supports_streaming = True
    provider.stream = _stream
    return provider


def _non_streaming_provider(return_text="Narrating the work."):
    provider = AsyncMock()
    provider.supports_streaming = False
    provider.complete = AsyncMock(return_value=return_text)
    return provider


# ---------------------------------------------------------------------------
# Test 1: streaming path is taken when provider supports it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_uses_streaming_when_supported():
    """audio_queue.submit is called multiple times (one per sentence chunk)."""
    # Three chunks that form two clear sentences — streamer splits at boundaries.
    # We need chunks long enough that AudioStreamer emits at least two calls.
    # "Claude is editing the config file now. It just finished reading the spec."
    chunks = [
        "Claude is editing the config file now. ",
        "It just finished reading the spec.",
    ]
    provider = _streaming_provider(*chunks)
    mode = _make_mode(provider)
    events = [_make_event()]

    await mode._narrate(events, priority="normal", session_id="test-session")

    # With two sentences, submit should be called at least twice (one per sentence).
    assert mode.audio_queue.submit.call_count >= 2


# ---------------------------------------------------------------------------
# Test 2: falls back to complete() when streaming is not supported
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_falls_back_to_complete_when_streaming_unsupported():
    """Non-streaming provider: complete() is called, submit is called exactly once."""
    provider = _non_streaming_provider("Reading the orchestrator file.")
    mode = _make_mode(provider)
    events = [_make_event()]

    await mode._narrate(events, priority="normal", session_id="test-session")

    provider.complete.assert_called_once()
    assert mode.audio_queue.submit.call_count == 1


# ---------------------------------------------------------------------------
# Test 3: per-session voice is used in streamed AudioJobs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_streaming_respects_per_session_voice():
    """AudioJobs for streaming chunks carry the session's configured voice."""
    chunks = [
        "Claude is scanning the source tree. ",
        "Several config files are being checked.",
    ]
    provider = _streaming_provider(*chunks)

    # Build a minimal SessionRegistry stub that returns a session with a distinct voice.
    session_voice = "aria"
    sessions = MagicMock()
    sessions.config_for = MagicMock(return_value={
        "voice": {"model": session_voice, "rate": 1.2, "engine": "openai"},
    })

    mode = _make_mode(provider, voice="default-voice", sessions=sessions)
    events = [_make_event(session_id="sess-123")]

    await mode._narrate(events, priority="normal", session_id="sess-123")

    assert mode.audio_queue.submit.call_count >= 1
    for call in mode.audio_queue.submit.call_args_list:
        job = call[0][0]
        assert job.voice == session_voice, f"Expected '{session_voice}', got '{job.voice}'"


# ---------------------------------------------------------------------------
# Test 4: each streamed chunk is appended to the narration log
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_streaming_logs_each_chunk_to_narration_log():
    """Each sentence chunk produces one NarrationEntry with mode='live-stream'."""
    chunks = [
        "Claude is building the streaming pipeline now. ",
        "The audio queue receives each sentence separately.",
    ]
    provider = _streaming_provider(*chunks)

    narration_log = MagicMock()
    mode = _make_mode(provider, narration_log=narration_log)
    events = [_make_event()]

    await mode._narrate(events, priority="normal", session_id="test-session")

    assert narration_log.append.call_count >= 2
    for call in narration_log.append.call_args_list:
        entry = call[0][0]
        assert entry.mode == "live-stream"


# ---------------------------------------------------------------------------
# Test 5: provider exception during streaming does not crash the cadence loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrate_streaming_handles_provider_exception_silently():
    """If provider.stream raises, _narrate returns cleanly and submit is NOT called."""

    async def _bad_stream(prompt, max_tokens):
        raise RuntimeError("OpenRouter is down")
        yield  # make it a generator (never reached)

    provider = MagicMock()
    provider.supports_streaming = True
    provider.stream = _bad_stream

    mode = _make_mode(provider)
    events = [_make_event()]

    # Should not raise.
    await mode._narrate(events, priority="normal", session_id="test-session")

    mode.audio_queue.submit.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: prompt prefix is identical across different event sequences (prefix caching)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_prefix_identical_across_event_sequences():
    """The static portion (before RECENT EVENTS:) is byte-identical for same teacher_cfg."""
    provider = _streaming_provider("hello")

    mode_a = _make_mode(provider)
    mode_b = _make_mode(provider)

    events_a = [_make_event(ts=0.0, ev_type="PRE_TOOL", tool="Bash")]
    events_b = [
        _make_event(ts=0.0, ev_type="POST_TOOL", tool="Read"),
        _make_event(ts=1.5, ev_type="PRE_TOOL", tool="Edit"),
    ]

    prompt_a = mode_a._build_prompt(events_a)
    prompt_b = mode_b._build_prompt(events_b)

    # 2026-05-17 — marker renamed to "CURRENT EVENTS" as part of the
    # interpreter-style prompt rewrite (background-vs-current distinction).
    marker = "CURRENT EVENTS"
    idx_a = prompt_a.index(marker)
    idx_b = prompt_b.index(marker)

    prefix_a = prompt_a[:idx_a]
    prefix_b = prompt_b[:idx_b]

    assert prefix_a == prefix_b, (
        "Static prefix must be byte-identical across different event lists "
        f"to enable Gemini implicit prefix caching.\n"
        f"  prefix_a length={len(prefix_a)}\n"
        f"  prefix_b length={len(prefix_b)}"
    )
