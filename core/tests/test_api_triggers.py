"""Tests for Phase 14.5 trigger-mode REST endpoints.

Covers:
  GET  /api/triggers/config
  PUT  /api/triggers/config
  GET  /api/triggers/tags
  POST /api/triggers/tags
  GET  /api/triggers/tags/<id>
  PUT  /api/triggers/tags/<id>
  DELETE /api/triggers/tags/<id>
  POST /api/triggers/skill-install
  GET  /api/triggers/skill-preview
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette

from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state


# ---------------------------------------------------------------------------
# Shared fixture — isolated server state with overlay + skill paths redirected
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

    # Redirect the cfg-overlay.yaml so we never touch the real user file
    overlay_path = tmp_path / "cfg-overlay.yaml"
    monkeypatch.setattr(
        "claude_code_talker.api._TRIGGERS_OVERLAY_PATH",
        overlay_path,
    )

    # Redirect the SKILL.md install target
    skills_root = tmp_path / "skills"
    monkeypatch.setattr(
        "claude_code_talker.triggers.skill._SKILLS_ROOT",
        skills_root,
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


# ---------------------------------------------------------------------------
# 1. GET /api/triggers/config — returns expected fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_config_returns_expected_fields(client):
    async with client as c:
        r = await c.get("/api/triggers/config")
    assert r.status_code == 200
    body = r.json()
    assert "mode" in body
    assert "teacher_level" in body
    assert "persona" in body
    assert "skill_installed" in body
    # Defaults
    assert body["mode"] in ("llm", "trigger", "both")
    assert isinstance(body["skill_installed"], bool)


# ---------------------------------------------------------------------------
# 2. PUT /api/triggers/config — saves mode and reloads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_config_saves_mode(app):
    application, state, overlay_path = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/triggers/config", json={"mode": "trigger"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # Verify live.mode mirrored so the trigger handler sees it
    assert state.cfg.get("live", {}).get("mode") == "trigger"
    # Verify persisted to overlay
    assert overlay_path.exists()
    import yaml
    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
    assert overlay.get("triggers", {}).get("mode") == "trigger"
    assert overlay.get("live", {}).get("mode") == "trigger"


# ---------------------------------------------------------------------------
# 3. GET /api/triggers/tags — returns list with starter set bootstrapped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_tags_returns_starter_set(client):
    """On fresh state, bootstrapped starter tags are returned."""
    async with client as c:
        r = await c.get("/api/triggers/tags")
    assert r.status_code == 200
    body = r.json()
    assert "tags" in body
    ids = {t["id"] for t in body["tags"]}
    # Original 5 starter tags must always be present; the set has grown to
    # include plan-mode / subagent / skill / permission tags. Future
    # additions should not break this test.
    assert {"audible_summary", "audible_synopsis", "audible_briefs",
            "audible_listings", "audible_details"} <= ids
    assert len(body["tags"]) >= 5


# ---------------------------------------------------------------------------
# 4. POST /api/triggers/tags — creates a new tag with normalized ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_tags_creates_tag_with_normalized_id(client):
    async with client as c:
        r = await c.post("/api/triggers/tags", json={
            "display_name": "Audible Recap",
            "enabled": True,
            "when_to_trigger": "when the session is wrapping up",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "audible_recap"
    assert body["display_name"] == "Audible Recap"
    assert body["enabled"] is True


# ---------------------------------------------------------------------------
# 5. POST /api/triggers/tags — rejects empty display_name with 400
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_tags_rejects_empty_display_name(client):
    async with client as c:
        r = await c.post("/api/triggers/tags", json={"display_name": ""})
    assert r.status_code == 400
    assert "display_name" in r.json().get("error", "")


# ---------------------------------------------------------------------------
# 6. GET /api/triggers/tags/<id> — returns single tag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_single_tag_returns_tag(client):
    async with client as c:
        r = await c.get("/api/triggers/tags/audible_summary")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "audible_summary"
    assert "display_name" in body


# ---------------------------------------------------------------------------
# 7. GET /api/triggers/tags/<id> — returns 404 for unknown id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_single_tag_404_when_missing(client):
    async with client as c:
        r = await c.get("/api/triggers/tags/nonexistent_tag")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 8. PUT /api/triggers/tags/<id> — merges partial update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_tag_merges_partial_update(app):
    application, state, overlay_path = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/triggers/tags/audible_summary", json={
            "enabled": True,
            "when_to_trigger": "on every step",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "audible_summary"
    assert body["enabled"] is True
    assert body["when_to_trigger"] == "on every step"
    # display_name should still be present (unchanged)
    assert "display_name" in body


# ---------------------------------------------------------------------------
# 9. DELETE /api/triggers/tags/<id> — removes the tag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_tag_removes_it(app):
    application, _state, _overlay = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        # First create a tag to delete
        await c.post("/api/triggers/tags", json={"display_name": "Audible Temp"})
        r = await c.delete("/api/triggers/tags/audible_temp")
    assert r.status_code == 200
    assert r.json() == {"deleted": True}


# ---------------------------------------------------------------------------
# 10. DELETE /api/triggers/tags/<id> — 404 when missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_tag_404_when_missing(client):
    async with client as c:
        r = await c.delete("/api/triggers/tags/no_such_tag_xyz")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 11. POST /api/triggers/skill-install — writes SKILL.md, returns enabled_count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_install_writes_file_and_returns_enabled_count(app):
    application, state, overlay_path = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/triggers/skill-install")
    assert r.status_code == 200
    body = r.json()
    assert "installed_at" in body
    assert "enabled_count" in body
    assert isinstance(body["enabled_count"], int)
    # Verify the file actually exists at the returned path
    installed_path = Path(body["installed_at"])
    assert installed_path.exists()
    text = installed_path.read_text(encoding="utf-8")
    assert "Codetalker" in text or "codetalker" in text


# ---------------------------------------------------------------------------
# 12. GET /api/triggers/skill-preview — returns plain text of composed SKILL.md
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_preview_returns_plain_text(client):
    async with client as c:
        r = await c.get("/api/triggers/skill-preview")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    # Should contain skill content
    text = r.text
    assert "Codetalker" in text or "codetalker" in text
