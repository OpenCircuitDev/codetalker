"""Tests for Phase 14 v0.4.0 voice REST endpoints.

All heavy dependencies (ffmpeg, whisper, XTTS) are mocked so tests are fast.
Uses the same 'app' fixture pattern as test_api.py.
"""
from __future__ import annotations

import dataclasses
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.applications import Starlette

from claude_code_talker.api import build_routes
from claude_code_talker.server import build_server_state


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, monkeypatch):
    """Build a Starlette app with all voice routes wired."""
    monkeypatch.setattr("claude_code_talker.catalog.DEFAULT_PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr("claude_code_talker.persistent_sessions.DEFAULT_SESSIONS_DIR", tmp_path / "persistent")
    state = build_server_state()
    state.catalog._entries.clear()

    # Point voices references dir to tmp_path so we don't touch real files
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir()
    monkeypatch.setattr(
        "claude_code_talker.api._VOICES_REFS_DEFAULT",
        refs_dir,
    )

    routes = build_routes(state)
    return Starlette(routes=routes), state, refs_dir


@pytest.fixture
def client(app):
    application, _, _ = app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    )


# ---------------------------------------------------------------------------
# Helper — write a minimal WAV file
# ---------------------------------------------------------------------------

def _write_wav(path: Path, *, duration_frames: int = 22050) -> None:
    """Write a valid 22050 Hz mono 16-bit WAV to *path*."""
    import wave, struct
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(struct.pack("<" + "h" * duration_frames, *([0] * duration_frames)))


# ---------------------------------------------------------------------------
# GET /api/voices/list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voices_list_empty_refs_dir(client, app):
    """When refs dir is empty, voices list is empty."""
    async with client as c:
        r = await c.get("/api/voices/list")
    assert r.status_code == 200
    assert r.json() == {"voices": []}


@pytest.mark.asyncio
async def test_voices_list_returns_voices(client, app):
    """WAV files in refs dir appear in the list."""
    _, _, refs_dir = app
    _write_wav(refs_dir / "riley.wav")
    _write_wav(refs_dir / "alex.wav")
    # Write a sidecar for riley
    from claude_code_talker.voices.metadata import VoiceMetadata, write_metadata
    write_metadata(refs_dir, VoiceMetadata(name="riley", source_type="audio"))

    async with client as c:
        r = await c.get("/api/voices/list")
    assert r.status_code == 200
    body = r.json()
    names = [v["name"] for v in body["voices"]]
    assert "riley" in names
    assert "alex" in names
    riley = next(v for v in body["voices"] if v["name"] == "riley")
    assert riley["metadata"] is not None
    assert riley["metadata"]["source_type"] == "audio"


# ---------------------------------------------------------------------------
# GET /api/voices/dependency-status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dependency_status_all_missing(client, monkeypatch):
    """When nothing is installed, all_present is False and yt_dlp is informational."""
    monkeypatch.setattr(
        "claude_code_talker.voices.dependency_check.check_deps",
        lambda: {"yt_dlp": False, "ffmpeg": False, "whisper": False, "all_present": False,
                 "install_hint": "Missing: ffmpeg, whisper"},
    )
    async with client as c:
        r = await c.get("/api/voices/dependency-status")
    assert r.status_code == 200
    body = r.json()
    assert body["all_present"] is False
    assert "yt_dlp" in body
    assert "ffmpeg" in body
    assert "whisper" in body


@pytest.mark.asyncio
async def test_dependency_status_ffmpeg_whisper_present_means_all_present(client, monkeypatch):
    """Even if yt_dlp is absent, all_present is True when ffmpeg + whisper are there."""
    monkeypatch.setattr(
        "claude_code_talker.voices.dependency_check.check_deps",
        lambda: {"yt_dlp": False, "ffmpeg": True, "whisper": True, "all_present": False,
                 "install_hint": ""},
    )
    async with client as c:
        r = await c.get("/api/voices/dependency-status")
    assert r.status_code == 200
    body = r.json()
    assert body["all_present"] is True


# ---------------------------------------------------------------------------
# POST /api/voices/install-dependencies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_install_dependencies_returns_task_id(client, monkeypatch):
    """POST starts a background install and returns a task_id."""
    # Patch install_deps_async to a no-op coroutine so it doesn't actually run
    async def _noop(state):
        state.done = True

    monkeypatch.setattr("claude_code_talker.voices.auto_install.install_deps_async", _noop)
    async with client as c:
        r = await c.post("/api/voices/install-dependencies")
    assert r.status_code == 200
    body = r.json()
    assert "task_id" in body
    assert len(body["task_id"]) > 10


# ---------------------------------------------------------------------------
# GET /api/voices/install-status/<task_id>
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_install_status_not_found(client):
    async with client as c:
        r = await c.get("/api/voices/install-status/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_install_status_returns_task_state(client, app):
    """Manually inject a task and retrieve its status."""
    from claude_code_talker.voices.auto_install import InstallTaskState
    _, state, _ = app
    task_id = "test-task-123"
    task = InstallTaskState(step="ffmpeg", percent=40, done=False)
    state.voice_install_tasks[task_id] = task

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get(f"/api/voices/install-status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["step"] == "ffmpeg"
    assert body["percent"] == 40
    assert body["done"] is False


# ---------------------------------------------------------------------------
# POST /api/voices/clone-from-file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clone_from_file_missing_audio_field(client):
    async with client as c:
        r = await c.post("/api/voices/clone-from-file", data={"name": "riley"})
    assert r.status_code == 400
    assert "audio" in r.json()["error"]


@pytest.mark.asyncio
async def test_clone_from_file_missing_name(client):
    async with client as c:
        r = await c.post(
            "/api/voices/clone-from-file",
            files={"audio": ("test.wav", b"fake-audio", "audio/wav")},
        )
    assert r.status_code == 400
    assert "name" in r.json()["error"]


@pytest.mark.asyncio
async def test_clone_from_file_happy_path(client, app, tmp_path, monkeypatch):
    """Mock clone_from_local_file and verify response shape."""
    _, _, refs_dir = app

    async def _fake_clone(source, *, name, references_dir, start, end):
        out = references_dir / "riley.wav"
        _write_wav(out)
        return out

    monkeypatch.setattr("claude_code_talker.voices.clone.clone_from_local_file", _fake_clone)
    # Patch _is_video to return False (audio-only source)
    monkeypatch.setattr("claude_code_talker.voices.clone._is_video", lambda p: False)

    async with client as c:
        r = await c.post(
            "/api/voices/clone-from-file",
            files={"audio": ("interview.wav", b"fake-audio", "audio/wav")},
            data={"name": "riley"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "riley"
    assert "voice_path" in body
    assert body["face_frame_path"] is None
    assert body["metadata"] is not None
    assert body["metadata"]["source_type"] == "audio"


# ---------------------------------------------------------------------------
# POST /api/voices/preview-extract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_extract_missing_source_path(client):
    async with client as c:
        r = await c.post("/api/voices/preview-extract", json={})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_preview_extract_file_not_found(client):
    async with client as c:
        r = await c.post("/api/voices/preview-extract",
                         json={"source_path": "/nonexistent/file.wav"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_extract_happy_path(client, app, tmp_path, monkeypatch):
    """Mock ffmpeg + transcribe and verify token + segments returned."""
    _, state, _ = app
    # Create a real file to pass the existence check
    source = tmp_path / "interview.wav"
    _write_wav(source)

    # Mock ffmpeg subprocess
    async def _fake_subprocess(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_subprocess)

    # Mock transcribe_audio
    from claude_code_talker.voices.transcribe import Segment
    monkeypatch.setattr(
        "claude_code_talker.voices.transcribe.transcribe_audio",
        AsyncMock(return_value=[Segment(start=0.0, end=2.0, text="hello world")]),
    )

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/voices/preview-extract",
                         json={"source_path": str(source)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "token" in body
    assert body["audio_url"].startswith("/api/voices/preview-audio/")
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == "hello world"
    # Token is stored in state
    assert body["token"] in state.voice_preview_audio


# ---------------------------------------------------------------------------
# GET /api/voices/preview-audio/<token>
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_audio_not_found(client):
    async with client as c:
        r = await c.get("/api/voices/preview-audio/bad-token")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_audio_serves_wav(client, app, tmp_path):
    """If a token is registered, we get back the WAV bytes."""
    _, state, _ = app
    wav = tmp_path / "preview.wav"
    _write_wav(wav)
    state.voice_preview_audio["my-token"] = wav

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.get("/api/voices/preview-audio/my-token")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert len(r.content) > 0


# ---------------------------------------------------------------------------
# POST /api/voices/clone-from-preview
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clone_from_preview_missing_token(client):
    async with client as c:
        r = await c.post("/api/voices/clone-from-preview", json={"name": "voice"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_clone_from_preview_bad_token(client):
    async with client as c:
        r = await c.post("/api/voices/clone-from-preview",
                         json={"token": "bad", "name": "voice"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_clone_from_preview_happy_path(client, app, tmp_path, monkeypatch):
    _, state, refs_dir = app
    wav = tmp_path / "preview.wav"
    _write_wav(wav)
    state.voice_preview_audio["tok-123"] = wav

    async def _fake_clone(source, *, name, references_dir, start, end):
        out = references_dir / "preview_voice.wav"
        _write_wav(out)
        return out

    monkeypatch.setattr("claude_code_talker.voices.clone.clone_from_local_file", _fake_clone)

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/api/voices/clone-from-preview",
                         json={"token": "tok-123", "name": "preview_voice",
                               "start": 0.5, "end": 5.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "preview_voice"
    assert "metadata" in body


# ---------------------------------------------------------------------------
# PATCH /api/voices/<name>  (rename)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voices_rename_not_found(client):
    async with client as c:
        r = await c.patch("/api/voices/nope", json={"new_name": "other"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_voices_rename_happy_path(client, app):
    _, _, refs_dir = app
    _write_wav(refs_dir / "old.wav")
    from claude_code_talker.voices.metadata import VoiceMetadata, write_metadata
    write_metadata(refs_dir, VoiceMetadata(name="old"))

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/voices/old", json={"new_name": "new"})
    assert r.status_code == 200
    body = r.json()
    assert body["old_name"] == "old"
    assert body["new_name"] == "new"
    assert (refs_dir / "new.wav").exists()
    assert not (refs_dir / "old.wav").exists()


@pytest.mark.asyncio
async def test_voices_rename_conflict(client, app):
    _, _, refs_dir = app
    _write_wav(refs_dir / "a.wav")
    _write_wav(refs_dir / "b.wav")

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.patch("/api/voices/a", json={"new_name": "b"})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /api/voices/<name>
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voices_delete_not_found(client):
    async with client as c:
        r = await c.delete("/api/voices/gone")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_voices_delete_happy_path(client, app):
    _, _, refs_dir = app
    _write_wav(refs_dir / "temp.wav")
    (refs_dir / "temp.json").write_text("{}", encoding="utf-8")

    application, _, _ = app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.delete("/api/voices/temp")
    assert r.status_code == 200
    assert r.json() == {"deleted": True}
    assert not (refs_dir / "temp.wav").exists()
    assert not (refs_dir / "temp.json").exists()
