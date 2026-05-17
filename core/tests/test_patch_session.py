"""
Tests for PATCH /api/sessions/{sid} — the Phase 3 typed entry point
for session edits. Replaces the legacy PUT /api/sessions/{sid}/overlay
flat-dict path with a Pydantic-validated SessionPatch.

PUT-overlay still works for backward compat; Phase 6 removes it.
"""
import time
import pytest
import httpx
from pathlib import Path
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state
from claude_code_talker.catalog import CatalogEntry


NOW_ISH = time.time() - 3600.0


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
    state = build_server_state()
    state.catalog._entries.clear()
    routes = build_routes(state)
    return Starlette(routes=routes), state


@pytest.mark.asyncio
async def test_patch_session_returns_session_view_shape(app):
    """Happy path: PATCH a live session, response is a SessionView dict."""
    application, state = app
    state.sessions.touch("live-sid", cwd="/proj/a")
    state.catalog._entries["live-sid"] = CatalogEntry(
        session_id="live-sid", project_slug="proj-a",
        transcript_path=Path("/t/live-sid.jsonl"), last_modified=NOW_ISH,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/sessions/live-sid", json={"display_name": "Renamed"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "live-sid"
    assert body["display_name"] == "Renamed"
    # SessionView always carries these fields:
    assert "enabled" in body
    assert "audio_outputs" in body
    assert "is_live" in body
    assert "is_companion_active" in body


@pytest.mark.asyncio
async def test_patch_session_mutes_session(app):
    """Setting enabled=False persists to the in-memory mute flag."""
    application, state = app
    state.sessions.touch("mute-sid", cwd="/proj/m")
    state.catalog._entries["mute-sid"] = CatalogEntry(
        session_id="mute-sid", project_slug="proj-m",
        transcript_path=Path("/t/mute-sid.jsonl"), last_modified=NOW_ISH,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/sessions/mute-sid", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    # In-memory registry reflects the mute.
    assert state.sessions.get("mute-sid").enabled is False


@pytest.mark.asyncio
async def test_patch_session_unknown_field_rejected(app):
    """SessionPatch has extra=forbid so typos surface as 400."""
    application, state = app
    state.sessions.touch("strict-sid")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/sessions/strict-sid", json={"bogus_field": "x"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_session_invalid_mode_rejected(app):
    """active_mode is a Literal; bad values get 400."""
    application, state = app
    state.sessions.touch("mode-sid")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/sessions/mode-sid", json={"active_mode": "shouting"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_session_unknown_sid_returns_404_when_dormant(app):
    """Patching a sid the daemon doesn't know about returns 404."""
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/sessions/never-existed", json={"enabled": False})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_session_dormant_with_persistent_overlay_succeeds(app):
    """A session that's in persistent storage but not live can still be patched."""
    application, state = app
    state.persistent_sessions.save("dormant-sid", {
        "live_overlay": {}, "enabled": True, "attached_profile": None,
        "display_name": None, "last_modified": 1.0,
    })
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch(
            "/api/sessions/dormant-sid", json={"workspace_group": "BlueprintForge"}
        )
    assert r.status_code == 200
    assert r.json()["workspace_group"] == "BlueprintForge"
    # Persistent storage reflects the change.
    stored = state.persistent_sessions.get("dormant-sid")
    assert stored.get("workspace_group") == "BlueprintForge"


@pytest.mark.asyncio
async def test_patch_session_audio_outputs(app):
    """audio_outputs is a List[AudioOutput]; invalid values rejected, valid persisted."""
    application, state = app
    state.sessions.touch("audio-sid")
    state.catalog._entries["audio-sid"] = CatalogEntry(
        session_id="audio-sid", project_slug="proj-audio",
        transcript_path=Path("/t/audio-sid.jsonl"), last_modified=NOW_ISH,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch(
            "/api/sessions/audio-sid",
            json={"audio_outputs": ["phone", "glasses"]},
        )
    assert r.status_code == 200
    assert set(r.json()["audio_outputs"]) == {"phone", "glasses"}


@pytest.mark.asyncio
async def test_patch_session_cadence_routes_under_live(app):
    """Top-level cadence in the patch lands under live.cadence in persistent."""
    application, state = app
    state.sessions.touch("cadence-sid")
    state.catalog._entries["cadence-sid"] = CatalogEntry(
        session_id="cadence-sid", project_slug="proj-cad",
        transcript_path=Path("/t/cadence-sid.jsonl"), last_modified=NOW_ISH,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch(
            "/api/sessions/cadence-sid",
            json={"cadence": "periodic"},
        )
    assert r.status_code == 200
    stored = state.persistent_sessions.get("cadence-sid")
    assert stored["live_overlay"]["live"]["cadence"] == "periodic"


@pytest.mark.asyncio
async def test_patch_session_legacy_put_overlay_still_works(app):
    """Backward compat: PUT /api/sessions/{sid}/overlay still operational."""
    application, state = app
    state.sessions.touch("legacy-sid", cwd="/proj/l")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put(
            "/api/sessions/legacy-sid/overlay", json={"enabled": False}
        )
    assert r.status_code == 200
    assert state.sessions.get("legacy-sid").enabled is False
