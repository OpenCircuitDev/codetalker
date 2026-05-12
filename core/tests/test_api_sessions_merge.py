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


# --- v0.1.0 unification: transcript-mtime liveness fix ---
# A session is "live" if EITHER it has an in-memory SessionState (existing
# behavior — fired a hook recently) OR its transcript was modified within
# TRANSCRIPT_LIVE_WINDOW_SEC (60s). The mtime path catches CC sessions
# that are open but haven't fired tool-event hooks yet.

@pytest.mark.asyncio
async def test_recently_modified_transcript_marked_live(app, tmp_path, monkeypatch):
    """A session whose transcript was touched within 60s is is_live=True
    even if it has no in-memory SessionState."""
    application, state = app
    # Create a transcript file whose mtime is "now" (well within the 60s window)
    proj_dir = tmp_path / "projects" / "C--Users-test-proj"
    proj_dir.mkdir(parents=True)
    fresh_transcript = proj_dir / "fresh-sid-aaaa.jsonl"
    fresh_transcript.write_text("{}\n", encoding="utf-8")
    # Catalog the entry so it's in the merge loop
    state.catalog._entries["fresh-sid-aaaa"] = CatalogEntry(
        session_id="fresh-sid-aaaa",
        project_slug="proj",
        transcript_path=fresh_transcript,
        last_modified=fresh_transcript.stat().st_mtime,
    )
    # Note: NO state.sessions.touch() — no in-memory state.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    entry = next(s for s in r.json() if s["session_id"] == "fresh-sid-aaaa")
    assert entry["is_live"] is True, (
        "transcript modified <60s ago should be is_live even with no SessionState"
    )


@pytest.mark.asyncio
async def test_old_transcript_not_marked_live_by_mtime(app, tmp_path):
    """A session whose transcript was modified > 60s ago is is_live=False
    unless it also has an in-memory SessionState."""
    import os
    application, state = app
    proj_dir = tmp_path / "projects" / "C--Users-test-proj"
    proj_dir.mkdir(parents=True)
    stale = proj_dir / "stale-sid-bbbb.jsonl"
    stale.write_text("{}\n", encoding="utf-8")
    # Backdate the mtime to 5 minutes ago (well outside the 60s window)
    five_min_ago = stale.stat().st_mtime - 300
    os.utime(stale, (five_min_ago, five_min_ago))
    state.catalog._entries["stale-sid-bbbb"] = CatalogEntry(
        session_id="stale-sid-bbbb",
        project_slug="proj",
        transcript_path=stale,
        last_modified=five_min_ago,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    entry = next(s for s in r.json() if s["session_id"] == "stale-sid-bbbb")
    assert entry["is_live"] is False


@pytest.mark.asyncio
async def test_in_memory_state_still_marks_live_even_with_old_transcript(
    app, tmp_path
):
    """The mtime fix doesn't regress the in-memory path: if a session has
    a SessionState, it stays live regardless of transcript age."""
    import os
    application, state = app
    proj_dir = tmp_path / "projects" / "C--Users-test-proj"
    proj_dir.mkdir(parents=True)
    old_t = proj_dir / "in-mem-cccc.jsonl"
    old_t.write_text("{}\n", encoding="utf-8")
    os.utime(old_t, (old_t.stat().st_mtime - 600, old_t.stat().st_mtime - 600))
    state.catalog._entries["in-mem-cccc"] = CatalogEntry(
        session_id="in-mem-cccc",
        project_slug="proj",
        transcript_path=old_t,
        last_modified=old_t.stat().st_mtime,
    )
    state.sessions.touch("in-mem-cccc", cwd="/proj/c")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/sessions")
    entry = next(s for s in r.json() if s["session_id"] == "in-mem-cccc")
    assert entry["is_live"] is True, "in-memory session should stay live"
