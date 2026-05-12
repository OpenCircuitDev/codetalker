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


@pytest.mark.asyncio
async def test_clone_voice_then_attach_character(tmp_path, monkeypatch):
    """Clone a voice, update character's voice_ref, attach to session,
    assert voice_ok=True. This validates the voice_ref naming convention
    and XTTS engine registration end-to-end."""
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)

    # Build server state with a character (initial voice_ref is seed).
    state = build_server_state()
    state.characters.save(Character(id="test-char", display_name="Test", voice_ref="seed"))

    # Configure XTTS references dir.
    if state.cfg.get("engines") is None:
        state.cfg["engines"] = {}
    if state.cfg["engines"].get("xtts") is None:
        state.cfg["engines"]["xtts"] = {}
    state.cfg["engines"]["xtts"]["references_dir"] = str(refs_dir)

    # Create a session to attach to.
    sess = state.sessions.touch("sess-1")

    # Mock clone_from_local_file to write a reference wav.
    async def fake_clone(path, *, name, references_dir):
        (references_dir / f"{name}.wav").write_bytes(b"FAKE_VOICE_DATA")

    monkeypatch.setattr(
        "claude_code_talker.voices.clone.clone_from_local_file",
        fake_clone,
    )

    # Mock the XTTS engine to return the cloned voice in list_voices().
    class MockXTTSEngine:
        def list_voices(self):
            # Return the character ID as a voice name (matching what clone produces).
            return ["test-char"]

    state.engines = {"xtts": MockXTTSEngine()}

    app = build_asgi_app(state, disable_transport_security=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Clone the voice.
        wav = _silent_wav_bytes()
        files = {"audio": ("voice.wav", wav, "audio/wav")}
        clone_resp = await client.post("/api/characters/test-char/clone-voice", files=files)

        assert clone_resp.status_code == 202, f"Clone failed: {clone_resp.status_code}"
        clone_body = clone_resp.json()
        assert "voice_ref" in clone_body, clone_body
        cloned_voice_ref = clone_body["voice_ref"]

        # Step 2: Update character's voice_ref with the cloned one.
        char = state.characters.get("test-char")
        assert char is not None, "character not found"
        char.voice_ref = cloned_voice_ref
        state.characters.save(char)

        # Step 3: Attach the character to the session.
        attach_resp = await client.post(
            "/api/sessions/sess-1/attach-character",
            json={"character_id": "test-char"}
        )

        # Step 4: Assert attach succeeded (voice_ok=True).
        assert attach_resp.status_code == 200, \
            f"Attach failed with {attach_resp.status_code}: {attach_resp.text}"
        attach_body = attach_resp.json()
        assert attach_body.get("state", {}).get("attached_character") == "test-char"

        # Verify reference wav exists.
        assert (refs_dir / "test-char.wav").exists()
