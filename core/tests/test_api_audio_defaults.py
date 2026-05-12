"""Tests for the v0.1.0 unification audio-defaults endpoint pair.

Covers GET + PUT /api/cfg/audio-defaults — the third "obvious toggle"
called out in the unification spec (per-session destination > Pro app
shortcut > webui Preferences default), backed by the existing fleet
flag `companion_suppress_desktop` in cfg-overlay.yaml.

The endpoint exists so the webui's Preferences panel can flip the fleet
default without requiring the user to hand-edit cfg-overlay.yaml.
"""
from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette

from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Redirect cfg-overlay.yaml so we don't write to the user's real file.
    overlay_path = tmp_path / "cfg-overlay.yaml"
    monkeypatch.setattr(
        "claude_code_talker.api._TRIGGERS_OVERLAY_PATH",
        overlay_path,
    )
    monkeypatch.setattr(
        "claude_code_talker.catalog.DEFAULT_PROJECTS_DIR",
        tmp_path / "projects",
    )
    monkeypatch.setattr(
        "claude_code_talker.persistent_sessions.DEFAULT_SESSIONS_DIR",
        tmp_path / "persistent",
    )

    state = build_server_state()
    state.catalog._entries.clear()
    routes = build_routes(state)
    return Starlette(routes=routes), state, overlay_path


@pytest.fixture
def client(app):
    application, _state, _overlay_path = app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_get_returns_default_when_unset(client):
    """Default install: companion_suppress_desktop absent from cfg →
    GET reports False + all three sinks as default outputs."""
    async with client as c:
        r = await c.get("/api/cfg/audio-defaults")
    assert r.status_code == 200
    body = r.json()
    assert body["companion_suppress_desktop"] is False
    assert body["default_outputs"] == ["desktop", "phone", "glasses"]


@pytest.mark.asyncio
async def test_put_true_then_get_reflects_phone_glasses_only(app):
    """PUT true → GET shows only phone+glasses in default_outputs.
    Mirrors the audio worker's _resolve_audio_outputs fallback semantics."""
    application, _state, _overlay_path = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r1 = await c.put(
            "/api/cfg/audio-defaults",
            json={"companion_suppress_desktop": True},
        )
        assert r1.status_code == 200
        assert r1.json()["companion_suppress_desktop"] is True

        r2 = await c.get("/api/cfg/audio-defaults")
        assert r2.status_code == 200
        body = r2.json()
        assert body["companion_suppress_desktop"] is True
        assert body["default_outputs"] == ["phone", "glasses"]


@pytest.mark.asyncio
async def test_put_persists_to_overlay_file(app):
    """PUT writes through to the cfg-overlay.yaml so the change survives
    daemon restart (the whole point of the endpoint)."""
    application, _state, overlay_path = app
    import yaml as _yaml

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put(
            "/api/cfg/audio-defaults",
            json={"companion_suppress_desktop": True},
        )
        assert r.status_code == 200

    assert overlay_path.exists()
    saved = _yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
    assert saved.get("companion_suppress_desktop") is True


@pytest.mark.asyncio
async def test_put_updates_in_memory_cfg(app):
    """The mutation also lands in state.cfg so the audio worker's
    _resolve_audio_outputs picks it up immediately, no restart needed."""
    application, state, _overlay_path = app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        await c.put(
            "/api/cfg/audio-defaults",
            json={"companion_suppress_desktop": True},
        )

    assert state.cfg.get("companion_suppress_desktop") is True


@pytest.mark.asyncio
async def test_put_missing_body_returns_400(client):
    """PUT with empty body must reject — protects against accidental
    no-op writes that would leave cfg inconsistent with the file."""
    async with client as c:
        r = await c.put("/api/cfg/audio-defaults", json={})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_put_coerces_truthy_values_to_bool(client):
    """Defensive: webui sends booleans, but other clients might send 1/0
    or strings. The handler should bool-coerce so the cfg flag stays
    typed correctly."""
    async with client as c:
        # Non-bool truthy → True
        r1 = await c.put(
            "/api/cfg/audio-defaults",
            json={"companion_suppress_desktop": 1},
        )
        assert r1.status_code == 200
        assert r1.json()["companion_suppress_desktop"] is True

        # Non-bool falsy → False
        r2 = await c.put(
            "/api/cfg/audio-defaults",
            json={"companion_suppress_desktop": 0},
        )
        assert r2.status_code == 200
        assert r2.json()["companion_suppress_desktop"] is False
