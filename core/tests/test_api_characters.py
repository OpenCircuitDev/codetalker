"""Phase 25a — REST API tests for /api/characters."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from claude_code_talker.characters import Character, CharacterStore


@pytest.fixture
def state_with_chars(tmp_path):
    """Build server state with a CharacterStore pointed at tmp_path."""
    from claude_code_talker.server import build_server_state
    state = build_server_state()
    state.characters = CharacterStore(characters_dir=tmp_path / "chars")
    return state


@pytest.fixture
def app(state_with_chars):
    """Build an ASGI app with the test state."""
    from claude_code_talker.server import build_asgi_app
    return build_asgi_app(state_with_chars, disable_transport_security=True)


@pytest.mark.asyncio
async def test_list_characters_empty(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/characters")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_list_characters_returns_saved(state_with_chars, app):
    state_with_chars.characters.save(Character(id="alice", display_name="Alice", voice_ref="v"))
    state_with_chars.characters.save(Character(id="bob", display_name="Bob", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/characters")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        ids = {c["id"] for c in data}
        assert ids == {"alice", "bob"}


@pytest.mark.asyncio
async def test_get_character_by_id(state_with_chars, app):
    state_with_chars.characters.save(Character(id="alice", display_name="Alice", voice_ref="alice-voice"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/characters/alice")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "alice"
        assert data["display_name"] == "Alice"
        assert data["voice_ref"] == "alice-voice"


@pytest.mark.asyncio
async def test_get_character_404_when_missing(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/characters/nope")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_character_400_on_invalid_id(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/characters/UPPER-CASE")
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_post_character_creates(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"id": "alice", "display_name": "Alice", "voice_ref": "alice-voice"}
        r = await client.post("/api/characters", json=body)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "alice"
        assert data["created_at"] > 0
        assert data["updated_at"] > 0


@pytest.mark.asyncio
async def test_post_character_400_on_invalid_body(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/characters", json={"id": "BAD", "display_name": "X", "voice_ref": "v"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_post_character_409_when_exists(state_with_chars, app):
    state_with_chars.characters.save(Character(id="alice", display_name="A", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"id": "alice", "display_name": "Alice", "voice_ref": "v"}
        r = await client.post("/api/characters", json=body)
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_put_character_updates(state_with_chars, app):
    state_with_chars.characters.save(Character(id="alice", display_name="Old Name", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"id": "alice", "display_name": "New Name", "voice_ref": "v"}
        r = await client.put("/api/characters/alice", json=body)
        assert r.status_code == 200
        assert r.json()["display_name"] == "New Name"


@pytest.mark.asyncio
async def test_put_character_404_when_missing(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"id": "nope", "display_name": "X", "voice_ref": "v"}
        r = await client.put("/api/characters/nope", json=body)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_character_400_on_id_mismatch(state_with_chars, app):
    state_with_chars.characters.save(Character(id="alice", display_name="A", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"id": "different", "display_name": "X", "voice_ref": "v"}
        r = await client.put("/api/characters/alice", json=body)
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_character_returns_deleted_true(state_with_chars, app):
    state_with_chars.characters.save(Character(id="alice", display_name="A", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete("/api/characters/alice")
        assert r.status_code == 200
        assert r.json() == {"deleted": True}
        # And the character is actually gone
        r2 = await client.get("/api/characters/alice")
        assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_character_404_when_missing(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete("/api/characters/nope")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_character_cascades_session_detach(state_with_chars, app):
    """Deleting a character should null out attached_character on any live sessions."""
    state_with_chars.characters.save(Character(id="alice", display_name="A", voice_ref="v"))
    s = state_with_chars.sessions.touch("test-sid", cwd="/tmp", transcript_path="")
    s.attached_character = "alice"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete("/api/characters/alice")
        assert r.status_code == 200
    # After delete, the session's attached_character should be None
    assert state_with_chars.sessions.get("test-sid").attached_character is None
