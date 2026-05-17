"""
Tests for views.build_session_view — the shared row-builder.

The wire format of both /api/sessions (webui) and /api/companion/sessions
(Pro Android) used to live in two divergent implementations. After
Phase 3, both endpoints delegate to build_session_view. Tests here
pin every projection rule so future drift becomes a failing test.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from claude_code_talker.schemas import CharacterRef, SessionView
from claude_code_talker.views import (
    _derive_workspace_group,
    _resolve_display_name,
    build_session_view,
)


def _state(**overrides):
    """Minimal MagicMock-state with sensible defaults. Tests override what they need."""
    state = SimpleNamespace()
    state.sessions = None
    state.persistent_sessions = None
    state.catalog = None
    state.characters = None
    state.audio_hub = None
    state.cfg = {}
    state.active_mode = "brief"
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


# ---------------------------------------------------------------------------
# _derive_workspace_group — pattern-based fallback when persistent lacks an explicit group.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "display_name,expected",
    [
        ("OCRacing", "OCRacing"),
        ("ocr-pipeline", "OCRacing"),
        ("ocm", "OCDev"),
        ("codetalker", "OCDev"),
        ("BlueprintForge", "BlueprintForge"),
        ("bpf-web", "BlueprintForge"),
        ("BPFRefactor", "BlueprintForge"),
        ("DigitalWish", "Clients"),
        ("wish-portal", "Clients"),
        ("unrelated", None),
        ("", None),
        (None, None),
    ],
)
def test_derive_workspace_group_patterns(display_name, expected):
    assert _derive_workspace_group(display_name) == expected


# ---------------------------------------------------------------------------
# _resolve_display_name — strict precedence chain.
# ---------------------------------------------------------------------------


def test_display_name_persistent_wins_over_catalog():
    catalog_entry = SimpleNamespace(
        custom_title="custom",
        vscode_label="vscode",
        slug="my-slug",
        title="catalog title",
        project_slug="proj",
    )
    name = _resolve_display_name(
        persistent={"display_name": "user override"},
        catalog_entry=catalog_entry,
        fallback_sid="abc123def456",
    )
    assert name == "user override"


def test_display_name_custom_title_wins_over_vscode():
    entry = SimpleNamespace(
        custom_title="my-title", vscode_label="vscode", slug="", title="", project_slug=""
    )
    assert _resolve_display_name(
        persistent=None, catalog_entry=entry, fallback_sid="x"
    ) == "my-title"


def test_display_name_falls_back_to_sid_prefix():
    name = _resolve_display_name(
        persistent=None, catalog_entry=None, fallback_sid="abc123def456789"
    )
    assert name == "abc123def456"


# ---------------------------------------------------------------------------
# build_session_view — the integration.
# ---------------------------------------------------------------------------


def test_build_view_with_no_inputs_returns_minimal_view():
    """Bare-minimum: sid only. Defaults reasonable, no crash."""
    view = build_session_view(_state(), "sid-1")
    assert isinstance(view, SessionView)
    assert view.session_id == "sid-1"
    assert view.display_name == "sid-1"
    assert view.is_live is False
    assert view.enabled is True
    assert view.is_companion_active is False
    assert view.has_persistent_settings is False


def test_build_view_live_match_marks_is_live():
    live = SimpleNamespace(
        cwd="/proj/a",
        last_hook_at=12345.0,
        is_speaking=False,
        attached_profile=None,
        attached_character=None,
        last_user_interaction_at=12346.0,
    )
    view = build_session_view(_state(), "sid-2", live_match=live)
    assert view.is_live is True
    assert view.cwd == "/proj/a"
    assert view.last_hook_at == 12345.0
    assert view.last_user_interaction_at == 12346.0


def test_build_view_with_persistent_overlay():
    persistent = {
        "display_name": "Persistent Name",
        "enabled": False,
        "auto_mode_enabled": True,
        "pinned": True,
        "workspace_group": "BlueprintForge",
        "audio_outputs": ["phone", "glasses"],
    }
    view = build_session_view(_state(), "sid-3", persistent=persistent)
    assert view.display_name == "Persistent Name"
    assert view.enabled is False
    assert view.auto_mode_enabled is True
    assert view.pinned is True
    assert view.workspace_group == "BlueprintForge"
    assert view.audio_outputs == ["phone", "glasses"]
    assert view.has_persistent_settings is True


def test_build_view_companion_active_flag():
    view = build_session_view(
        _state(),
        "sid-4",
        companion_active_sids={"sid-4"},
    )
    assert view.is_companion_active is True


def test_build_view_companion_active_false_when_not_in_set():
    view = build_session_view(
        _state(),
        "sid-other",
        companion_active_sids={"sid-4"},
    )
    assert view.is_companion_active is False


def test_build_view_audio_misaligned_when_phone_configured_no_subscribers():
    """phone in audio_outputs but no hub subscriber → audio_misaligned=True."""
    hub = SimpleNamespace(_subscribers={})  # no key for sid-5
    state = _state(audio_hub=hub)
    persistent = {"audio_outputs": ["phone"]}
    view = build_session_view(state, "sid-5", persistent=persistent)
    assert view.audio_misaligned is True


def test_build_view_audio_misaligned_false_when_desktop_only():
    """desktop sink has no subscribe handshake; never counts as misaligned."""
    state = _state()
    persistent = {"audio_outputs": ["desktop"]}
    view = build_session_view(state, "sid-6", persistent=persistent)
    assert view.audio_misaligned is False


def test_build_view_audio_misaligned_false_when_hub_has_subscriber():
    hub = SimpleNamespace(_subscribers={"sid-7": ["queue-1"]})
    state = _state(audio_hub=hub)
    persistent = {"audio_outputs": ["phone"]}
    view = build_session_view(state, "sid-7", persistent=persistent)
    assert view.audio_misaligned is False


def test_build_view_audio_outputs_filters_invalid_values():
    persistent = {"audio_outputs": ["phone", "bogus", "glasses"]}
    view = build_session_view(_state(), "sid-8", persistent=persistent)
    assert view.audio_outputs == ["phone", "glasses"]


def test_build_view_attached_character_resolved_from_id():
    """When attached_character is an ID, looks up state.characters."""
    fake_char = SimpleNamespace(
        to_dict=lambda: {
            "id": "char-aria",
            "display_name": "Aria",
            "voice_ref": "char-aria-v1",
            "persona": "warm narrator",
            "mesh_prompt_history": ["old prompt"],  # should be filtered out
        }
    )
    characters = SimpleNamespace(get=lambda cid: fake_char if cid == "char-aria" else None)
    state = _state(characters=characters)
    view = build_session_view(
        state,
        "sid-9",
        persistent={"attached_character": "char-aria"},
    )
    assert isinstance(view.attached_character, CharacterRef)
    assert view.attached_character.id == "char-aria"
    assert view.attached_character.voice_ref == "char-aria-v1"


def test_build_view_attached_character_stale_id_returns_stub():
    """Stale character ID → minimal stub rather than dropping the attachment."""
    characters = SimpleNamespace(get=lambda cid: None)
    state = _state(characters=characters)
    view = build_session_view(
        state,
        "sid-10",
        persistent={"attached_character": "deleted-char"},
    )
    assert view.attached_character is not None
    assert view.attached_character.id == "deleted-char"


def test_build_view_live_match_overrides_persistent_cwd():
    """Live cwd wins over catalog cwd."""
    live = SimpleNamespace(
        cwd="/live/cwd",
        last_hook_at=0.0,
        is_speaking=False,
        attached_profile=None,
        attached_character=None,
        last_user_interaction_at=0.0,
    )
    entry = SimpleNamespace(
        cwd="/catalog/cwd",
        last_modified=0.0,
        custom_title="",
        vscode_label="",
        slug="",
        title="",
        project_slug="proj",
        transcript_path=None,
    )
    view = build_session_view(_state(), "sid-11", live_match=live, catalog_entry=entry)
    assert view.cwd == "/live/cwd"


def test_build_view_workspace_group_explicit_wins_over_derive():
    """Explicit persistent.workspace_group beats display-name derivation."""
    persistent = {
        "display_name": "OCRacing-pipeline",  # would derive to "OCRacing"
        "workspace_group": "CustomGroup",
    }
    view = build_session_view(_state(), "sid-12", persistent=persistent)
    assert view.workspace_group == "CustomGroup"


def test_build_view_workspace_group_derives_from_display_name():
    """No explicit workspace_group → derive from display_name."""
    persistent = {"display_name": "bpf-tools"}
    view = build_session_view(_state(), "sid-13", persistent=persistent)
    assert view.workspace_group == "BlueprintForge"


def test_build_view_is_speaking_from_live_match():
    live = SimpleNamespace(
        cwd="",
        last_hook_at=0.0,
        is_speaking=True,
        attached_profile=None,
        attached_character=None,
        last_user_interaction_at=0.0,
    )
    view = build_session_view(_state(), "sid-14", live_match=live)
    assert view.is_speaking is True


def test_build_view_emits_valid_pydantic():
    """Round-trip via model_dump_json — ensures the schema validates."""
    view = build_session_view(_state(), "sid-15")
    json_payload = view.model_dump_json()
    assert "sid-15" in json_payload
    assert "session_id" in json_payload
