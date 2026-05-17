"""
Tests for audio_decisions — single source of truth for audio gates.

This module covers two essential properties of the refactor:

  1. **is_session_audible returns a NAMED reason** for every drop.
     The "skipped: no text" ambiguity is over. Every "no audio"
     report can now be traced to a single gate by reading the
     returned AudibleStatus.reason.

  2. **AudioJobRegistry preserves state_history** through every
     transition. The trace IS the source of truth for diagnostics
     — if a job is dropped, the history names the gate.
"""
from __future__ import annotations

import pytest

from claude_code_talker.audio_decisions import (
    AudioJobRegistry,
    is_session_audible,
    route_audio_publish_key,
)
from claude_code_talker.schemas import (
    AudibleStatus,
    MasterConfig,
    Session,
    VoiceConfig,
)


# ---------------------------------------------------------------------------
# is_session_audible — every drop has a named gate.
# ---------------------------------------------------------------------------


def test_audible_happy_path():
    """Healthy session + master on → audible."""
    s = Session(
        session_id="abc",
        display_name="Test",
        enabled=True,
        audio_outputs=["desktop"],
    )
    m = MasterConfig(enabled=True)
    status = is_session_audible(s, m)
    assert status.audible is True
    assert status.reason == "audible"
    assert status.blocking_gate is None


def test_audible_master_off():
    """Master switch off → master_disabled (highest priority gate)."""
    s = Session(session_id="abc", display_name="Test")
    m = MasterConfig(enabled=False)
    status = is_session_audible(s, m)
    assert status.audible is False
    assert status.reason == "master_disabled"
    assert status.blocking_gate == "master.enabled"


def test_audible_session_muted():
    """Session muted (enabled=False) → session_muted reason."""
    s = Session(session_id="abc", display_name="Test", enabled=False)
    m = MasterConfig(enabled=True)
    status = is_session_audible(s, m)
    assert status.audible is False
    assert status.reason == "session_muted"
    assert status.blocking_gate == "session.enabled"


def test_audible_no_audio_outputs():
    """No audio sinks → no_audio_outputs (lowest priority gate)."""
    s = Session(
        session_id="abc",
        display_name="Test",
        enabled=True,
        audio_outputs=[],
    )
    m = MasterConfig(enabled=True)
    status = is_session_audible(s, m)
    assert status.audible is False
    assert status.reason == "no_audio_outputs"
    assert status.blocking_gate == "session.audio_outputs"


def test_audible_master_off_overrides_session_state():
    """Master off wins even when session would otherwise also be muted."""
    s = Session(session_id="abc", display_name="Test", enabled=False)
    m = MasterConfig(enabled=False)
    status = is_session_audible(s, m)
    # master is the first gate checked — it wins.
    assert status.reason == "master_disabled"


def test_audible_no_master_treats_as_enabled():
    """For test ergonomics, master=None is treated as enabled."""
    s = Session(
        session_id="abc",
        display_name="Test",
        enabled=True,
        audio_outputs=["desktop"],
    )
    status = is_session_audible(s, master=None)
    assert status.audible is True


def test_audible_require_audio_outputs_off_skips_sink_check():
    """When the caller doesn't care about sinks, audio_outputs=[]
    is OK. Used by hook handlers that only check 'should the
    text be produced' before routing."""
    s = Session(session_id="abc", display_name="Test", audio_outputs=[])
    m = MasterConfig(enabled=True)
    status = is_session_audible(s, m, require_audio_outputs=False)
    assert status.audible is True


# ---------------------------------------------------------------------------
# route_audio_publish_key — wraps Strategy C with typed inputs.
# ---------------------------------------------------------------------------


def test_route_publishes_to_source_when_no_opted_in():
    """No session has audio_outputs ∋ phone/glasses → source-sid
    routing. The Strategy-C fall-through ensures audio plays
    even before per-session config exists."""
    s1 = Session(session_id="a", display_name="A", audio_outputs=["desktop"])
    decision = route_audio_publish_key(
        s1,
        all_sessions=[s1],
        companion_active_session_id=None,
        last_played_session_id=None,
        now=0.0,
    )
    assert decision.publish_to_session_id == "a"


def test_route_publishes_to_source_session_even_when_companion_active_set():
    """2026-05-17 — dropped the lex-first fan-in. With multiple opted-in
    sessions, EACH session's audio publishes to its OWN hub key. The phone
    subscribes to N keys via setActiveSessions() and fans them in client-
    side. The old behavior published every session's audio to a single
    `companion_active_session` hub key (set deterministically to the
    lex-first member), which meant every other "active" session's
    subscription received zero bytes — the multi-day silence pattern."""
    s1 = Session(
        session_id="a",
        display_name="A",
        workspace_group="GroupA",
        audio_outputs=["phone"],
    )
    s2 = Session(
        session_id="b",
        display_name="B",
        workspace_group="GroupB",
        audio_outputs=["phone"],
    )
    decision = route_audio_publish_key(
        s1,
        all_sessions=[s1, s2],
        companion_active_session_id="b",
        last_played_session_id=None,
        now=0.0,
    )
    assert decision.publish_to_session_id == "a"
    # With multiple sessions opted in and a workspace_group on the source,
    # the intro tag identifies the speaker so the listener knows which
    # workspace is talking.
    assert decision.intro_text == "GroupA: "


def test_route_drops_when_source_not_opted_in_and_others_are():
    """If OTHER sessions opted in but this one didn't, drop the audio
    — Strategy C honors the opt-in registry."""
    s1 = Session(
        session_id="a",
        display_name="A",
        audio_outputs=["desktop"],  # not in opted_in
    )
    s2 = Session(
        session_id="b",
        display_name="B",
        audio_outputs=["phone"],  # in opted_in
    )
    decision = route_audio_publish_key(
        s1,
        all_sessions=[s1, s2],
        companion_active_session_id=None,
        last_played_session_id=None,
        now=0.0,
    )
    assert decision.publish_to_session_id == ""  # drop


# ---------------------------------------------------------------------------
# AudioJobRegistry — state machine + audit trail.
# ---------------------------------------------------------------------------


def test_registry_create_initial_state():
    reg = AudioJobRegistry()
    job = reg.create(
        session_id="abc",
        text="hello",
        voice=VoiceConfig(model="en_US-joe-medium"),
    )
    assert job.state == "created"
    assert job.state_history == []
    assert reg.count() == 1


def test_registry_transition_appends_history():
    reg = AudioJobRegistry()
    job = reg.create("abc", "hi", VoiceConfig())
    updated = reg.transition(
        job.job_id,
        to_state="queued",
        gate="dispatch",
    )
    assert updated is not None
    assert updated.state == "queued"
    assert len(updated.state_history) == 1
    assert updated.state_history[0].from_state == "created"
    assert updated.state_history[0].to_state == "queued"
    assert updated.state_history[0].gate == "dispatch"


def test_registry_transition_records_reason_for_drops():
    """A skipped state must carry the reason — that's the whole
    point of the audit trail."""
    reg = AudioJobRegistry()
    job = reg.create("abc", "hi", VoiceConfig())
    reg.transition(job.job_id, to_state="queued", gate="dispatch")
    reg.transition(
        job.job_id,
        to_state="skipped",
        gate="audibility_check",
        reason="master_disabled",
    )
    final = reg.get(job.job_id)
    assert final is not None
    assert final.state == "skipped"
    assert final.state_history[-1].reason == "master_disabled"


def test_registry_transition_records_publish_key():
    """Publish_key is set when routing completes; survives later transitions."""
    reg = AudioJobRegistry()
    job = reg.create("abc", "hi", VoiceConfig())
    reg.transition(
        job.job_id, to_state="routing", gate="route", publish_key="other-sid"
    )
    reg.transition(
        job.job_id, to_state="synthesizing", gate="synth"
    )  # doesn't pass publish_key
    final = reg.get(job.job_id)
    assert final.publish_key == "other-sid"  # preserved


def test_registry_transition_missing_job_returns_none():
    reg = AudioJobRegistry()
    result = reg.transition(
        "nonexistent", to_state="queued", gate="dispatch"
    )
    assert result is None


def test_registry_recent_newest_first():
    reg = AudioJobRegistry()
    j1 = reg.create("a", "hi 1", VoiceConfig())
    j2 = reg.create("b", "hi 2", VoiceConfig())
    j3 = reg.create("c", "hi 3", VoiceConfig())

    recent = reg.recent(limit=10)
    assert [j.job_id for j in recent] == [j3.job_id, j2.job_id, j1.job_id]


def test_registry_recent_for_session_filters():
    reg = AudioJobRegistry()
    j1 = reg.create("a", "hi 1", VoiceConfig())
    j2 = reg.create("b", "hi 2", VoiceConfig())
    j3 = reg.create("a", "hi 3", VoiceConfig())

    for_a = reg.recent_for_session("a")
    assert [j.job_id for j in for_a] == [j3.job_id, j1.job_id]
    for_b = reg.recent_for_session("b")
    assert [j.job_id for j in for_b] == [j2.job_id]


def test_registry_ring_buffer_evicts_oldest():
    """When the ring fills, oldest jobs get evicted."""
    reg = AudioJobRegistry(max_size=3)
    j1 = reg.create("a", "1", VoiceConfig())
    j2 = reg.create("b", "2", VoiceConfig())
    j3 = reg.create("c", "3", VoiceConfig())
    j4 = reg.create("d", "4", VoiceConfig())  # evicts j1

    assert reg.count() == 3
    assert reg.get(j1.job_id) is None
    assert reg.get(j2.job_id) is not None
    assert reg.get(j4.job_id) is not None


def test_registry_full_lifecycle_trace():
    """A successful job records every transition: created → queued
    → routing → synthesizing → publishing → played."""
    reg = AudioJobRegistry()
    job = reg.create("abc", "hi", VoiceConfig())
    reg.transition(job.job_id, to_state="queued", gate="dispatch")
    reg.transition(job.job_id, to_state="routing", gate="route", publish_key="abc")
    reg.transition(job.job_id, to_state="synthesizing", gate="synth")
    reg.transition(
        job.job_id,
        to_state="publishing",
        gate="hub",
        bytes_synthesized=12345,
    )
    reg.transition(job.job_id, to_state="played", gate="hub")

    final = reg.get(job.job_id)
    assert final is not None
    assert final.state == "played"
    assert [t.to_state for t in final.state_history] == [
        "queued", "routing", "synthesizing", "publishing", "played"
    ]
    assert final.publish_key == "abc"
    assert final.bytes_synthesized == 12345
