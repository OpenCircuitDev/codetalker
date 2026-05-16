"""
Tests for LegacyPersistentSessionAdapter.

The adapter is what lets the existing daemon code (server.py,
api.py, audio.py, hooks.py) keep working unchanged while the
storage layer moves to SessionStore. These tests verify:

  1. Round-trip symmetry: session_to_legacy_dict → legacy_dict_to_session
     produces an equivalent Session.

  2. API compatibility: the adapter's 5 methods behave identically
     to the YAML-backed PersistentSessionStore — same return shapes,
     same edge cases.

  3. Realistic legacy YAML payloads round-trip through the adapter
     without data loss.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_talker.schemas import Session, VoiceConfig
from claude_code_talker.store import (
    LegacyPersistentSessionAdapter,
    SessionStore,
    legacy_dict_to_session,
    session_to_legacy_dict,
)


@pytest.fixture
def store(tmp_path: Path):
    s = SessionStore(tmp_path / "sessions.db")
    yield s
    s.close()


@pytest.fixture
def adapter(store):
    return LegacyPersistentSessionAdapter(store)


# ---------------------------------------------------------------------------
# Session ↔ legacy dict round-trip.
# ---------------------------------------------------------------------------


def test_roundtrip_minimal():
    """A bare session → legacy dict → session is identity."""
    s1 = Session(session_id="abc-123", display_name="Minimal")
    legacy = session_to_legacy_dict(s1)
    s2 = legacy_dict_to_session("abc-123", legacy)

    assert s2.session_id == s1.session_id
    assert s2.display_name == s1.display_name
    assert s2.active_mode == s1.active_mode
    assert s2.enabled == s1.enabled
    assert s2.audio_outputs == s1.audio_outputs


def test_roundtrip_full():
    """Every field populated → preserves through round-trip."""
    s1 = Session(
        session_id="full-test",
        display_name="Full Test",
        cwd="/tmp/x",
        workspace_group="OCDev",
        active_mode="live",
        cadence="significant_only",
        enabled=False,
        auto_mode_enabled=True,
        audio_outputs=["desktop", "phone", "glasses"],
        voice=VoiceConfig(engine="piper", model="en_US-joe-medium", rate=1.1),
        pinned=True,
        last_modified=12345.0,
    )

    legacy = session_to_legacy_dict(s1)
    s2 = legacy_dict_to_session("full-test", legacy)

    assert s2.workspace_group == s1.workspace_group
    assert s2.active_mode == "live"
    assert s2.cadence == "significant_only"
    assert s2.enabled is False
    assert s2.auto_mode_enabled is True
    assert set(s2.audio_outputs) == set(s1.audio_outputs)
    assert s2.voice.model == "en_US-joe-medium"
    assert s2.voice.rate == 1.1
    assert s2.pinned is True
    assert s2.last_modified == 12345.0


def test_legacy_dict_emits_live_overlay_structure():
    """The emitted dict has the right nesting — live_overlay carries
    active_mode/voice/cadence; top-level carries enabled/display_name."""
    s = Session(
        session_id="x",
        display_name="Test",
        active_mode="brief",
        cadence="periodic",
        workspace_group="OCDev",
    )
    legacy = session_to_legacy_dict(s)

    assert "live_overlay" in legacy
    assert legacy["live_overlay"]["active_mode"] == "brief"
    assert legacy["live_overlay"]["live"]["cadence"] == "periodic"
    assert legacy["enabled"] is True
    assert legacy["display_name"] == "Test"
    assert legacy["workspace_group"] == "OCDev"


# ---------------------------------------------------------------------------
# Adapter API behavior — drop-in for PersistentSessionStore.
# ---------------------------------------------------------------------------


def test_adapter_list_empty(adapter):
    assert adapter.list() == []


def test_adapter_save_then_get(adapter):
    adapter.save(
        "abc-123",
        {
            "display_name": "Saved",
            "enabled": True,
            "workspace_group": "OCDev",
            "live_overlay": {"active_mode": "live"},
        },
    )

    fetched = adapter.get("abc-123")
    assert fetched is not None
    assert fetched["display_name"] == "Saved"
    assert fetched["enabled"] is True
    assert fetched["workspace_group"] == "OCDev"
    assert fetched["live_overlay"]["active_mode"] == "live"


def test_adapter_get_missing_returns_none(adapter):
    assert adapter.get("nonexistent") is None


def test_adapter_exists(adapter):
    assert not adapter.exists("abc-123")
    adapter.save("abc-123", {"display_name": "Test"})
    assert adapter.exists("abc-123")


def test_adapter_list_returns_session_ids(adapter):
    adapter.save("aaa", {"display_name": "First"})
    adapter.save("bbb", {"display_name": "Second"})
    assert adapter.list() == ["aaa", "bbb"]


def test_adapter_delete(adapter):
    adapter.save("abc-123", {"display_name": "Test"})
    assert adapter.exists("abc-123")
    adapter.delete("abc-123")
    assert not adapter.exists("abc-123")


def test_adapter_delete_idempotent(adapter):
    """Deleting a missing session should not raise — matches
    PersistentSessionStore semantics."""
    adapter.delete("never-existed")
    # No exception = pass


# ---------------------------------------------------------------------------
# Realistic legacy YAML shape: full live_overlay with markup, paths, voice.
# ---------------------------------------------------------------------------


def test_adapter_preserves_realistic_yaml_shape(adapter):
    """A realistic legacy payload (matches the OCR-Web YAML on disk)
    survives save → get with all fields intact."""
    payload = {
        "live_overlay": {
            "active_mode": "brief",
            "voice": {"model": "en_US-joe-medium", "engine": "piper"},
            "paths": {"handling": "omit"},
            "code_blocks": "stub",
            "live": {"cadence": "significant_only"},
            "markup": {
                "code_fence": {"kind": "skip"},
                "tool_output": {"kind": "describe"},
                "inline_code": {"kind": "identifier_only"},
                "todo_update": {"kind": "count_only"},
            },
        },
        "attached_profile": None,
        "enabled": True,
        "display_name": "OCR-Web",
        "last_modified": 1778357833.8549354,
        "workspace_group": "OCRacing",
        "auto_mode_enabled": False,
        "audio_outputs": ["phone"],
        "cwd": "C:\\Users\\brand\\Dropbox\\OCR\\Open_Circuit\\BF-Workspace",
    }
    adapter.save("ocr-web-test", payload)

    fetched = adapter.get("ocr-web-test")
    assert fetched is not None
    # Top-level fields
    assert fetched["display_name"] == "OCR-Web"
    assert fetched["enabled"] is True
    assert fetched["workspace_group"] == "OCRacing"
    assert fetched["audio_outputs"] == ["phone"]
    assert fetched["last_modified"] == 1778357833.8549354
    # Live overlay
    assert fetched["live_overlay"]["active_mode"] == "brief"
    assert fetched["live_overlay"]["voice"]["model"] == "en_US-joe-medium"
    assert fetched["live_overlay"]["live"]["cadence"] == "significant_only"
    assert fetched["live_overlay"]["paths"]["handling"] == "omit"
    assert fetched["live_overlay"]["markup"]["code_fence"]["kind"] == "skip"
    assert fetched["live_overlay"]["markup"]["tool_output"]["kind"] == "describe"


def test_adapter_handles_partial_save(adapter):
    """Save with only display_name + enabled fills defaults sensibly."""
    adapter.save("partial", {"display_name": "Just a name", "enabled": False})

    fetched = adapter.get("partial")
    assert fetched["display_name"] == "Just a name"
    assert fetched["enabled"] is False
    # Defaults applied:
    assert fetched["live_overlay"]["active_mode"] == "brief"
