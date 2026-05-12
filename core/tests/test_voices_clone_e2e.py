"""End-to-end voice cloning: POST audio → real XTTS clone → voice ref on disk."""
from __future__ import annotations

import io
import wave

import pytest
from httpx import AsyncClient, ASGITransport

from claude_code_talker.characters import Character
from claude_code_talker.server import build_server_state, build_asgi_app


def _silent_wav_bytes(duration_secs: float = 1.0, framerate: int = 16000) -> bytes:
    """Generate a minimal valid wav for clone-upload tests."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        nframes = int(duration_secs * framerate)
        w.writeframes(b"\x00\x00" * nframes)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_clone_voice_endpoint_calls_real_cloner(tmp_path, monkeypatch):
    """POST /api/characters/{cid}/clone-voice must invoke clone_from_local_file
    with the actual audio bytes — not the v1 stub that discards them."""
    refs_dir = tmp_path / "refs"

    # Create a character to clone against first
    state = build_server_state()
    state.characters.save(Character(id="test-char", display_name="Test", voice_ref="seed"))

    # Configure the XTTS references dir in state.cfg
    if state.cfg.get("engines") is None:
        state.cfg["engines"] = {}
    if state.cfg["engines"].get("xtts") is None:
        state.cfg["engines"]["xtts"] = {}
    state.cfg["engines"]["xtts"]["references_dir"] = str(refs_dir)
    
    # Patch the real cloner so we can observe the call.
    calls = []

    async def fake_clone(path, *, name, references_dir):
        calls.append({"path": str(path), "name": name, "refs": str(references_dir)})
        # Simulate the real cloner writing the reference wav.
        (references_dir / f"{name}.wav").write_bytes(b"REF")

    monkeypatch.setattr(
        "claude_code_talker.voices.clone.clone_from_local_file",
        fake_clone,
    )

    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        wav = _silent_wav_bytes()
        files = {"audio": ("voice.wav", wav, "audio/wav")}
        resp = await client.post("/api/characters/test-char/clone-voice", files=files)

    assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "job_id" in body, body

    # Real cloner must have been called with the actual bytes' path.
    assert len(calls) == 1, "clone_from_local_file was never called — stub still in place"
    assert calls[0]["name"] == "test-char"

    # Reference wav must exist where the cloner wrote it.
    assert (refs_dir / "test-char.wav").exists(), f"Reference not found at {refs_dir / 'test-char.wav'}"
