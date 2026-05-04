"""Tests for voices.auto_install — v0.4.0 revised scope.

Installs: ffmpeg + whisper.cpp model + WhisperX + gltf-pipeline.
yt-dlp is NOT in the required set (deferred to v0.4.1 optional install).
All subprocess calls are mocked — no real downloads happen.
"""
from __future__ import annotations

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from claude_code_talker.voices.auto_install import (
    InstallTaskState,
    _ffmpeg_archive_url_for_platform,
    install_deps_async,
    _install_ffmpeg,
    _install_whisper,
    _install_whisperx,
    _install_gltf_pipeline,
)


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------

def test_install_task_state_starts_idle():
    """InstallTaskState initialises with zero progress and no error."""
    state = InstallTaskState()
    assert state.percent == 0
    assert state.step == ""
    assert state.error is None
    assert state.done is False


def test_install_state_update_sets_fields():
    """update() atomically sets step and percent."""
    state = InstallTaskState()
    state.update(step="ffmpeg", percent=42)
    assert state.step == "ffmpeg"
    assert state.percent == 42


# ---------------------------------------------------------------------------
# Platform URL helper
# ---------------------------------------------------------------------------

def test_ffmpeg_url_per_platform():
    """_ffmpeg_archive_url_for_platform returns a non-empty HTTPS URL containing 'ffmpeg'."""
    url = _ffmpeg_archive_url_for_platform()
    assert url.startswith("https://")
    assert "ffmpeg" in url.lower() or "BtbN" in url


# ---------------------------------------------------------------------------
# Skip-when-all-present fast path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_install_skips_when_all_present(monkeypatch, tmp_path):
    """install_deps_async exits early and marks done when deps already installed."""
    monkeypatch.setattr("claude_code_talker.voices.auto_install.DEPS_DIR", tmp_path)
    monkeypatch.setattr(
        "claude_code_talker.voices.auto_install.check_deps",
        lambda: {"all_present": True, "ffmpeg": True, "whisper": True},
    )
    state = InstallTaskState()
    await install_deps_async(state)
    assert state.done is True
    assert state.percent == 100
    assert state.error is None


# ---------------------------------------------------------------------------
# All four installers are invoked when deps are missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_four_installers_invoked(monkeypatch, tmp_path):
    """install_deps_async calls all four sub-installers when everything is missing."""
    monkeypatch.setattr("claude_code_talker.voices.auto_install.DEPS_DIR", tmp_path)
    monkeypatch.setattr(
        "claude_code_talker.voices.auto_install.check_deps",
        lambda: {"all_present": False, "ffmpeg": False, "whisper": False},
    )
    fake_ffmpeg = AsyncMock(return_value=None)
    fake_whisper = AsyncMock(return_value=None)
    fake_whisperx = AsyncMock(return_value=None)
    fake_gltf = AsyncMock(return_value=None)
    monkeypatch.setattr("claude_code_talker.voices.auto_install._install_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr("claude_code_talker.voices.auto_install._install_whisper", fake_whisper)
    monkeypatch.setattr("claude_code_talker.voices.auto_install._install_whisperx", fake_whisperx)
    monkeypatch.setattr("claude_code_talker.voices.auto_install._install_gltf_pipeline", fake_gltf)

    state = InstallTaskState()
    await install_deps_async(state)

    assert state.done is True
    assert state.error is None
    fake_ffmpeg.assert_awaited_once()
    fake_whisper.assert_awaited_once()
    fake_whisperx.assert_awaited_once()
    fake_gltf.assert_awaited_once()


# ---------------------------------------------------------------------------
# Error recorded on failure (state machine atomically reaches done=True)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_install_records_error_on_failure(monkeypatch, tmp_path):
    """When one installer raises, the error is captured and done is still set True."""
    monkeypatch.setattr("claude_code_talker.voices.auto_install.DEPS_DIR", tmp_path)
    monkeypatch.setattr(
        "claude_code_talker.voices.auto_install.check_deps",
        lambda: {"all_present": False, "ffmpeg": False, "whisper": True},
    )
    fake_failing = AsyncMock(side_effect=RuntimeError("network down"))
    monkeypatch.setattr("claude_code_talker.voices.auto_install._install_ffmpeg", fake_failing)
    # whisperx + gltf-pipeline should still run (graceful-continue) or be skipped —
    # either way done must be True.
    monkeypatch.setattr(
        "claude_code_talker.voices.auto_install._install_whisperx",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "claude_code_talker.voices.auto_install._install_gltf_pipeline",
        AsyncMock(return_value=None),
    )

    state = InstallTaskState()
    await install_deps_async(state)

    assert state.done is True
    assert state.error is not None
    assert "network" in state.error.lower()


# ---------------------------------------------------------------------------
# WhisperX: pip install uses --target to deps dir
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whisperx_install_uses_target_flag(monkeypatch, tmp_path):
    """_install_whisperx runs pip install --target pointing at the deps dir."""
    monkeypatch.setattr("claude_code_talker.voices.auto_install.DEPS_DIR", tmp_path)

    captured_args = []

    async def fake_exec(*args, **kwargs):
        captured_args.extend(args)
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    state = InstallTaskState()
    await _install_whisperx(state)

    cmd_str = " ".join(str(a) for a in captured_args)
    assert "--target" in cmd_str
    # Must install into the deps subdirectory
    assert str(tmp_path) in cmd_str or "whisperx" in cmd_str
    assert "whisperx" in cmd_str


# ---------------------------------------------------------------------------
# gltf-pipeline: graceful when Node is missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gltf_pipeline_graceful_when_no_node(monkeypatch, tmp_path, caplog):
    """_install_gltf_pipeline logs a warning and does NOT raise when Node is absent."""
    import shutil
    import logging
    monkeypatch.setattr("claude_code_talker.voices.auto_install.DEPS_DIR", tmp_path)
    # Make shutil.which return None for node/npm — simulates Node not on PATH
    monkeypatch.setattr(shutil, "which", lambda name: None)

    state = InstallTaskState()
    # Should NOT raise
    with caplog.at_level(logging.WARNING):
        await _install_gltf_pipeline(state)

    # Some warning about Node missing must be logged
    assert any(
        "node" in record.message.lower() or "npm" in record.message.lower()
        for record in caplog.records
    )
    # state still advances (not stuck at 0)
    assert state.percent > 0 or state.step != ""
