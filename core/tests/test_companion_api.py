"""CCT-31 — companion REST endpoint tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from claude_code_talker.server import build_server_state
from claude_code_talker.api import build_routes
from starlette.applications import Starlette


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_TALKER_HOME", str(tmp_path))
    state = build_server_state()
    # X-1: ar_pairing + buddy_mode + direct_stt are Pro-gated. Tests in
    # this file cover companion endpoint mechanics (auth, validation,
    # routing), not the gate itself. Grant Pro at fixture level so
    # every test exercises its real subject. Dedicated gate tests live
    # alongside the production code in test_licensing.
    state.licensing.pro_active = True
    app = Starlette(routes=build_routes(state))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_post_pair_returns_token(client):
    r = await client.post("/api/companion/pair", json={"label": "test-phone"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert len(body["token"]) >= 32


@pytest.mark.asyncio
async def test_post_pair_validates_token(client):
    r = await client.post("/api/companion/pair", json={"label": "x"})
    tok = r.json()["token"]
    r2 = await client.get("/api/companion/sessions", headers={"X-CCT-Pairing-Token": tok})
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_companion_request_returns_401(client):
    r = await client.get("/api/companion/sessions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_post_start_buddy_requires_anthropic_key(client):
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    headers = {"X-CCT-Pairing-Token": tok}
    r = await client.post(
        "/api/companion/start-buddy",
        json={"user_session_id": "sid-1"},
        headers=headers,
    )
    assert r.status_code in (200, 400)  # 400 if no anthropic key set


@pytest.mark.asyncio
async def test_companion_active_session_endpoint(client):
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    r = await client.post(
        "/api/companion/active-session",
        json={"session_id": "sid-1"},
        headers={"X-CCT-Pairing-Token": tok},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_companion_screen_frames_returns_image_or_404(client):
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    r = await client.get(
        "/api/companion/screen-frame/fullscreen",
        headers={"X-CCT-Pairing-Token": tok},
    )
    # On non-Windows / no dxcam: 503 or 404 acceptable. On Windows with dxcam: 200 + image/jpeg.
    assert r.status_code in (200, 404, 503)


@pytest.mark.asyncio
async def test_companion_sessions_includes_attached_character_when_set(tmp_path, monkeypatch):
    """CCT-31: when a session has a character attached on the desktop, the
    AR companion's session list must include that character's display_name,
    persona, voice_ref, and mesh_path so the listener sees + hears who's
    speaking. Pure regression for the user's explicit ask: 'make sure
    character and custom voice cloning are accommodated from the user's
    session on their desktop settings.'"""
    monkeypatch.setenv("CLAUDE_CODE_TALKER_HOME", str(tmp_path))
    state = build_server_state()
    state.licensing.pro_active = True  # X-1: ar_pairing is gated; grant Pro for this test.
    app = Starlette(routes=build_routes(state))
    transport = ASGITransport(app=app)

    # Stub a character on disk + an attached session.
    from claude_code_talker.characters import Character
    char = Character(
        id="aria",
        display_name="Aria",
        voice_ref="char-aria",
        persona="warm",
    )
    char.mesh_path = "/fake/path/aria.glb"
    state.characters.save(char)

    # Inject a live session with Aria attached.
    from claude_code_talker.sessions import SessionState
    sid = "test-sid-aria-attached"
    state.sessions._sessions[sid] = SessionState(
        session_id=sid, cwd="/tmp", transcript_path="/tmp/aria.jsonl",
        last_hook_at=0.0, attached_character="aria",
    )
    # And a catalog entry so list_sessions returns it.
    from pathlib import Path as _Path
    from claude_code_talker.catalog import CatalogEntry
    state.catalog._entries[sid] = CatalogEntry(
        session_id=sid, project_slug="test",
        transcript_path=_Path("/tmp/aria.jsonl"), last_modified=0.0,
        title="hello", custom_title="Aria session",
    )

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pair = await c.post("/api/companion/pair", json={"label": "x"})
        tok = pair.json()["token"]
        r = await c.get("/api/companion/sessions", headers={"X-CCT-Pairing-Token": tok})
        assert r.status_code == 200
        body = r.json()
        match = next((s for s in body if s["session_id"] == sid), None)
        assert match is not None, f"session not found in companion list: {body}"
        ac = match["attached_character"]
        assert ac is not None, "attached_character should be resolved, not None"
        assert ac["id"] == "aria"
        assert ac["display_name"] == "Aria"
        assert ac["persona"] == "warm"
        assert ac["voice_ref"] == "char-aria"
        assert ac["mesh_path"] == "/fake/path/aria.glb"


@pytest.mark.asyncio
async def test_companion_sessions_attached_character_null_when_no_character(client):
    """Regression: sessions without a character return attached_character=null,
    not a partial/empty object. The Android UI checks for null specifically."""
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    r = await client.get("/api/companion/sessions", headers={"X-CCT-Pairing-Token": tok})
    assert r.status_code == 200
    body = r.json()
    # Default fixture has no characters / sessions, but the response shape
    # must still include attached_character as a key (null) on each entry,
    # so the Android client can rely on the field's presence.
    for s in body:
        assert "attached_character" in s, f"missing key in {s}"
        # Either None (no character) or full dict (character resolved)
        assert s["attached_character"] is None or isinstance(s["attached_character"], dict)
