"""
Tests for the codetalker domain schemas (claude_code_talker.schemas).

These tests lock down the contract that the daemon, webui, and Pro
Android app share. Any change to a schema that breaks these tests
must be a conscious decision (with corresponding client regeneration
in phase 5).

The tests are organized around three properties we want to hold
forever:

  1. **Round-trip stability** — serialize to JSON and deserialize;
     the result must equal the original. If this breaks, clients
     can't reliably reconstruct daemon responses.

  2. **Strict validation** — unknown fields are rejected (extra:
     forbid). Invalid enum values are rejected. This is how we
     prevent silent schema drift across the three languages.

  3. **Defaults are sensible** — a Session created with only its
     required fields has reasonable values for everything else.
     This is what the SessionStore returns on first touch.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from claude_code_talker.schemas import (
    AudibleStatus,
    AudioJob,
    AudioJobStateChanged,
    BriefsConfig,
    CharacterPoseChanged,
    CharacterRef,
    LifecycleChanged,
    MasterConfig,
    MasterConfigChanged,
    MasterConfigPatch,
    Session,
    SessionChanged,
    SessionPatch,
    StateTransition,
    SubscriptionChanged,
    VoiceConfig,
)


# ---------------------------------------------------------------------------
# Round-trip — every schema must survive JSON serialization unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_class,kwargs",
    [
        (VoiceConfig, {"engine": "piper", "model": "en_US-joe-medium", "rate": 1.0}),
        (VoiceConfig, {}),  # all defaults
        (BriefsConfig, {}),
        (BriefsConfig, {"user_prompt_enabled": False, "always_brief_on_stop": False}),
        (MasterConfig, {}),
        (MasterConfig, {"enabled": False, "preset": "brief"}),
        (CharacterRef, {"id": "aria", "display_name": "Aria", "voice_ref": "en_US-amy-medium"}),
        (Session, {"session_id": "abc-123", "display_name": "Test"}),
        (Session, {
            "session_id": "abc-123",
            "display_name": "Test",
            "active_mode": "live",
            "enabled": False,
            "audio_outputs": ["desktop", "phone", "glasses"],
        }),
    ],
)
def test_roundtrip(model_class, kwargs):
    """Serialize → deserialize → must equal original."""
    instance = model_class(**kwargs)
    json_str = instance.model_dump_json()
    rebuilt = model_class.model_validate_json(json_str)
    assert rebuilt.model_dump() == instance.model_dump()


# ---------------------------------------------------------------------------
# Strict validation — extra fields and invalid enum values are rejected.
# ---------------------------------------------------------------------------


def test_session_rejects_extra_fields():
    """Unknown fields must raise. This is the contract that prevents
    schema drift — typos in PATCH requests fail at the API boundary
    instead of silently being stored and ignored."""
    with pytest.raises(ValidationError):
        Session(session_id="x", display_name="y", surprise_field="oops")


def test_session_rejects_invalid_speaking_mode():
    """Only live/brief/direct are valid. trigger/teacher are
    intentionally NOT in the schema — adding them later requires a
    conscious decision."""
    with pytest.raises(ValidationError):
        Session(session_id="x", display_name="y", active_mode="trigger")  # type: ignore


def test_session_rejects_invalid_audio_output():
    """Only desktop/phone/glasses are valid sinks."""
    with pytest.raises(ValidationError):
        Session(
            session_id="x",
            display_name="y",
            audio_outputs=["headphones"],  # type: ignore
        )


def test_session_rejects_invalid_lifecycle():
    """SessionLifecycle is exactly 4 states. Anything else fails."""
    with pytest.raises(ValidationError):
        Session(session_id="x", display_name="y", lifecycle="ACTIVE")  # type: ignore


def test_voice_config_rejects_invalid_rate():
    """Rate is clamped to [0.5, 2.0]. Outside the range is unintelligible."""
    with pytest.raises(ValidationError):
        VoiceConfig(rate=3.0)
    with pytest.raises(ValidationError):
        VoiceConfig(rate=0.1)


def test_session_patch_rejects_extra_fields():
    """PATCH endpoints validate the same way — unknown fields fail."""
    with pytest.raises(ValidationError):
        SessionPatch(enabled=False, typo_field=True)  # type: ignore


def test_master_config_patch_partial_update():
    """A patch with only some fields parses; omitted fields are None."""
    patch = MasterConfigPatch(enabled=False)
    dumped = patch.model_dump(exclude_none=True)
    assert dumped == {"enabled": False}


# ---------------------------------------------------------------------------
# Defaults — a newly-touched session has reasonable values.
# ---------------------------------------------------------------------------


def test_session_defaults_are_safe():
    """A bare session (only required fields) is in a sensible state."""
    s = Session(session_id="abc-123", display_name="Untitled")
    assert s.active_mode == "brief"           # safest default — short, less verbose
    assert s.enabled is True                   # don't ship muted-by-default
    assert s.auto_mode_enabled is False        # explicit opt-in
    assert s.audio_outputs == ["desktop"]      # safest default — local play only
    assert s.lifecycle == "DORMANT"            # not active until a hook fires
    assert s.pinned is False
    assert s.attached_character is None
    assert s.attached_profile is None


def test_master_config_defaults_are_safe():
    """A bare master config has narration ON (not OFF like the 5-day
    outage cfg). preset = monitor matches production."""
    m = MasterConfig()
    assert m.enabled is True
    assert m.preset == "monitor"
    assert m.briefs.user_prompt_enabled is True
    assert "desktop" in m.audio_outputs_default


# ---------------------------------------------------------------------------
# Events — discriminator-based union; each subclass parses to itself.
# ---------------------------------------------------------------------------


def test_session_changed_event():
    ev = SessionChanged(at=1.0, session_id="abc", changed_fields={"enabled": False})
    json_str = ev.model_dump_json()
    rebuilt = SessionChanged.model_validate_json(json_str)
    assert rebuilt.event_type == "SessionChanged"
    assert rebuilt.changed_fields == {"enabled": False}


def test_lifecycle_changed_event():
    ev = LifecycleChanged(
        at=2.0, session_id="abc", from_state="IDLE", to_state="LISTENING"
    )
    assert ev.event_type == "LifecycleChanged"


def test_audio_job_state_changed_event():
    ev = AudioJobStateChanged(
        at=3.0,
        job_id="job-1",
        session_id="abc",
        from_state="synthesizing",
        to_state="played",
        gate="audio_worker",
        reason=None,
    )
    assert ev.event_type == "AudioJobStateChanged"
    assert ev.gate == "audio_worker"


def test_master_config_changed_event():
    ev = MasterConfigChanged(at=4.0, changed_fields={"enabled": True})
    assert ev.event_type == "MasterConfigChanged"


def test_subscription_changed_event():
    ev = SubscriptionChanged(
        at=5.0, session_id="abc", subscriber_count=2, delta=1, device_type="phone"
    )
    assert ev.event_type == "SubscriptionChanged"
    assert ev.delta == 1


def test_character_pose_changed_event():
    """AR/XR-relevant event. Defined now, consumed by glasses HUD
    in phase 7. Schema-ready means phase 7 is a client-side change
    only."""
    ev = CharacterPoseChanged(
        at=6.0, session_id="abc", character_id="aria", pose="listening"
    )
    assert ev.event_type == "CharacterPoseChanged"
    assert ev.pose == "listening"


# ---------------------------------------------------------------------------
# AudioJob — the audit trail primitive.
# ---------------------------------------------------------------------------


def test_audio_job_creates_with_empty_history():
    """Newly-created job starts in 'created' state with no transitions."""
    job = AudioJob(
        job_id="job-1",
        session_id="abc",
        text="Hello world",
        voice=VoiceConfig(),
        created_at=0.0,
    )
    assert job.state == "created"
    assert job.state_history == []


def test_audio_job_state_history_records_transitions():
    """The trace IS the state_history list. We can append and the
    list ordering is the trace."""
    job = AudioJob(
        job_id="job-1",
        session_id="abc",
        text="Hello world",
        voice=VoiceConfig(),
        created_at=0.0,
        state="skipped",
        state_history=[
            StateTransition(
                from_state="created", to_state="queued", at=1.0, gate="dispatch"
            ),
            StateTransition(
                from_state="queued",
                to_state="skipped",
                at=2.0,
                gate="master_check",
                reason="master_disabled",
            ),
        ],
    )
    assert len(job.state_history) == 2
    assert job.state_history[-1].reason == "master_disabled"


def test_audible_status_carries_reason():
    """The single decision function returns this. The reason value
    replaces today's ambiguous 'skipped: no text' string."""
    s = AudibleStatus(audible=False, reason="master_disabled", blocking_gate="master_check")
    assert s.audible is False
    assert s.reason == "master_disabled"


def test_audible_status_audible_case():
    """Healthy case — audible=True with reason='audible'."""
    s = AudibleStatus(audible=True, reason="audible")
    assert s.blocking_gate is None
