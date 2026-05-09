"""Phase 25c — clone-voice REST tests."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from claude_code_talker.characters import Character, CharacterStore
from claude_code_talker.voice.cloning_jobs import CloneJobTracker


@pytest.fixture
def state(tmp_path):
    from claude_code_talker.server import build_server_state
    s = build_server_state()
    s.characters = CharacterStore(characters_dir=tmp_path / "chars")
    s.clone_jobs = CloneJobTracker(tmp_path / "clone_jobs")
    return s


@pytest.fixture
def app(state):
    from claude_code_talker.server import build_asgi_app
    return build_asgi_app(state, disable_transport_security=True)


@pytest.mark.asyncio
async def test_clone_voice_returns_job_id(state, app):
    state.characters.save(Character(id="buddy", display_name="Buddy", voice_ref="seed"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"audio": ("sample.webm", b"fake bytes", "audio/webm")}
        data = {"mime_type": "audio/webm"}
        r = await client.post("/api/characters/buddy/clone-voice", files=files, data=data)
        assert r.status_code == 202
        body = r.json()
        # Phase 25c v1: stub clone path completes immediately
        assert body["status"] == "succeeded"
        assert body["job_id"]
        assert body["voice_ref"] == "char-buddy"


@pytest.mark.asyncio
async def test_clone_voice_unknown_character_returns_404(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"audio": ("x.webm", b"x", "audio/webm")}
        r = await client.post("/api/characters/nope/clone-voice", files=files)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_clone_job(state, app):
    state.characters.save(Character(id="x", display_name="X", voice_ref="seed"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"audio": ("a.webm", b"a", "audio/webm")}
        r = await client.post(
            "/api/characters/x/clone-voice", files=files, data={"mime_type": "audio/webm"}
        )
        job_id = r.json()["job_id"]
        g = await client.get(f"/api/voice-clone-jobs/{job_id}")
        assert g.status_code == 200
        assert g.json()["job_id"] == job_id


@pytest.mark.asyncio
async def test_get_clone_job_unknown_returns_404(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/voice-clone-jobs/nope")
        assert r.status_code == 404
