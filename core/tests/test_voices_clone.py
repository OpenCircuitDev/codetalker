"""Tests for voices.clone — v0.4.0 unified (local file + face frame; no URL path)."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from claude_code_talker.voices.clone import (
    sanitize_voice_name,
    build_ffmpeg_clean_args,
    clone_from_local_file,
    extract_face_frame,
    _is_video,
    MIN_DURATION_S,
    MAX_DURATION_S,
)


# ---------------------------------------------------------------------------
# sanitize_voice_name
# ---------------------------------------------------------------------------

def test_sanitize_voice_name_basic():
    assert sanitize_voice_name("My Voice") == "My-Voice"
    assert sanitize_voice_name("riley/test") == "rileytest"
    assert sanitize_voice_name("ok_name-1") == "ok_name-1"


def test_sanitize_voice_name_collision_suffix(tmp_path):
    (tmp_path / "voice.wav").write_text("")
    out = sanitize_voice_name("voice", existing_dir=tmp_path)
    assert out == "voice-2"


# ---------------------------------------------------------------------------
# build_ffmpeg_clean_args
# ---------------------------------------------------------------------------

def test_build_ffmpeg_clean_args_includes_silence_remove():
    args = build_ffmpeg_clean_args(
        input_path="/in.wav", output_path="/out.wav", start=10.0, end=15.0
    )
    flat = " ".join(str(a) for a in args)
    assert "silenceremove" in flat
    assert "loudnorm" in flat
    assert "aresample=22050" in flat
    assert "-ss" in args and "10.0" in flat
    assert "-to" in args and "15.0" in flat
    assert "-ac" in args and "1" in args


def test_build_ffmpeg_args_omits_ss_to_when_no_range():
    args = build_ffmpeg_clean_args(input_path="/in.wav", output_path="/out.wav")
    assert "-ss" not in args
    assert "-to" not in args


# ---------------------------------------------------------------------------
# _is_video
# ---------------------------------------------------------------------------

def test_is_video_returns_true_for_video_extensions():
    assert _is_video(Path("clip.mp4")) is True
    assert _is_video(Path("clip.mov")) is True
    assert _is_video(Path("clip.mkv")) is True
    assert _is_video(Path("clip.webm")) is True
    assert _is_video(Path("clip.avi")) is True
    assert _is_video(Path("clip.m4v")) is True


def test_is_video_returns_false_for_audio_extensions():
    assert _is_video(Path("audio.mp3")) is False
    assert _is_video(Path("audio.wav")) is False
    assert _is_video(Path("audio.m4a")) is False
    assert _is_video(Path("audio.flac")) is False
    assert _is_video(Path("audio.ogg")) is False
    assert _is_video(Path("audio.opus")) is False


def test_is_video_returns_false_for_unknown():
    assert _is_video(Path("file.unknown")) is False
    assert _is_video(Path("file")) is False


# ---------------------------------------------------------------------------
# clone_from_local_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clone_from_local_file_runs_ffmpeg(tmp_path, monkeypatch):
    src = tmp_path / "input.mp3"
    src.write_text("fake")
    refs = tmp_path / "refs"
    refs.mkdir()

    async def fake_run(*args, **kwargs):
        # Simulate ffmpeg writing the output file (last positional arg)
        out = Path(args[-1])
        out.write_bytes(b"RIFF" + b"\x00" * 1000)
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    monkeypatch.setattr(
        "claude_code_talker.voices.clone._probe_duration",
        AsyncMock(return_value=5.0),
    )
    out = await clone_from_local_file(src, name="riley", references_dir=refs)
    assert out.exists()
    assert out.name == "riley.wav"


@pytest.mark.asyncio
async def test_clone_from_local_file_rejects_too_short(tmp_path, monkeypatch):
    src = tmp_path / "input.mp3"
    src.write_text("fake")
    refs = tmp_path / "refs"
    refs.mkdir()

    async def fake_run(*args, **kwargs):
        out = Path(args[-1])
        out.write_bytes(b"RIFF" + b"\x00" * 1000)
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    # Probe says output is 2s (too short)
    monkeypatch.setattr(
        "claude_code_talker.voices.clone._probe_duration",
        AsyncMock(return_value=2.0),
    )
    with pytest.raises(ValueError, match="too short"):
        await clone_from_local_file(src, name="riley", references_dir=refs)


@pytest.mark.asyncio
async def test_clone_from_local_file_propagates_ffmpeg_error(tmp_path, monkeypatch):
    src = tmp_path / "input.mp3"
    src.write_text("fake")
    refs = tmp_path / "refs"
    refs.mkdir()

    async def fake_run(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b"unknown codec\n"))
        proc.returncode = 1
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        await clone_from_local_file(src, name="riley", references_dir=refs)


# ---------------------------------------------------------------------------
# extract_face_frame
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_face_frame_from_video_returns_path(tmp_path, monkeypatch):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"fakevideo")
    out = tmp_path / "face.png"
    call_args = []

    async def fake_run(*args, **kwargs):
        call_args.extend(args)
        out.write_bytes(b"fakepng")
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    # Stub ffprobe for duration (used to compute midpoint)
    monkeypatch.setattr(
        "claude_code_talker.voices.clone._probe_duration",
        AsyncMock(return_value=10.0),
    )

    result = await extract_face_frame(src, out)
    assert result is not None
    assert result == out
    # ffmpeg must have been called with -vframes 1
    flat = " ".join(str(a) for a in call_args)
    assert "-vframes" in flat
    assert "1" in flat


@pytest.mark.asyncio
async def test_extract_face_frame_from_video_uses_explicit_at_seconds(tmp_path, monkeypatch):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"fakevideo")
    out = tmp_path / "face.png"
    call_args = []

    async def fake_run(*args, **kwargs):
        call_args.extend(args)
        out.write_bytes(b"fakepng")
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)

    result = await extract_face_frame(src, out, at_seconds=3.5)
    assert result is not None
    flat = " ".join(str(a) for a in call_args)
    assert "3.5" in flat


@pytest.mark.asyncio
async def test_extract_face_frame_from_audio_returns_none(tmp_path, monkeypatch):
    src = tmp_path / "audio.mp3"
    src.write_bytes(b"fakeaudio")
    out = tmp_path / "face.png"

    ffmpeg_called = []

    async def fake_run(*args, **kwargs):
        ffmpeg_called.append(True)
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)

    result = await extract_face_frame(src, out)
    assert result is None
    # ffmpeg must NOT have been called for audio-only sources
    assert len(ffmpeg_called) == 0


@pytest.mark.asyncio
async def test_extract_face_frame_returns_none_on_ffmpeg_failure(tmp_path, monkeypatch):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"fakevideo")
    out = tmp_path / "face.png"

    async def fake_run(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b"stream not found\n"))
        proc.returncode = 1
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    monkeypatch.setattr(
        "claude_code_talker.voices.clone._probe_duration",
        AsyncMock(return_value=8.0),
    )

    # Must NOT raise — face frame is optional, failures are silent
    result = await extract_face_frame(src, out)
    assert result is None
