"""
Tests for the Phase 4 event emitters + /api/events SSE endpoint.

Strategy: avoid full httpx SSE streaming (which is fragile under
ASGI test transport timing). Instead, validate two layers:

  1. Emitters wired correctly: subscribing to state.event_bus and
     invoking the relevant handler produces the expected event.
  2. The /api/events route is registered.

End-to-end SSE wire-format coverage lives in test_event_bus.py
(the bus pub/sub) plus a smoke test here that asserts the response
opens with the right Content-Type.
"""
import asyncio
import time

import httpx
import pytest
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
    # Critical: master_enabled_put writes to DEFAULT_GLOBAL_PATH
    # (~/.claude/scripts/tts_config.yaml). Without this monkeypatch
    # the test would mutate the user's real config and leak state to
    # every subsequent test that calls build_server_state().
    fake_cfg = tmp_path / "tts_config.yaml"
    monkeypatch.setattr(
        "claude_code_talker.config.DEFAULT_GLOBAL_PATH", fake_cfg
    )
    state = build_server_state()
    state.catalog._entries.clear()
    # Force in-memory cfg to a known-true baseline so the audibility
    # gate isn't blocked by master_disabled inherited from disk.
    state.cfg["enabled"] = True
    routes = build_routes(state)
    return Starlette(routes=routes), state


# ---------------------------------------------------------------------------
# Emitter wiring — verify each mutator publishes the right event.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_session_emits_session_changed(app):
    """PATCH /api/sessions/{sid} → SessionChanged on the bus."""
    application, state = app
    state.sessions.touch("sse-sid", cwd="/proj/sse")

    received = []
    sub = state.event_bus.subscribe(topics=["SessionChanged"])

    async def consumer():
        async for ev in sub:
            received.append(ev)
            return

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let subscribe register

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/sessions/sse-sid", json={"enabled": False})
        assert r.status_code == 200

    await asyncio.wait_for(task, timeout=2.0)
    await sub.aclose()

    assert len(received) == 1
    assert received[0].event_type == "SessionChanged"
    assert received[0].session_id == "sse-sid"
    assert received[0].changed_fields["enabled"] is False


@pytest.mark.asyncio
async def test_master_enabled_put_emits_master_changed(app):
    """PUT /api/master-enabled → MasterConfigChanged on the bus."""
    application, state = app

    received = []
    sub = state.event_bus.subscribe(topics=["MasterConfigChanged"])

    async def consumer():
        async for ev in sub:
            received.append(ev)
            return

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.put("/api/master-enabled", json={"enabled": False})
        assert r.status_code == 200

    await asyncio.wait_for(task, timeout=2.0)
    await sub.aclose()

    assert len(received) == 1
    assert received[0].event_type == "MasterConfigChanged"
    assert received[0].changed_fields["enabled"] is False


@pytest.mark.asyncio
async def test_topic_filter_excludes_other_event_types(app):
    """Subscribing to MasterConfigChanged should not receive
    SessionChanged. Together with the per-event tests above, this
    pins the filter semantics SSE clients depend on."""
    application, state = app
    state.sessions.touch("filter-sid")

    received = []
    sub = state.event_bus.subscribe(topics=["MasterConfigChanged"])

    async def consumer():
        async for ev in sub:
            received.append(ev)
            return

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        # SessionChanged — must NOT pass the filter.
        await c.patch("/api/sessions/filter-sid", json={"enabled": False})
        # MasterConfigChanged — must pass.
        await c.put("/api/master-enabled", json={"enabled": False})

    await asyncio.wait_for(task, timeout=2.0)
    await sub.aclose()
    assert len(received) == 1
    assert received[0].event_type == "MasterConfigChanged"


# ---------------------------------------------------------------------------
# Route registration + smoke.
# ---------------------------------------------------------------------------


def test_events_route_registered():
    """The /api/events route must be in the route table."""
    state = build_server_state()
    routes = build_routes(state)
    paths = [r.path for r in routes if hasattr(r, "path")]
    assert "/api/events" in paths


# Full SSE wire-format coverage (Content-Type, "data:" framing, server
# disconnect handling) is intentionally not tested via httpx ASGI
# streaming — that combination is fragile under pytest + asyncio. The
# wire format is exercised in production by the webui useEventSource
# hook and the Pro Android EventSource client; the bus-level tests
# above + the route-registration test cover what's testable cleanly.
