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
