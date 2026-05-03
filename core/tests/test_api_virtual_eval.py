"""Tests for /api/virtual-eval/* endpoints."""
import asyncio
import json
import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, patch
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state


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
    monkeypatch.setattr(
        "claude_code_talker.virtual_eval.history.DEFAULT_HISTORY_PATH",
        tmp_path / "tuning.jsonl",
    )
    state = build_server_state()
    state.catalog._entries.clear()
    routes = build_routes(state)
    return Starlette(routes=routes), state


@pytest.mark.asyncio
async def test_get_history_empty(app):
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/virtual-eval/history")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_latest_when_no_runs_returns_null(app):
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/virtual-eval/latest")
    assert r.status_code == 200
    assert r.json() == {"latest": None}


@pytest.mark.asyncio
async def test_post_run_returns_report(app, monkeypatch):
    application, state = app
    fake_report = {
        "personas_count": 5, "narrations_evaluated": 3,
        "aggregate": {"total_evals": 15},
        "proposal": {"fields_to_set": {"glossary": True}, "reasoning": "x", "pending_approval": False},
        "applied": True,
    }
    async def fake_run(**kwargs):
        return fake_report
    monkeypatch.setattr("claude_code_talker.virtual_eval.run_eval", fake_run)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/virtual-eval/run")
    assert r.status_code == 200
    body = r.json()
    assert body["personas_count"] == 5
    assert body["applied"] is True


@pytest.mark.asyncio
async def test_post_revert_unknown_id_returns_404(app):
    application, state = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/virtual-eval/revert/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_returns_last_run(app, monkeypatch):
    application, state = app
    fake_report = {
        "personas_count": 5, "narrations_evaluated": 1,
        "aggregate": {"total_evals": 5},
        "proposal": {"fields_to_set": {}, "reasoning": "", "pending_approval": False},
        "applied": False,
    }
    async def fake_run(**kwargs):
        return fake_report
    monkeypatch.setattr("claude_code_talker.virtual_eval.run_eval", fake_run)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        await c.post("/api/virtual-eval/run")
        r = await c.get("/api/virtual-eval/latest")
    body = r.json()
    assert body["latest"]["personas_count"] == 5
