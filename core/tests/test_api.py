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
