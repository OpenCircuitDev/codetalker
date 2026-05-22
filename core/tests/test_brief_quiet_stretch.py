"""Tests for the brief-mode quiet-stretch trigger.

These cover the pure decision functions:
  - `_should_fire_for_session` — quiet-stretch brief trigger
  - `_should_fire_heartbeat_for_session` — heartbeat "Still here." signal

The surrounding asyncio loop is shaped around these gates, so getting
the decision logic right covers most of the behavior.
"""
from __future__ import annotations

from claude_code_talker.modes.brief_quiet_stretch import (
    _should_fire_for_session,
    _should_fire_heartbeat_for_session,
    _select_heartbeat_text,
    QuietStretchFireDecision,
    HeartbeatFireDecision,
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


# =====================================================================
# Heartbeat decision tests
# =====================================================================
# The heartbeat fires when: daemon is alive (hooks recent) BUT the
# user has been in silence (no brief) long enough to wonder if
# anything is happening. Single-word signal: "Still here."

HB_SILENCE = 30.0  # User hears silence for 30s
HB_WINDOW = 60.0   # Daemon must have hooked within 60s


def test_heartbeat_disabled_when_flag_false():
    """heartbeat_enabled=False disables the feature."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=900.0,       # 100s of silence
        last_hook_at=950.0,            # recent hooks
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=False,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d.fire is False
    assert d.reason == "heartbeat_disabled"


def test_heartbeat_requires_brief_mode():
    """Heartbeat only fires in brief mode."""
    d_live = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=900.0,
        last_hook_at=950.0,
        session_cfg={"active_mode": "live"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d_live.fire is False
    assert d_live.reason == "active_mode_not_brief"


def test_heartbeat_needs_hooks_to_fire():
    """Can't signal 'daemon alive' if no hooks have fired."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=900.0,       # silence
        last_hook_at=0.0,              # no hooks yet
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d.fire is False
    assert d.reason == "no_hooks_yet"


def test_heartbeat_stale_hooks_means_silence_is_correct():
    """If last_hook_at is stale (>window), daemon really stopped — don't heartbeat."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=900.0,       # 100s of silence
        last_hook_at=920.0,            # 80s stale (> 60s window)
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d.fire is False
    assert d.reason == "hooks_too_stale"


def test_heartbeat_needs_silence_duration():
    """If narration was recent, don't heartbeat — user just heard something."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=980.0,       # 20s ago (< 30s threshold)
        last_hook_at=990.0,            # recent hooks
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d.fire is False
    assert d.reason == "silence_below_threshold"


def test_heartbeat_fires_when_all_gates_pass():
    """Heartbeat fires when: brief mode, hooks recent, user in silence."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=960.0,       # 40s of silence (> 30s)
        last_hook_at=980.0,            # 20s stale (< 60s window) — daemon alive
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d.fire is True
    assert d.reason == "fire"


def test_heartbeat_decision_is_a_dataclass():
    """Sanity check the decision shape."""
    d = HeartbeatFireDecision(fire=True, reason="fire")
    assert d.fire is True
    assert d.reason == "fire"


def test_heartbeat_edge_case_silence_exactly_at_threshold():
    """Silence at exactly the threshold boundary should fire."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=970.0,       # exactly 30s ago
        last_hook_at=990.0,            # recent
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    assert d.fire is True
    assert d.reason == "fire"


def test_heartbeat_edge_case_hooks_exactly_at_window():
    """Hooks at exactly the window boundary (hook_age == window) should fire.

    The check is hook_age > window (strictly greater), so at the boundary
    (60.0 > 60.0 = False) the hook is NOT too stale yet.
    """
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=960.0,       # 40s silence
        last_hook_at=940.0,            # exactly 60s stale (at edge of window)
        session_cfg={"active_mode": "brief"},
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    # At the boundary, hook_age == window, so condition is hook_age > window
    # which is False. So the hook is NOT too stale, and heartbeat should fire.
    assert d.fire is True
    assert d.reason == "fire"


def test_heartbeat_default_mode_is_brief():
    """No active_mode in cfg → assume brief."""
    d = _should_fire_heartbeat_for_session(
        now=1000.0,
        last_narration_at=960.0,       # silence
        last_hook_at=980.0,            # recent
        session_cfg={},                # no active_mode
        heartbeat_enabled=True,
        silence_threshold_seconds=HB_SILENCE,
        active_window_seconds=HB_WINDOW,
    )
    # Default active_mode is brief, so other gates determine the result.
    assert d.fire is True
    assert d.reason == "fire"


# =====================================================================
# Heartbeat text escalation tests
# =====================================================================
# Tests for _select_heartbeat_text: the pure text selection logic
# that escalates based on firing count and silence duration.


def test_select_heartbeat_text_first_firing():
    """First firing (count=1): "Still here." — unchanged."""
    text = _select_heartbeat_text(firing_count=1, silence_seconds=30.0)
    assert text == "Still here."


def test_select_heartbeat_text_second_firing_under_three_minutes():
    """Second firing (count=2): "Still here. Quiet two minutes." """
    text = _select_heartbeat_text(firing_count=2, silence_seconds=60.0)
    assert text == "Still here. Quiet two minutes."


def test_select_heartbeat_text_third_firing_exactly_three_minutes():
    """Third firing (count=3): "Still on it — 3 minutes." """
    text = _select_heartbeat_text(firing_count=3, silence_seconds=180.0)
    assert text == "Still on it — 3 minutes."


def test_select_heartbeat_text_fourth_firing_five_minutes():
    """Fourth firing (count=4): "Still on it — 5 minutes." """
    text = _select_heartbeat_text(firing_count=4, silence_seconds=300.0)
    assert text == "Still on it — 5 minutes."


def test_select_heartbeat_text_caps_at_ten_plus():
    """Silence >= 10 minutes: "Still on it — 10+ minutes." """
    text = _select_heartbeat_text(firing_count=10, silence_seconds=900.0)
    assert text == "Still on it — 10+ minutes."
    # Also test with even longer silence
    text_long = _select_heartbeat_text(firing_count=15, silence_seconds=1200.0)
    assert text_long == "Still on it — 10+ minutes."


def test_select_heartbeat_text_rounds_to_nearest_minute():
    """Silence duration is rounded to nearest minute."""
    # 89.5s → rounds to 1.5 → rounds to 2 minutes
    text_90s = _select_heartbeat_text(firing_count=3, silence_seconds=90.0)
    assert text_90s == "Still on it — 2 minutes."
    # 150s (2.5 min) → rounds to 2 minutes
    text_150s = _select_heartbeat_text(firing_count=3, silence_seconds=150.0)
    assert text_150s == "Still on it — 2 minutes."
    # 180s (3 min) → 3 minutes
    text_180s = _select_heartbeat_text(firing_count=3, silence_seconds=180.0)
    assert text_180s == "Still on it — 3 minutes."


def test_select_heartbeat_text_zero_or_negative_count_treated_as_first():
    """Edge case: count <= 0 defaults to "Still here." """
    text_zero = _select_heartbeat_text(firing_count=0, silence_seconds=100.0)
    assert text_zero == "Still here."
    text_neg = _select_heartbeat_text(firing_count=-1, silence_seconds=100.0)
    assert text_neg == "Still here."
