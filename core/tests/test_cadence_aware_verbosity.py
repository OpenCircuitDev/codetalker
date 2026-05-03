"""Tests for cadence-aware verbosity in LiveMode (Sub-task 2.1)."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from claude_code_talker.modes.live import LiveMode
from claude_code_talker.event_buffer import EventBuffer, Event
from claude_code_talker.cadence.periodic import PeriodicCadence


def _make_events(sigs):
    """Build a list of Events with the given significance values."""
    return [
        Event(timestamp=float(i), type="POST_TOOL", metadata={"tool_name": "Read"}, significance=s)
        for i, s in enumerate(sigs)
    ]


def _make_mode(cfg=None):
    """Build a minimal LiveMode for unit testing."""
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=60.0)
    audio_q = MagicMock()
    return LiveMode(
        provider=None,
        cadence=cadence,
        event_buffer=buf,
        audio_queue=audio_q,
        cfg=cfg or {},
    )


# ---------------------------------------------------------------------------
# 1. skip when no significance and few events
# ---------------------------------------------------------------------------

def test_skip_when_no_significance_and_few_events():
    mode = _make_mode()
    events = _make_events([0.1, 0.2])  # max_sig=0.2 < 0.3, count=2 <= 2
    assert mode._decide_verbosity_for_events(events) == "skip"


def test_skip_when_significance_below_threshold_single_event():
    mode = _make_mode()
    events = _make_events([0.05])  # max_sig=0.05, count=1
    assert mode._decide_verbosity_for_events(events) == "skip"


# ---------------------------------------------------------------------------
# 2. concise when low significance (above skip threshold)
# ---------------------------------------------------------------------------

def test_concise_when_low_significance():
    mode = _make_mode()
    # max_sig=0.4, count=3 — above skip threshold, below 0.5
    events = _make_events([0.1, 0.3, 0.4])
    assert mode._decide_verbosity_for_events(events) == "concise"


def test_concise_when_max_sig_just_below_0_5():
    mode = _make_mode()
    events = _make_events([0.49])
    assert mode._decide_verbosity_for_events(events) == "concise"


def test_concise_when_low_sig_but_more_than_two_events():
    """count=3 > 2, so skip threshold (count<=2) doesn't fire even with low sig."""
    mode = _make_mode()
    events = _make_events([0.1, 0.2, 0.2])  # max_sig=0.2, count=3 — NOT skipped
    assert mode._decide_verbosity_for_events(events) == "concise"


# ---------------------------------------------------------------------------
# 3. expanded when high significance burst
# ---------------------------------------------------------------------------

def test_expanded_when_high_significance_burst():
    mode = _make_mode()
    # max_sig=0.9 >= 0.8, count=6 >= 5
    events = _make_events([0.5, 0.6, 0.7, 0.8, 0.85, 0.9])
    assert mode._decide_verbosity_for_events(events) == "expanded"


def test_expanded_requires_both_high_sig_and_count():
    """High sig alone (count<5) falls through to standard."""
    mode = _make_mode()
    events = _make_events([0.9, 0.85, 0.8])  # count=3 < 5
    assert mode._decide_verbosity_for_events(events) == "standard"


def test_expanded_requires_both_high_sig_and_count_b():
    """High count alone (sig<0.8) falls through to standard."""
    mode = _make_mode()
    events = _make_events([0.6, 0.65, 0.7, 0.72, 0.75, 0.79])  # count=6, max_sig=0.79
    assert mode._decide_verbosity_for_events(events) == "standard"


# ---------------------------------------------------------------------------
# 4. standard when moderate
# ---------------------------------------------------------------------------

def test_standard_when_moderate():
    mode = _make_mode()
    # max_sig=0.6, count=4 — not skip, not concise, not expanded
    events = _make_events([0.5, 0.55, 0.6, 0.58])
    assert mode._decide_verbosity_for_events(events) == "standard"


def test_standard_when_sig_exactly_0_5():
    mode = _make_mode()
    events = _make_events([0.5])  # sig==0.5, not < 0.5, count=1 < 5
    assert mode._decide_verbosity_for_events(events) == "standard"


# ---------------------------------------------------------------------------
# 5. disabled returns teacher default
# ---------------------------------------------------------------------------

def test_disabled_returns_teacher_default_standard():
    cfg = {
        "live": {"cadence_aware_verbosity": False},
        "teacher_mode": {"enabled": True, "verbosity": "standard"},
    }
    mode = _make_mode(cfg=cfg)
    # Even low-significance events should return "standard", not "skip"/"concise"
    events = _make_events([0.0, 0.1])
    assert mode._decide_verbosity_for_events(events) == "standard"


def test_disabled_returns_teacher_default_expanded():
    cfg = {
        "live": {"cadence_aware_verbosity": False},
        "teacher_mode": {"enabled": True, "verbosity": "expanded"},
    }
    mode = _make_mode(cfg=cfg)
    events = _make_events([0.0])
    assert mode._decide_verbosity_for_events(events) == "expanded"


def test_disabled_returns_teacher_default_concise():
    cfg = {
        "live": {"cadence_aware_verbosity": False},
        "teacher_mode": {"enabled": True, "verbosity": "concise"},
    }
    mode = _make_mode(cfg=cfg)
    events = _make_events([0.9, 0.9, 0.9, 0.9, 0.9, 0.9])
    # Would normally be "expanded" if enabled; disabled → returns teacher's "concise"
    assert mode._decide_verbosity_for_events(events) == "concise"


def test_disabled_fallback_when_no_teacher_cfg():
    """No teacher_mode in cfg → falls back to 'standard' default."""
    cfg = {"live": {"cadence_aware_verbosity": False}}
    mode = _make_mode(cfg=cfg)
    events = _make_events([0.0])
    assert mode._decide_verbosity_for_events(events) == "standard"


# ---------------------------------------------------------------------------
# 6. skip decision prevents audio_queue.submit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_decision_prevents_audio_submit():
    """Full integration: _narrate with all-noise events must not call audio_queue.submit."""
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=60.0)
    audio_q = MagicMock()
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="some narration")
    # No `supports_streaming` → uses non-streaming path
    del provider.supports_streaming  # ensure getattr fallback to False

    cfg = {
        "live": {"llm_latency_budget_seconds": 5.0},
        "voice": {"model": "jenny", "rate": 1.0},
    }
    mode = LiveMode(
        provider=provider,
        cadence=cadence,
        event_buffer=buf,
        audio_queue=audio_q,
        cfg=cfg,
    )

    # max_sig=0.1 < 0.3, count=1 ≤ 2 → skip
    events = [Event(timestamp=0.0, type="PRE_TOOL", metadata={"tool_name": "Glob"}, significance=0.1)]
    await mode._narrate(events, priority="normal")

    audio_q.submit.assert_not_called()
    provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_skip_not_fired_for_significant_event():
    """Significant event (sig=0.7) must NOT be skipped."""
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=60.0)
    audio_q = MagicMock()
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="test is failing")
    provider.supports_streaming = False  # force non-streaming

    cfg = {
        "live": {"llm_latency_budget_seconds": 5.0},
        "voice": {"model": "jenny", "rate": 1.0},
    }
    mode = LiveMode(
        provider=provider,
        cadence=cadence,
        event_buffer=buf,
        audio_queue=audio_q,
        cfg=cfg,
    )

    # sig=0.7 → "standard", not skip
    events = [Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Bash", "success": False}, significance=0.7)]
    await mode._narrate(events, priority="alert")

    provider.complete.assert_called_once()
    audio_q.submit.assert_called_once()
