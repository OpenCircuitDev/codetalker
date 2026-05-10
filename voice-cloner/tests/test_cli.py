"""Tests for the voice-cloner CLI."""
import subprocess
import sys
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _mock_ffmpeg_present(monkeypatch):
    """Pretend ffmpeg is installed for all CLI tests by default."""
    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, b"ffmpeg version 6.0", b"")
    monkeypatch.setattr(
        "claude_code_voice_cloner.cli.subprocess.run", fake_run
    )


def test_cli_list_shows_names(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("claude_code_voice_cloner.registry.DEFAULT_REGISTRY", tmp_path)
    (tmp_path / "marvin.wav").write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", ["voice-cloner", "list"])
    from claude_code_voice_cloner.cli import main
    main()
    out = capsys.readouterr().out
    assert "marvin" in out


def test_cli_remove_invokes_registry(tmp_path, monkeypatch):
    monkeypatch.setattr("claude_code_voice_cloner.registry.DEFAULT_REGISTRY", tmp_path)
    (tmp_path / "marvin.wav").write_bytes(b"x")
    (tmp_path / "marvin.json").write_text("{}")
    monkeypatch.setattr(sys, "argv", ["voice-cloner", "remove", "--name", "marvin"])
    from claude_code_voice_cloner.cli import main
    main()
    assert not (tmp_path / "marvin.wav").exists()


def test_check_ffmpeg_exits_when_missing(monkeypatch):
    """If ffmpeg is not on PATH, _check_ffmpeg should exit non-zero."""
    def raise_not_found(cmd, *args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "ffmpeg")
    monkeypatch.setattr(
        "claude_code_voice_cloner.cli.subprocess.run", raise_not_found
    )
    from claude_code_voice_cloner.cli import _check_ffmpeg
    with pytest.raises(SystemExit) as exc_info:
        _check_ffmpeg()
    # SystemExit with a string message is treated as an error (non-zero) by sys.exit
    assert exc_info.value.code != 0
    assert "ffmpeg" in str(exc_info.value.code).lower()


def test_check_ffmpeg_exits_when_nonzero_returncode(monkeypatch):
    """If ffmpeg -version returns non-zero, _check_ffmpeg should exit non-zero."""
    def fake_run_fail(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, 127, b"", b"command not found")
    monkeypatch.setattr(
        "claude_code_voice_cloner.cli.subprocess.run", fake_run_fail
    )
    from claude_code_voice_cloner.cli import _check_ffmpeg
    with pytest.raises(SystemExit) as exc_info:
        _check_ffmpeg()
    assert exc_info.value.code != 0
