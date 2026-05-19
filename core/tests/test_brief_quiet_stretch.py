"""Tests for the brief-mode quiet-stretch trigger.

These cover the pure decision function (`_should_fire_for_session`) —
the surrounding asyncio loop is shaped around it, so getting the
gate right covers most of the behavior.
"""
from __future__ import annotations

from claude_code_talker.modes.brief_quiet_stretch import (
    _should_fire_for_session,
    QuietStretchFireDecision,
)


THRESHOLD = 120.0


def test_feature_disabled_when_threshold_zero():
    """threshold_seconds <= 0 disables the feature globally."""
    d = _should_fire_for_session(
        now=1000.0,
        last_brief_at=0.0,
        last_hook_at=500.0,
        session_cfg={"active_mode": "brief"},
        threshold_seconds=0.0,
    )
    assert d.fire is False
    assert d.reason == "feature_disabled"


def test_active_mode_must_be_brief():
    """Live sessions are owned by LiveMode's cadence; direct doesn't summarize."""
    d_live = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=0.0,
        last_hook_at=500.0,
        session_cfg={"active_mode": "live"},
        threshold_seconds=THRESHOLD,
    )
    assert d_live.fire is False
    assert d_live.reason == "active_mode_not_brief"

    d_direct = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=0.0,
        last_hook_at=500.0,
        session_cfg={"active_mode": "direct"},
        threshold_seconds=THRESHOLD,
    )
    assert d_direct.fire is False
    assert d_direct.reason == "active_mode_not_brief"


def test_default_active_mode_is_brief():
    """No active_mode in cfg → assume brief (matches schema default)."""
    d = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=0.0,
        last_hook_at=500.0,
        session_cfg={},
        threshold_seconds=THRESHOLD,
    )
    # Other gates may block, but active_mode is fine.
    assert d.reason != "active_mode_not_brief"


def test_no_hooks_yet():
    """A session that has registered but produced no events doesn't get a brief."""
    d = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=0.0,
        last_hook_at=0.0,
        session_cfg={"active_mode": "brief"},
        threshold_seconds=THRESHOLD,
    )
    assert d.fire is False
    assert d.reason == "no_hooks_yet"


def test_no_new_activity_since_last_brief():
    """If nothing has happened since the last brief, don't fire again — even past threshold."""
    d = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=9_000.0,        # 1000s ago
        last_hook_at=8_500.0,         # BEFORE the last brief
        session_cfg={"active_mode": "brief"},
        threshold_seconds=THRESHOLD,
    )
    assert d.fire is False
    assert d.reason == "no_new_activity"


def test_within_threshold():
    """New activity, but not enough time has passed since the last brief."""
    d = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=9_950.0,        # 50s ago
        last_hook_at=9_960.0,         # newer than last brief
        session_cfg={"active_mode": "brief"},
        threshold_seconds=THRESHOLD,
    )
    assert d.fire is False
    assert d.reason == "within_threshold"


def test_first_brief_fires_after_threshold():
    """A session with hooks but no prior brief fires once threshold elapses since session start.

    The 'first brief' case uses last_brief_at=0, so the elapsed calculation
    is `now - max(0, 0) = now`. Any `now >= threshold` passes — which is
    fine: by the time the cadence task ticks for the first time, the
    daemon has been up at least 30s (the tick interval). Once last_hook_at
    is non-zero (a real hook fired), we know there's something to brief.
    """
    d = _should_fire_for_session(
        now=200.0,                    # plenty past threshold (120s)
        last_brief_at=0.0,
        last_hook_at=150.0,
        session_cfg={"active_mode": "brief"},
        threshold_seconds=THRESHOLD,
    )
    assert d.fire is True
    assert d.reason == "fire"


def test_subsequent_brief_fires_after_threshold():
    """After the first brief, the next one fires once threshold elapses again."""
    d = _should_fire_for_session(
        now=10_000.0,
        last_brief_at=9_800.0,        # 200s ago → past threshold
        last_hook_at=9_900.0,         # new activity since last brief
        session_cfg={"active_mode": "brief"},
        threshold_seconds=THRESHOLD,
    )
    assert d.fire is True
    assert d.reason == "fire"


def test_decision_is_a_dataclass():
    """Sanity check the decision shape — used in caller pattern-matching."""
    d = QuietStretchFireDecision(fire=True, reason="fire")
    assert d.fire is True
    assert d.reason == "fire"
