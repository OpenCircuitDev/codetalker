"""Tests for REST API routes via httpx ASGITransport."""
import json
import time
import pytest
import httpx
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state
from claude_code_talker.profiles import ProfileStore
from claude_code_talker.audio import AudioQueue, AudioJob
from claude_code_talker.narration_log import NarrationLog


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
    # 2026-05-16 -- /api/health now includes narration_enabled and
    # narration_warning so clients can surface the master narration
    # switch state. Assert the core contract (ok=True) without
    # locking down the exact field set.
    body = r.json()
    assert body["ok"] is True


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


# ---------------------------------------------------------------------------
# PUT /api/llm-models/default — per-mode model selection (Sub-task 2.2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_llm_default_with_mode_field(app, monkeypatch, tmp_path):
    """PUT with mode='live' only updates cfg.modes.live.{provider, model}."""
    application, state = app
    # Inject a mock openrouter provider so the endpoint accepts it
    from unittest.mock import MagicMock
    mock_prov = MagicMock()
    mock_prov.model = "google/gemini-2.0-flash-001"
    mock_prov.api_key = "fake-key"
    mock_prov.__class__ = mock_prov.__class__  # keep as MagicMock
    state.providers["openrouter"] = mock_prov
    # Suppress disk write
    monkeypatch.setattr("claude_code_talker.api._persist_default_provider", lambda *a, **kw: None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/llm-models/default", json={
            "provider": "openrouter",
            "model": "anthropic/claude-haiku-4-5",
            "mode": "live",
        })

    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True
    assert body["updated_modes"] == ["live"]
    # Only cfg.modes.live is updated — brief should not be touched
    assert state.cfg["modes"]["live"]["provider"] == "openrouter"
    assert state.cfg["modes"]["live"]["model"] == "anthropic/claude-haiku-4-5"
    # brief should NOT have been set by this call
    assert "model" not in state.cfg.get("modes", {}).get("brief", {})


@pytest.mark.asyncio
async def test_put_llm_default_without_mode_updates_all(app, monkeypatch, tmp_path):
    """PUT without mode updates both live and brief (existing behavior preserved)."""
    application, state = app
    from unittest.mock import MagicMock
    mock_prov = MagicMock()
    mock_prov.model = "google/gemini-2.0-flash-001"
    mock_prov.api_key = "fake-key"
    state.providers["openrouter"] = mock_prov
    monkeypatch.setattr("claude_code_talker.api._persist_default_provider", lambda *a, **kw: None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/llm-models/default", json={
            "provider": "openrouter",
            "model": "google/gemini-2.0-flash-lite-001",
        })

    assert r.status_code == 200
    body = r.json()
    assert body["live_uses"] == "openrouter"
    assert body["brief_uses"] == "openrouter"
    assert "live" in body["updated_modes"]
    assert "brief" in body["updated_modes"]
    assert state.cfg["modes"]["live"]["provider"] == "openrouter"
    assert state.cfg["modes"]["brief"]["provider"] == "openrouter"


@pytest.mark.asyncio
async def test_hooks_status_returns_installed_false_when_settings_missing(app, monkeypatch, tmp_path):
    application, state = app
    monkeypatch.setattr("claude_code_talker.api.CLAUDE_SETTINGS_PATH",
                        tmp_path / "settings.json")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/hooks-status")
    assert r.status_code == 200
    body = r.json()
    assert body["installed"] is False
    assert body["settings_path"].endswith("settings.json")
    assert "missing_events" in body
    assert set(body["missing_events"]) == {"Stop", "Notification", "PreToolUse", "PostToolUse", "UserPromptSubmit"}


@pytest.mark.asyncio
async def test_hooks_status_returns_installed_true_after_install(app, monkeypatch, tmp_path):
    application, state = app
    monkeypatch.setattr("claude_code_talker.api.CLAUDE_SETTINGS_PATH",
                        tmp_path / "settings.json")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        # First install
        await c.post("/api/install-hooks")
        # Then check status
        r = await c.get("/api/hooks-status")
    body = r.json()
    assert body["installed"] is True
    assert body["missing_events"] == []


@pytest.mark.asyncio
async def test_put_persistent_session_mirrors_enabled_to_live_registry(app):
    """Phase 13.6d regression — PUT /persistent-sessions/{sid} must update the
    in-memory SessionRegistry too, not just persist to disk. Otherwise the
    mute toggle doesn't take effect until daemon restart.
    """
    application, state = app
    # Force an active session into the registry
    state.sessions.touch("test-mute-sid", cwd="C:/test")
    assert state.sessions.get("test-mute-sid").enabled is True
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put(
            "/api/persistent-sessions/test-mute-sid",
            json={"enabled": False, "live_overlay": {}},
        )
    assert r.status_code == 200
    # The live registry MUST reflect the change immediately
    assert state.sessions.get("test-mute-sid").enabled is False, (
        "PUT /persistent-sessions did not mirror enabled to in-memory SessionRegistry — "
        "mute toggle would not take effect without daemon restart"
    )


@pytest.mark.asyncio
async def test_put_persistent_session_auto_registers_when_missing_from_live(app):
    """Phase 13.7d cold-start regression — when the session isn't in the live
    registry yet (typical right after daemon restart), PUT enabled=False must
    BOTH persist AND create a live entry so the mute takes immediate effect.
    """
    application, state = app
    sid = "cold-start-sid-13-7d"
    # Confirm it's NOT in the live registry to start
    assert state.sessions.get(sid) is None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put(
            "/api/persistent-sessions/" + sid,
            json={"enabled": False, "live_overlay": {}},
        )
    assert r.status_code == 200
    # The live registry MUST now have it with enabled=False
    live = state.sessions.get(sid)
    assert live is not None, (
        "PUT did not auto-register the cold-start session in the live registry"
    )
    assert live.enabled is False


# ────────────────────────────────────────────────────────────────────────────
# POST /api/audio/rewind — replay last N seconds of narration (2026-05-21)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audio_rewind_requeus_recent_entries(app, tmp_path):
    """Rewind endpoint reads narration_log, filters by timestamp and mode,
    and resubmits matching entries to the audio queue."""
    application, state = app

    # Wire a narration log and audio queue to the state
    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    # Mock audio queue with a list to capture submitted jobs
    submitted_jobs = []
    
    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)
    
    state.audio_queue = MockAudioQueue()

    # Build fake narration log with 3 entries within the 30s window
    # and 1 entry outside the window
    now = time.time()
    old_entry = {
        "timestamp": now - 60.0,  # 60s ago, outside 30s window
        "session_id": "sid-old",
        "text": "this is too old",
        "voice": "voice1",
        "engine": "piper",
        "mode": "live",
    }
    recent_entries = [
        {
            "timestamp": now - 20.0,  # 20s ago, within window
            "session_id": "sid-1",
            "text": "message one",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
        },
        {
            "timestamp": now - 15.0,  # 15s ago, within window
            "session_id": "sid-2",
            "text": "message two",
            "voice": "voice2",
            "engine": "piper",
            "mode": "brief",
        },
        {
            "timestamp": now - 5.0,  # 5s ago, within window
            "session_id": "sid-1",
            "text": "message three",
            "voice": "voice1",
            "engine": "piper",
            "mode": "direct",
        },
    ]

    # Append entries to the narration log
    narration_log.append(old_entry)
    for entry in recent_entries:
        narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/rewind", json={"seconds": 30})

    assert r.status_code == 200
    body = r.json()
    # Should requeue the 3 entries within the window, drop the old one
    assert body["requeued"] == 3
    assert len(submitted_jobs) == 3
    
    # Verify the submitted jobs have the correct text
    texts = {job.text for job in submitted_jobs}
    assert texts == {"message one", "message two", "message three"}
    
    # Verify they were submitted with the correct session IDs
    sessions = {job.session_id for job in submitted_jobs}
    assert sessions == {"sid-1", "sid-2"}


@pytest.mark.asyncio
async def test_audio_rewind_filters_by_session(app, tmp_path):
    """When session_id is provided, only entries for that session are requeued."""
    application, state = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []
    
    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)
    
    state.audio_queue = MockAudioQueue()

    now = time.time()
    entries = [
        {
            "timestamp": now - 10.0,
            "session_id": "sid-A",
            "text": "from A",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
        },
        {
            "timestamp": now - 5.0,
            "session_id": "sid-B",
            "text": "from B",
            "voice": "voice2",
            "engine": "piper",
            "mode": "live",
        },
    ]

    for entry in entries:
        narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/rewind", json={"seconds": 30, "session_id": "sid-A"})

    assert r.status_code == 200
    body = r.json()
    assert body["requeued"] == 1
    assert len(submitted_jobs) == 1
    assert submitted_jobs[0].session_id == "sid-A"
    assert submitted_jobs[0].text == "from A"


@pytest.mark.asyncio
async def test_audio_rewind_returns_error_when_queue_missing(app):
    """Rewind returns 503 when audio_queue is not available."""
    application, state = app
    state.narration_log = NarrationLog()
    state.audio_queue = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/rewind", json={"seconds": 30})

    assert r.status_code == 503
    assert "unavailable" in r.json()["error"].lower()


@pytest.mark.asyncio
async def test_audio_rewind_returns_zero_when_no_entries(app, tmp_path):
    """Rewind returns requeued=0 when narration log is empty or outside window."""
    application, state = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log-empty.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []
    
    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)
    
    state.audio_queue = MockAudioQueue()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/rewind", json={"seconds": 30})

    assert r.status_code == 200
    body = r.json()
    assert body["requeued"] == 0
    assert "no entries in window" in body.get("message", "").lower()
