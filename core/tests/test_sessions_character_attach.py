"""Phase 25a — session attach lifecycle + cfg merge precedence tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_talker.characters import Character, CharacterStore
from claude_code_talker.sessions import LiveSession


def test_live_session_has_attached_character_field():
    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    assert hasattr(s, "attached_character")
    assert s.attached_character is None


def test_live_session_attached_character_setter():
    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"
    assert s.attached_character == "alice"


def test_resolve_for_session_with_character_overrides_voice_and_persona(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"engine": "piper", "model": "default-voice", "rate": 1.0}, "triggers": {"persona": "warm"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")
    char_store = CharacterStore(characters_dir=tmp_path / "chars")
    char_store.save(Character(id="alice", display_name="Alice", voice_ref="alice-voice", persona="methodical"))

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"

    resolved = resolve_for_session(base, s, profile_store, char_store)
    assert resolved["voice"]["model"] == "alice-voice"
    assert resolved["triggers"]["persona"] == "methodical"
    assert resolved["voice"]["engine"] == "piper"  # base preserved
    assert resolved["voice"]["rate"] == 1.0


def test_resolve_for_session_overlay_beats_character(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"model": "default"}, "triggers": {"persona": "warm"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")
    char_store = CharacterStore(characters_dir=tmp_path / "chars")
    char_store.save(Character(id="alice", display_name="Alice", voice_ref="alice-voice", persona="methodical"))

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"
    s.live_overlay = {"voice": {"model": "override-voice"}}

    resolved = resolve_for_session(base, s, profile_store, char_store)
    assert resolved["voice"]["model"] == "override-voice"  # overlay wins
    assert resolved["triggers"]["persona"] == "methodical"  # character still wins for persona


def test_resolve_for_session_dangling_character_falls_back(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"model": "default"}, "triggers": {"persona": "warm"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")
    char_store = CharacterStore(characters_dir=tmp_path / "chars")  # empty

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "missing-char"

    # Should not raise; character missing → fall back to base
    resolved = resolve_for_session(base, s, profile_store, char_store)
    assert resolved["voice"]["model"] == "default"
    assert resolved["triggers"]["persona"] == "warm"


def test_resolve_for_session_character_store_none_is_safe(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"model": "default"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"  # set but no store

    resolved = resolve_for_session(base, s, profile_store, None)
    assert resolved["voice"]["model"] == "default"  # graceful fallback


@pytest.mark.asyncio
async def test_attach_character_endpoint_sets_field(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from claude_code_talker.server import build_server_state, build_asgi_app
    state = build_server_state()
    state.characters = CharacterStore(characters_dir=tmp_path / "chars")
    state.characters.save(Character(id="alice", display_name="Alice", voice_ref="en_GB-jenny_dioco-medium"))
    s = state.sessions.touch("test-sid", cwd="/tmp", transcript_path="")
    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/sessions/test-sid/attach-character", json={"character_id": "alice"})
        assert r.status_code == 200
        data = r.json()
        assert data["state"]["attached_character"] == "alice"
        assert state.sessions.get("test-sid").attached_character == "alice"


@pytest.mark.asyncio
async def test_attach_character_400_on_unknown_character(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from claude_code_talker.server import build_server_state, build_asgi_app
    state = build_server_state()
    state.characters = CharacterStore(characters_dir=tmp_path / "chars")
    state.sessions.touch("test-sid", cwd="/tmp", transcript_path="")
    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/sessions/test-sid/attach-character", json={"character_id": "nope"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_attach_character_404_on_unknown_session(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from claude_code_talker.server import build_server_state, build_asgi_app
    state = build_server_state()
    state.characters = CharacterStore(characters_dir=tmp_path / "chars")
    state.characters.save(Character(id="alice", display_name="A", voice_ref="v"))
    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/sessions/missing-sid/attach-character", json={"character_id": "alice"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_detach_character_clears_field(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from claude_code_talker.server import build_server_state, build_asgi_app
    state = build_server_state()
    state.characters = CharacterStore(characters_dir=tmp_path / "chars")
    state.characters.save(Character(id="alice", display_name="A", voice_ref="v"))
    s = state.sessions.touch("test-sid", cwd="/tmp", transcript_path="")
    s.attached_character = "alice"
    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete("/api/sessions/test-sid/character")
        assert r.status_code == 200
        data = r.json()
        assert data["state"]["attached_character"] is None
        assert state.sessions.get("test-sid").attached_character is None


@pytest.mark.asyncio
async def test_detach_character_idempotent(tmp_path):
    """Detaching a character that wasn't attached is OK (no error)."""
    from httpx import ASGITransport, AsyncClient
    from claude_code_talker.server import build_server_state, build_asgi_app
    state = build_server_state()
    state.characters = CharacterStore(characters_dir=tmp_path / "chars")
    state.sessions.touch("test-sid", cwd="/tmp", transcript_path="")
    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete("/api/sessions/test-sid/character")
        assert r.status_code == 200
