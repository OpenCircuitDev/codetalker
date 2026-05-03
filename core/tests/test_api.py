"""Tests for REST API routes via httpx ASGITransport."""
import pytest
import httpx
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state
from claude_code_talker.profiles import ProfileStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Isolate from real ~/.claude/projects (catalog scan) and persistent sessions
    # so the merged /api/sessions view doesn't surface the user's real history.
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
    # Override ProfileStore with a tmp_path-isolated instance so tests don't
    # pollute or read the real ~/.claude/scripts/profiles directory.
    state.profiles = ProfileStore(profiles_dir=tmp_path / "profiles")
    routes = build_routes(state)
    return Starlette(routes=routes), state


@pytest.fixture
def client(app):
    application, _ = app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_health_endpoint(client):
    async with client as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_list_sessions_empty_when_no_activity(client):
    async with client as c:
        r = await c.get("/api/sessions")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_sessions_returns_active(app):
    application, state = app
    state.sessions.touch("sess-1", cwd="/proj/a", transcript_path="/t/sess-1.jsonl")
    state.sessions.touch("sess-2", cwd="/proj/b")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    body = r.json()
    assert len(body) == 2
    ids = {s["session_id"] for s in body}
    assert ids == {"sess-1", "sess-2"}
    cwd_for_1 = next(s["cwd"] for s in body if s["session_id"] == "sess-1")
    assert cwd_for_1 == "/proj/a"


@pytest.mark.asyncio
async def test_get_session_returns_state_and_resolved_cfg(app):
    application, state = app
    state.sessions.touch("sess-1", cwd="/proj/a")
    state.sessions.update_overlay("sess-1", {"voice": {"model": "marvin"}})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions/sess-1")
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["session_id"] == "sess-1"
    assert body["state"]["live_overlay"] == {"voice": {"model": "marvin"}}
    assert body["resolved_cfg"]["voice"]["model"] == "marvin"


@pytest.mark.asyncio
async def test_get_session_404_when_unknown(client):
    async with client as c:
        r = await c.get("/api/sessions/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_overlay_merges(app):
    application, state = app
    state.sessions.touch("sess-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/sessions/sess-1/overlay",
                        json={"voice": {"model": "marvin"}, "active_mode": "live"})
    assert r.status_code == 200
    s = state.sessions.get("sess-1")
    assert s.live_overlay == {"voice": {"model": "marvin"}, "active_mode": "live"}
    assert s.cached_cfg is None


@pytest.mark.asyncio
async def test_put_overlay_404_unknown_session(client):
    async with client as c:
        r = await c.put("/api/sessions/nope/overlay", json={"voice": {"model": "x"}})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_overlay_400_malformed_body(app):
    application, state = app
    state.sessions.touch("sess-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/sessions/sess-1/overlay", content=b"{not json")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_put_overlay_400_array_body(app):
    application, state = app
    state.sessions.touch("sess-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/sessions/sess-1/overlay", json=[1, 2, 3])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_overlay_keypath(app):
    application, state = app
    state.sessions.touch("sess-1")
    state.sessions.update_overlay("sess-1", {"voice": {"model": "marvin", "rate": 1.2}})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.delete("/api/sessions/sess-1/overlay/voice.model")
    assert r.status_code == 200
    assert state.sessions.get("sess-1").live_overlay == {"voice": {"rate": 1.2}}


@pytest.mark.asyncio
async def test_attach_profile_records_and_invalidates_cache(app):
    application, state = app
    state.profiles.save("verbose", {"voice": {"model": "marvin"}})
    state.sessions.touch("sess-1", cwd="/proj/a")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/sessions/sess-1/attach-profile", json={"name": "verbose"})
    assert r.status_code == 200
    assert state.sessions.get("sess-1").attached_profile == "verbose"
    assert state.profiles.last_profile_for_cwd("/proj/a") == "verbose"


@pytest.mark.asyncio
async def test_attach_profile_400_when_profile_missing(app):
    application, state = app
    state.sessions.touch("sess-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/sessions/sess-1/attach-profile", json={"name": "ghost"})
    assert r.status_code == 400
    assert "ghost" in r.json()["error"]


@pytest.mark.asyncio
async def test_attach_profile_400_invalid_name(app):
    application, state = app
    state.sessions.touch("sess-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/sessions/sess-1/attach-profile", json={"name": "../etc/passwd"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_detach_profile_clears_and_clears_binding(app):
    application, state = app
    state.profiles.save("verbose", {"x": 1})
    state.sessions.touch("sess-1", cwd="/proj/a")
    state.sessions.attach_profile("sess-1", "verbose")
    state.profiles.set_last_profile_for_cwd("/proj/a", "verbose")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.delete("/api/sessions/sess-1/profile")
    assert r.status_code == 200
    assert state.sessions.get("sess-1").attached_profile is None
    assert state.profiles.last_profile_for_cwd("/proj/a") is None


@pytest.mark.asyncio
async def test_save_as_profile_serializes_overlay(app):
    application, state = app
    state.sessions.touch("sess-1")
    state.sessions.update_overlay("sess-1", {"voice": {"model": "marvin"}, "active_mode": "live"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/sessions/sess-1/save-as-profile",
                         json={"name": "verbose-marvin"})
    assert r.status_code == 200
    assert state.profiles.exists("verbose-marvin")
    assert state.profiles.get("verbose-marvin") == {"voice": {"model": "marvin"}, "active_mode": "live"}


@pytest.mark.asyncio
async def test_save_as_profile_overwrites_existing(app):
    application, state = app
    state.profiles.save("verbose-marvin", {"old": "data"})
    state.sessions.touch("sess-1")
    state.sessions.update_overlay("sess-1", {"voice": {"model": "marvin"}})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/sessions/sess-1/save-as-profile",
                         json={"name": "verbose-marvin"})
    assert r.status_code == 200
    assert state.profiles.get("verbose-marvin") == {"voice": {"model": "marvin"}}


@pytest.mark.asyncio
async def test_save_as_profile_400_invalid_name(app):
    application, state = app
    state.sessions.touch("sess-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/sessions/sess-1/save-as-profile", json={"name": "bad/name"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_save_as_profile_404_unknown_session(client):
    async with client as c:
        r = await c.post("/api/sessions/nope/save-as-profile", json={"name": "x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_profiles_empty(client):
    async with client as c:
        r = await c.get("/api/profiles")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_profiles_returns_names(app):
    application, state = app
    state.profiles.save("alpha", {"x": 1})
    state.profiles.save("zeta", {"x": 1})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/profiles")
    body = r.json()
    names = [p["name"] for p in body]
    assert names == ["alpha", "zeta"]


@pytest.mark.asyncio
async def test_get_profile_returns_content(app):
    application, state = app
    state.profiles.save("verbose", {"voice": {"model": "marvin"}})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/profiles/verbose")
    assert r.status_code == 200
    assert r.json() == {"name": "verbose", "content": {"voice": {"model": "marvin"}}}


@pytest.mark.asyncio
async def test_get_profile_404(client):
    async with client as c:
        r = await c.get("/api/profiles/ghost")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_profile_replaces_content(app):
    application, state = app
    state.profiles.save("verbose", {"old": "data"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/profiles/verbose", json={"voice": {"model": "jenny"}})
    assert r.status_code == 200
    assert state.profiles.get("verbose") == {"voice": {"model": "jenny"}}


@pytest.mark.asyncio
async def test_delete_profile_removes_and_detaches(app):
    application, state = app
    state.profiles.save("verbose", {"x": 1})
    state.sessions.touch("sess-1", cwd="/proj/a")
    state.sessions.attach_profile("sess-1", "verbose")
    state.sessions.touch("sess-2", cwd="/proj/b")
    state.sessions.attach_profile("sess-2", "verbose")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.delete("/api/profiles/verbose")
    assert r.status_code == 200
    body = r.json()
    assert body == {"deleted": True, "detached_from_sessions": 2}
    assert not state.profiles.exists("verbose")
    assert state.sessions.get("sess-1").attached_profile is None
    assert state.sessions.get("sess-2").attached_profile is None


@pytest.mark.asyncio
async def test_delete_profile_404(client):
    async with client as c:
        r = await c.delete("/api/profiles/ghost")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_voices_for_engine(app):
    application, state = app
    from unittest.mock import MagicMock
    state.engines["fake"] = MagicMock(list_voices=lambda: ["voice-a", "voice-b"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/voices?engine=fake")
    assert r.status_code == 200
    assert r.json() == ["voice-a", "voice-b"]


@pytest.mark.asyncio
async def test_voices_400_unknown_engine(client):
    async with client as c:
        r = await c.get("/api/voices?engine=does-not-exist")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_voices_400_missing_engine_param(client):
    async with client as c:
        r = await c.get("/api/voices")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_status_returns_summary(app):
    application, state = app
    state.cfg["enabled"] = True
    state.sessions.touch("s1")
    state.sessions.update_overlay("s1", {"active_mode": "live"})
    state.sessions.touch("s2")
    state.sessions.update_overlay("s2", {"active_mode": "brief"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/status")
    body = r.json()
    assert body["enabled"] is True
    assert body["session_count"] == 2
    assert "engines" in body
    assert "providers" in body


@pytest.mark.asyncio
async def test_mute_sets_enabled_false(app):
    application, state = app
    state.cfg["enabled"] = True
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/mute")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}
    assert state.cfg["enabled"] is False


@pytest.mark.asyncio
async def test_unmute_sets_enabled_true(app):
    application, state = app
    state.cfg["enabled"] = False
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/unmute")
    assert r.status_code == 200
    assert r.json() == {"enabled": True}
    assert state.cfg["enabled"] is True


import json
from pathlib import Path


@pytest.mark.asyncio
async def test_install_hooks_creates_settings_when_absent(app, tmp_path, monkeypatch):
    application, state = app
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("claude_code_talker.api.CLAUDE_SETTINGS_PATH", settings_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/install-hooks")
    assert r.status_code == 200
    body = r.json()
    assert body["installed"] is True
    assert body["hooks_added"] == 5
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "hooks" in data
    assert "Stop" in data["hooks"]
    assert "Notification" in data["hooks"]
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]
    assert "UserPromptSubmit" in data["hooks"]


@pytest.mark.asyncio
async def test_install_hooks_idempotent(app, tmp_path, monkeypatch):
    application, state = app
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("claude_code_talker.api.CLAUDE_SETTINGS_PATH", settings_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r1 = await c.post("/api/install-hooks")
        r2 = await c.post("/api/install-hooks")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["hooks_added"] == 0


@pytest.mark.asyncio
async def test_install_hooks_preserves_unrelated_hooks(app, tmp_path, monkeypatch):
    application, state = app
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "user-script"}]}]
        },
        "other_setting": "preserved",
    }))
    monkeypatch.setattr("claude_code_talker.api.CLAUDE_SETTINGS_PATH", settings_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/install-hooks")
    assert r.status_code == 200
    data = json.loads(settings_path.read_text())
    stop_entries = data["hooks"]["Stop"]
    assert len(stop_entries) == 2
    assert any(any(h.get("command") == "user-script" for h in e.get("hooks", []))
               for e in stop_entries)
    assert any(any(h.get("command") == "claude-code-talker-hook" for h in e.get("hooks", []))
               for e in stop_entries)
    assert data["other_setting"] == "preserved"
