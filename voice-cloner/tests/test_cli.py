"""Tests for the voice-cloner CLI."""
import sys
from unittest.mock import patch


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
