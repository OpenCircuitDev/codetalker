"""Tests for /api/catalog endpoints."""
import pytest
import httpx
from pathlib import Path
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state
from claude_code_talker.catalog import CatalogEntry


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Isolate from the user's real ~/.claude/projects and persistent sessions.
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
async def test_catalog_endpoint_lists_entries(app):
    application, state = app
    state.catalog._entries["aaa"] = CatalogEntry(
        session_id="aaa", project_slug="proj-a",
        transcript_path=Path("/t/aaa.jsonl"), last_modified=100.0,
    )
    state.catalog._entries["bbb"] = CatalogEntry(
        session_id="bbb", project_slug="proj-b",
        transcript_path=Path("/t/bbb.jsonl"), last_modified=200.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    ids = {e["session_id"] for e in body}
    assert ids == {"aaa", "bbb"}


@pytest.mark.asyncio
async def test_catalog_filter_by_project(app):
    application, state = app
    state.catalog._entries["aaa"] = CatalogEntry(
        session_id="aaa", project_slug="proj-a",
        transcript_path=Path("/t/aaa.jsonl"), last_modified=100.0,
    )
    state.catalog._entries["bbb"] = CatalogEntry(
        session_id="bbb", project_slug="proj-b",
        transcript_path=Path("/t/bbb.jsonl"), last_modified=200.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/catalog?project=proj-a")
    body = r.json()
    assert {e["session_id"] for e in body} == {"aaa"}


@pytest.mark.asyncio
async def test_catalog_entry_shape(app):
    application, state = app
    state.catalog._entries["aaa"] = CatalogEntry(
        session_id="aaa", project_slug="proj-a",
        transcript_path=Path("/t/aaa.jsonl"), last_modified=100.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/catalog")
    e = r.json()[0]
    assert "session_id" in e
    assert "project_slug" in e
    assert "transcript_path" in e
    assert "last_modified" in e


@pytest.mark.asyncio
async def test_catalog_invalid_project_400(app):
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/catalog?project=../etc/passwd")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_refresh_triggers_scan(app):
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/catalog/refresh")
    assert r.status_code == 200
    body = r.json()
    assert "scanned" in body


@pytest.mark.asyncio
async def test_refresh_rate_limited_within_5s(app):
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r1 = await c.post("/api/catalog/refresh")
        r2 = await c.post("/api/catalog/refresh")
    assert r1.status_code == 200
    assert r2.status_code == 429
