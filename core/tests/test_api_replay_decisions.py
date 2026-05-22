"""Tests for POST /api/audio/replay-decisions endpoint."""
import json
import time
import pytest
import httpx
from starlette.applications import Starlette
from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state
from claude_code_talker.narration_log import NarrationLog


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Build isolated test app with narration log + audio queue."""
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
    return Starlette(routes=routes), state, tmp_path


@pytest.mark.asyncio
async def test_replay_decisions_empty_log(app):
    """Empty log returns replayed=0 without error."""
    application, state, tmp_path = app

    # Wire a narration log and audio queue to the state
    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []

    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)

    state.audio_queue = MockAudioQueue()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/replay-decisions", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["replayed"] == 0
    assert body["window_seconds"] == 1800.0
    assert body["session_id"] is None
    assert len(submitted_jobs) == 0


@pytest.mark.asyncio
async def test_replay_decisions_filters_to_checkpoints(app):
    """Only entries with checkpoint=True are replayed."""
    application, state, tmp_path = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []

    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)

    state.audio_queue = MockAudioQueue()

    # Build fake narration log with checkpoints and non-checkpoints
    now = time.time()
    entries = [
        {
            "timestamp": now - 20.0,  # within window
            "session_id": "sid-1",
            "text": "decision one",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,  # checkpoint
        },
        {
            "timestamp": now - 15.0,  # within window
            "session_id": "sid-1",
            "text": "not a checkpoint",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": False,  # NOT a checkpoint
        },
        {
            "timestamp": now - 10.0,  # within window
            "session_id": "sid-1",
            "text": "decision two",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,  # checkpoint
        },
    ]

    for entry in entries:
        narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/replay-decisions", json={"window_seconds": 30})

    assert r.status_code == 200
    body = r.json()
    # Should replay only the 2 checkpoint entries, skip the non-checkpoint
    assert body["replayed"] == 2
    assert len(submitted_jobs) == 2

    # Verify the submitted jobs have checkpoint texts
    texts = {job.text for job in submitted_jobs}
    assert texts == {"decision one", "decision two"}


@pytest.mark.asyncio
async def test_replay_decisions_filters_by_window(app):
    """Only entries within window_seconds are replayed."""
    application, state, tmp_path = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []

    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)

    state.audio_queue = MockAudioQueue()

    # Build fake narration log with checkpoints at various timestamps
    now = time.time()
    entries = [
        {
            "timestamp": now - 3600.0,  # 1 hour ago, outside any reasonable window
            "session_id": "sid-1",
            "text": "old decision",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 20.0,  # 20s ago, within 30min
            "session_id": "sid-1",
            "text": "recent decision",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
    ]

    for entry in entries:
        narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/replay-decisions", json={"window_seconds": 1800})

    assert r.status_code == 200
    body = r.json()
    # Should only replay the recent decision, not the old one
    assert body["replayed"] == 1
    assert len(submitted_jobs) == 1
    assert submitted_jobs[0].text == "recent decision"


@pytest.mark.asyncio
async def test_replay_decisions_filters_by_session(app):
    """When session_id is provided, only entries for that session are replayed."""
    application, state, tmp_path = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []

    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)

    state.audio_queue = MockAudioQueue()

    # Build fake narration log with checkpoints from different sessions
    now = time.time()
    entries = [
        {
            "timestamp": now - 20.0,
            "session_id": "sid-1",
            "text": "decision from session 1",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 15.0,
            "session_id": "sid-2",
            "text": "decision from session 2",
            "voice": "voice2",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 10.0,
            "session_id": "sid-1",
            "text": "another decision from session 1",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
    ]

    for entry in entries:
        narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post(
            "/api/audio/replay-decisions",
            json={"window_seconds": 30, "session_id": "sid-1"},
        )

    assert r.status_code == 200
    body = r.json()
    # Should only replay the 2 entries from sid-1, not the one from sid-2
    assert body["replayed"] == 2
    assert body["session_id"] == "sid-1"
    assert len(submitted_jobs) == 2

    sessions = {job.session_id for job in submitted_jobs}
    assert sessions == {"sid-1"}


@pytest.mark.asyncio
async def test_replay_decisions_default_window(app):
    """Default window_seconds=1800 when omitted."""
    application, state, tmp_path = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []

    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)

    state.audio_queue = MockAudioQueue()

    # Create a checkpoint within default window (1800s = 30min)
    now = time.time()
    entry = {
        "timestamp": now - 60.0,  # 1 min ago, within default 30min window
        "session_id": "sid-1",
        "text": "decision",
        "voice": "voice1",
        "engine": "piper",
        "mode": "live",
        "checkpoint": True,
    }
    narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        # Omit window_seconds to use default
        r = await c.post("/api/audio/replay-decisions", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["window_seconds"] == 1800.0
    assert body["replayed"] == 1


@pytest.mark.asyncio
async def test_replay_decisions_returns_error_when_queue_missing(app):
    """Returns 503 error when audio queue is not available."""
    application, state, tmp_path = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log
    # Clear the audio queue to simulate it being unavailable
    state.audio_queue = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/replay-decisions", json={})

    assert r.status_code == 503
    body = r.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_replay_decisions_multiple_checkpoints(app):
    """Replay multiple checkpoints maintaining order."""
    application, state, tmp_path = app

    narration_log = NarrationLog(log_path=tmp_path / "narration-log.jsonl")
    state.narration_log = narration_log

    submitted_jobs = []

    class MockAudioQueue:
        def submit(self, job):
            submitted_jobs.append(job)

    state.audio_queue = MockAudioQueue()

    # Build fake narration log with 5 checkpoints within window
    now = time.time()
    entries = [
        {
            "timestamp": now - 50.0,
            "session_id": "sid-1",
            "text": "decision 1",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 40.0,
            "session_id": "sid-1",
            "text": "decision 2",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 30.0,
            "session_id": "sid-1",
            "text": "decision 3",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 20.0,
            "session_id": "sid-1",
            "text": "decision 4",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
        {
            "timestamp": now - 10.0,
            "session_id": "sid-1",
            "text": "decision 5",
            "voice": "voice1",
            "engine": "piper",
            "mode": "live",
            "checkpoint": True,
        },
    ]

    for entry in entries:
        narration_log.append(entry)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/audio/replay-decisions", json={"window_seconds": 60})

    assert r.status_code == 200
    body = r.json()
    assert body["replayed"] == 5
    assert len(submitted_jobs) == 5

    # Verify all 5 decisions were replayed
    texts = {job.text for job in submitted_jobs}
    assert texts == {
        "decision 1",
        "decision 2",
        "decision 3",
        "decision 4",
        "decision 5",
    }
