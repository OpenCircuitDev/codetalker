"""Tests for voices.transcribe (whisper.cpp wrapper + WhisperX forced-align).

Phase 14 Task 4 — v0.4.0 unified scope:
  - Segment / parse_whisper_output / transcribe_audio  — whisper.cpp preview wizard
  - WordTime / align_words                             — WhisperX word-level timestamps
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_code_talker.voices.transcribe import (
    Segment,
    WordTime,
    align_words,
    parse_whisper_output,
    transcribe_audio,
)


# ---------------------------------------------------------------------------
# Segment dataclass (whisper.cpp / preview wizard)
# ---------------------------------------------------------------------------


def test_segment_dataclass():
    s = Segment(start=1.0, end=2.5, text="hello")
    assert s.start == 1.0
    assert s.end == 2.5
    assert s.text == "hello"


# ---------------------------------------------------------------------------
# parse_whisper_output
# ---------------------------------------------------------------------------


def test_parse_whisper_output_extracts_segments():
    raw = json.dumps(
        {
            "transcription": [
                {"offsets": {"from": 1000, "to": 2500}, "text": " hello world"},
                {"offsets": {"from": 2500, "to": 4000}, "text": " more text"},
            ]
        }
    )
    segs = parse_whisper_output(raw)
    assert len(segs) == 2
    assert segs[0].start == 1.0
    assert segs[0].end == 2.5
    assert segs[0].text == "hello world"  # leading space stripped


def test_parse_whisper_output_handles_empty():
    assert parse_whisper_output("") == []
    assert parse_whisper_output("not json") == []


# ---------------------------------------------------------------------------
# transcribe_audio — whisper.cpp subprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_runs_whisper_subprocess(tmp_path, monkeypatch):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)
    fake_json = json.dumps(
        {
            "transcription": [
                {"offsets": {"from": 0, "to": 1500}, "text": " first segment"},
            ]
        }
    )

    # Stub out binary/model discovery so the test doesn't require real installs
    monkeypatch.setattr(
        "claude_code_talker.voices.transcribe._whisper_binary",
        lambda: "whisper-cpp",
    )
    monkeypatch.setattr(
        "claude_code_talker.voices.transcribe._whisper_model",
        lambda: str(tmp_path / "ggml-small.en.bin"),
    )

    async def fake_run(*args, **kwargs):
        # whisper.cpp writes {stem}.json when given -of {stem}
        # Find the -of argument and derive the .json output path.
        arg_list = list(args)
        for i, a in enumerate(arg_list):
            if a == "-of" and i + 1 < len(arg_list):
                json_path = Path(arg_list[i + 1] + ".json")
                json_path.write_text(fake_json, encoding="utf-8")
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    segs = await transcribe_audio(audio)
    assert len(segs) == 1
    assert segs[0].text == "first segment"


@pytest.mark.asyncio
async def test_transcribe_propagates_whisper_error(tmp_path, monkeypatch):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)

    monkeypatch.setattr(
        "claude_code_talker.voices.transcribe._whisper_binary",
        lambda: "whisper-cpp",
    )
    monkeypatch.setattr(
        "claude_code_talker.voices.transcribe._whisper_model",
        lambda: str(tmp_path / "ggml-small.en.bin"),
    )

    async def fake_run(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b"model not found\n"))
        proc.returncode = 1
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)
    with pytest.raises(RuntimeError, match="whisper"):
        await transcribe_audio(audio)


# ---------------------------------------------------------------------------
# WordTime dataclass (WhisperX / lip-sync)
# ---------------------------------------------------------------------------


def test_word_time_dataclass():
    wt = WordTime(text="hello", start=0.1, end=0.4)
    assert wt.text == "hello"
    assert wt.start == 0.1
    assert wt.end == 0.4
    # WordTime and Segment have different field shapes — no overlap required
    assert not hasattr(wt, "offsets")


# ---------------------------------------------------------------------------
# align_words — WhisperX subprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_align_words_runs_whisperx_subprocess(tmp_path, monkeypatch):
    """align_words should spawn a subprocess using whisperx and parse its JSON output."""
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 200)
    text = "hello world"

    fake_output = json.dumps(
        [
            {"text": "hello", "start": 0.1, "end": 0.4},
            {"text": "world", "start": 0.5, "end": 0.9},
        ]
    )

    async def fake_run(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(
            return_value=(fake_output.encode(), b"")
        )
        proc.returncode = 0
        return proc

    captured: list[tuple] = []

    async def capturing_run(*args, **kwargs):
        captured.append(args)
        return await fake_run(*args, **kwargs)

    monkeypatch.setattr("asyncio.create_subprocess_exec", capturing_run)

    result = await align_words(audio, text)

    # Command should include sys.executable and whisperx-related args
    assert len(captured) == 1
    cmd_args = captured[0]
    cmd_flat = " ".join(str(a) for a in cmd_args)
    assert sys.executable in cmd_flat or "python" in cmd_flat.lower()
    assert "whisperx" in cmd_flat.lower() or "-m" in cmd_flat

    # Parsed result
    assert len(result) == 2
    assert result[0].text == "hello"
    assert result[0].start == pytest.approx(0.1)
    assert result[0].end == pytest.approx(0.4)
    assert result[1].text == "world"


@pytest.mark.asyncio
async def test_align_words_propagates_whisperx_error(tmp_path, monkeypatch):
    """Non-zero exit from the subprocess should raise RuntimeError."""
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 200)

    async def fake_run(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(
            return_value=(b"", b"CUDA out of memory\n")
        )
        proc.returncode = 1
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)

    with pytest.raises(RuntimeError):
        await align_words(audio, "some text")


@pytest.mark.asyncio
async def test_align_words_raises_when_whisperx_missing(tmp_path, monkeypatch):
    """When subprocess fails because whisperx module is not installed, surface a
    clean RuntimeError about WhisperX not being installed."""
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 200)

    async def fake_run(*args, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(
            return_value=(
                b"",
                b"No module named whisperx\n",
            )
        )
        proc.returncode = 1
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)

    with pytest.raises(RuntimeError, match="[Ww]hisper[Xx].*not installed|not installed.*[Ww]hisper[Xx]"):
        await align_words(audio, "some text")


@pytest.mark.asyncio
async def test_align_words_handles_empty_text_gracefully(tmp_path, monkeypatch):
    """Empty transcript input should return an empty list without invoking subprocess."""
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 200)

    called = []

    async def fake_run(*args, **kwargs):  # pragma: no cover
        called.append(args)
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"[]", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_run)

    result = await align_words(audio, "")
    assert result == []
    # Subprocess should NOT be called for empty text (fast-path short-circuit)
    assert called == []
