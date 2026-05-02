"""Tests for the reference WAV registry."""
import json
from pathlib import Path
from claude_code_voice_cloner.registry import (
    save_reference, list_references, remove_reference, registry_dir,
)


def test_save_reference_writes_wav_and_json(tmp_path, monkeypatch):
    monkeypatch.setattr("claude_code_voice_cloner.registry.DEFAULT_REGISTRY", tmp_path)
    save_reference("marvin", b"FAKE_WAV", source_url="https://yt/x", start="1:23", duration=15)
    assert (tmp_path / "marvin.wav").exists()
    assert (tmp_path / "marvin.json").exists()
    meta = json.loads((tmp_path / "marvin.json").read_text())
    assert meta["source_url"] == "https://yt/x"


def test_list_references_returns_names(tmp_path, monkeypatch):
    monkeypatch.setattr("claude_code_voice_cloner.registry.DEFAULT_REGISTRY", tmp_path)
    (tmp_path / "marvin.wav").write_bytes(b"x")
    (tmp_path / "strong-bad.wav").write_bytes(b"y")
    (tmp_path / "ignored.txt").write_text("x")
    names = list_references()
    assert sorted(names) == ["marvin", "strong-bad"]


def test_remove_reference_deletes_both(tmp_path, monkeypatch):
    monkeypatch.setattr("claude_code_voice_cloner.registry.DEFAULT_REGISTRY", tmp_path)
    (tmp_path / "marvin.wav").write_bytes(b"x")
    (tmp_path / "marvin.json").write_text("{}")
    remove_reference("marvin")
    assert not (tmp_path / "marvin.wav").exists()
    assert not (tmp_path / "marvin.json").exists()
