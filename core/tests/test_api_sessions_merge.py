"""Tests for the merged /api/sessions view (live + catalog + persistent)."""
import pytest
import httpx
from pathlib import Path
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state
from claude_code_talker.catalog import CatalogEntry


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
async def test_merged_includes_catalog_only_sessions(app):
    application, state = app
    state.catalog._entries["catalog-only"] = CatalogEntry(
        session_id="catalog-only", project_slug="proj-a",
        transcript_path=Path("/t/catalog-only.jsonl"), last_modified=100.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    body = r.json()
    sids = [s["session_id"] for s in body]
    assert "catalog-only" in sids
    catalog_only_entry = next(s for s in body if s["session_id"] == "catalog-only")
    assert catalog_only_entry["is_live"] is False


@pytest.mark.asyncio
async def test_merged_marks_live_sessions(app):
    application, state = app
    state.catalog._entries["both"] = CatalogEntry(
        session_id="both", project_slug="proj-b",
        transcript_path=Path("/t/both.jsonl"), last_modified=100.0,
    )
    state.sessions.touch("both", cwd="/proj/b")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    body = r.json()
    entry = next(s for s in body if s["session_id"] == "both")
    assert entry["is_live"] is True


@pytest.mark.asyncio
async def test_merged_includes_has_persistent_settings_flag(app):
    application, state = app
    state.catalog._entries["with-persist"] = CatalogEntry(
        session_id="with-persist", project_slug="proj-c",
        transcript_path=Path("/t/with-persist.jsonl"), last_modified=100.0,
    )
    state.persistent_sessions.save("with-persist", {
        "live_overlay": {}, "enabled": True, "attached_profile": None,
        "display_name": None, "last_modified": 1.0,
    })
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    entry = next(s for s in r.json() if s["session_id"] == "with-persist")
    assert entry["has_persistent_settings"] is True


@pytest.mark.asyncio
async def test_merged_sorted_by_last_modified_desc(app):
    application, state = app
    state.catalog._entries["older"] = CatalogEntry(
        session_id="older", project_slug="p", transcript_path=Path("/t/o.jsonl"),
        last_modified=100.0,
    )
    state.catalog._entries["newer"] = CatalogEntry(
        session_id="newer", project_slug="p", transcript_path=Path("/t/n.jsonl"),
        last_modified=200.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    sids = [s["session_id"] for s in r.json()]
    assert sids.index("newer") < sids.index("older")


@pytest.mark.asyncio
async def test_merged_includes_enabled_flag_default_true(app):
    application, state = app
    state.catalog._entries["aaa"] = CatalogEntry(
        session_id="aaa", project_slug="p", transcript_path=Path("/t/a.jsonl"),
        last_modified=100.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    entry = next(s for s in r.json() if s["session_id"] == "aaa")
    assert entry["enabled"] is True
