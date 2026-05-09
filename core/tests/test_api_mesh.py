"""Phase 25b — mesh REST tests with mocked providers."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from claude_code_talker.characters import Character, CharacterStore
from claude_code_talker.mesh.provider import Mesh3DProvider, MeshJobStatus
from claude_code_talker.mesh.tracker import MeshJobTracker


class _StubProvider(Mesh3DProvider):
    """Mock mesh provider used to drive the API end-to-end without HTTP."""

    name = "stub"
    next_status: str = "queued"
    next_model_url: str | None = None
    last_prompt: str | None = None
    last_image_url: str | None = None
    download_bytes: bytes = b"GLB-BYTES"
    raise_on_start: Exception | None = None

    def __init__(self, api_key: str = "", **_):
        self.api_key = api_key

    def start(self, *, prompt, image_url=None, **opts):
        if _StubProvider.raise_on_start:
            raise _StubProvider.raise_on_start
        _StubProvider.last_prompt = prompt
        _StubProvider.last_image_url = image_url
        return "stub-pjid-1"

    def poll(self, job_id):
        return MeshJobStatus(
            "stub",
            job_id,
            _StubProvider.next_status,
            model_url=_StubProvider.next_model_url,
        )

    def download(self, job_id, dest):
        if not dest.suffix:
            dest = dest.with_suffix(".glb")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_StubProvider.download_bytes)
        return dest


def _reset_stub():
    _StubProvider.next_status = "queued"
    _StubProvider.next_model_url = None
    _StubProvider.last_prompt = None
    _StubProvider.last_image_url = None
    _StubProvider.download_bytes = b"GLB-BYTES"
    _StubProvider.raise_on_start = None


@pytest.fixture(autouse=True)
def _stub_state():
    _reset_stub()
    yield
    _reset_stub()


@pytest.fixture
def state(tmp_path):
    from claude_code_talker.server import build_server_state

    s = build_server_state()
    s.characters = CharacterStore(characters_dir=tmp_path / "chars")
    s.mesh_jobs = MeshJobTracker(tmp_path / "models" / "_jobs")
    s.mesh_models_root = tmp_path / "models"
    return s


@pytest.fixture
def app(state, monkeypatch):
    # Always inject the stub provider regardless of provider name in the body.
    monkeypatch.setattr(
        "claude_code_talker.api.make_provider",
        lambda name, api_key: _StubProvider(api_key=api_key),
    )
    # Ensure secrets store reports configured keys for all providers.
    monkeypatch.setattr(
        state.secrets, "get", lambda key: "stub-key" if key.endswith("_api_key") else None
    )
    from claude_code_talker.server import build_asgi_app

    return build_asgi_app(state, disable_transport_security=True)


@pytest.mark.asyncio
async def test_post_mesh_jobs_starts_a_job(state, app):
    state.characters.save(Character(id="x", display_name="X", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/mesh-jobs",
            json={"character_id": "x", "provider": "hyper3d", "prompt": "fox"},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert body["job_id"]
    # Confirm the provider job id was recorded
    j = state.mesh_jobs.get(body["job_id"])
    assert j is not None
    assert j.provider_job_id == "stub-pjid-1"
    assert _StubProvider.last_prompt == "fox"


@pytest.mark.asyncio
async def test_post_mesh_jobs_unknown_character_404(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/mesh-jobs",
            json={"character_id": "no", "provider": "hyper3d", "prompt": "x"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_mesh_jobs_unknown_provider_400(state, app):
    state.characters.save(Character(id="x", display_name="X", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/mesh-jobs",
            json={"character_id": "x", "provider": "bogus", "prompt": "x"},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_post_mesh_jobs_missing_fields_400(state, app):
    state.characters.save(Character(id="x", display_name="X", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/mesh-jobs", json={"character_id": "x"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_mesh_jobs_lists(state, app):
    state.characters.save(Character(id="x", display_name="X", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/mesh-jobs",
            json={"character_id": "x", "provider": "meshy", "prompt": "robot"},
        )
        r = await client.get("/api/mesh-jobs")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 1


@pytest.mark.asyncio
async def test_get_unknown_mesh_job_404(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/mesh-jobs/nope")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_poll_succeeded_writes_mesh_to_character(state, app, tmp_path):
    state.characters.save(Character(id="hero", display_name="Hero", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        post = await client.post(
            "/api/mesh-jobs",
            json={"character_id": "hero", "provider": "tripo3d", "prompt": "warrior"},
        )
        job_id = post.json()["job_id"]
        # Make stub return succeeded next time
        _StubProvider.next_status = "succeeded"
        _StubProvider.next_model_url = "https://cdn/m.glb"
        r = await client.post(f"/api/mesh-jobs/{job_id}/poll")
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "succeeded"
        assert j["model_path"]
        # Character record updated
        char = state.characters.get("hero")
        assert char.mesh_path == j["model_path"]
        assert char.mesh_provider == "tripo3d"
        assert char.mesh_prompt == "warrior"


@pytest.mark.asyncio
async def test_poll_failure_records_error(state, app):
    state.characters.save(Character(id="x", display_name="X", voice_ref="v"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        post = await client.post(
            "/api/mesh-jobs",
            json={"character_id": "x", "provider": "meshy", "prompt": "p"},
        )
        job_id = post.json()["job_id"]
        _StubProvider.next_status = "failed"
        _StubProvider.next_model_url = None
        r = await client.post(f"/api/mesh-jobs/{job_id}/poll")
        assert r.status_code == 200
        assert r.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_mesh_providers_lists_three(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/mesh-providers")
        assert r.status_code == 200
        items = r.json()
        names = {it["name"] for it in items}
        assert {"hyper3d", "meshy", "tripo3d"}.issubset(names)
