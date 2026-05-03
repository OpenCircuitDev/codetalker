"""Tests for REST API routes via httpx ASGITransport."""
import pytest
import httpx
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state


@pytest.fixture
def app():
    state = build_server_state()
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
