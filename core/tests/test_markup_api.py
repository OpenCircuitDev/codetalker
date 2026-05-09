"""Phase 26 — markup REST endpoints."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette

from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state


# ---------------------------------------------------------------------------
# Shared fixture — isolated server state with overlay path redirected
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "claude_code_talker.catalog.DEFAULT_PROJECTS_DIR",
        tmp_path / "projects",
    )
    monkeypatch.setattr(
        "claude_code_talker.persistent_sessions.DEFAULT_SESSIONS_DIR",
        tmp_path / "persistent",
    )
    overlay_path = tmp_path / "cfg-overlay.yaml"
    monkeypatch.setattr(
        "claude_code_talker.api._TRIGGERS_OVERLAY_PATH",
        overlay_path,
    )
    state = build_server_state()
    state.catalog._entries.clear()
    routes = build_routes(state)
    return Starlette(routes=routes), state, overlay_path


@pytest.fixture
def client(app):
    application, _state, _overlay = app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_get_markup_config_returns_presets_for_default_mode(client):
    async with client as c:
        r = await c.get("/api/markup/config")
    assert r.status_code == 200
    data = r.json()
    assert "code_fence" in data
    assert data["code_fence"]["kind"] in {"skip", "describe", "read"}


@pytest.mark.asyncio
async def test_put_markup_config_accepts_valid_kind(client):
    async with client as c:
        r = await c.put("/api/markup/config", json={"code_fence": {"kind": "skip"}})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_put_markup_config_rejects_invalid_kind(client):
    async with client as c:
        r = await c.put("/api/markup/config", json={"code_fence": {"kind": "bogus"}})
    assert r.status_code == 400
