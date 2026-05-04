"""Tests for voices.dependency_check."""
import pytest
from pathlib import Path
from claude_code_talker.voices.dependency_check import check_deps


def test_check_deps_returns_expected_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("claude_code_talker.voices.dependency_check.DEPS_DIR", tmp_path)
    result = check_deps()
    assert set(result.keys()) >= {"yt_dlp", "ffmpeg", "whisper", "all_present", "install_hint"}


def test_check_deps_finds_local_binary(tmp_path, monkeypatch):
    monkeypatch.setattr("claude_code_talker.voices.dependency_check.DEPS_DIR", tmp_path)
    # Pretend ffmpeg is in deps/ffmpeg/ffmpeg
    fake = tmp_path / "ffmpeg" / "ffmpeg"
    fake.parent.mkdir(parents=True)
    fake.write_text("")
    fake.chmod(0o755)
    result = check_deps()
    assert result["ffmpeg"] is True


def test_check_deps_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.voices.dependency_check.DEPS_DIR", tmp_path)
    # Mock shutil.which to return a path for ffmpeg only
    import shutil
    orig = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    result = check_deps()
    assert result["ffmpeg"] is True
    assert result["yt_dlp"] is False
    assert result["all_present"] is False


def test_install_hint_mentions_missing_only(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.voices.dependency_check.DEPS_DIR", tmp_path)
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = check_deps()
    assert "yt-dlp" in result["install_hint"]
    assert "ffmpeg" in result["install_hint"]
    assert "whisper" in result["install_hint"]
