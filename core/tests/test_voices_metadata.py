"""Tests for voices.metadata — sidecar JSON read/write."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from claude_code_talker.voices.metadata import (
    VoiceMetadata,
    metadata_path,
    new_metadata,
    read_metadata,
    update_metadata,
    write_metadata,
)


# ---------------------------------------------------------------------------
# metadata_path
# ---------------------------------------------------------------------------

def test_metadata_path_returns_json_name(tmp_path):
    p = metadata_path(tmp_path, "riley")
    assert p == tmp_path / "riley.json"


# ---------------------------------------------------------------------------
# write_metadata + read_metadata round-trip
# ---------------------------------------------------------------------------

def test_write_read_roundtrip(tmp_path):
    meta = VoiceMetadata(name="riley", source_path="/videos/interview.mp4",
                         source_type="video", clip_start=1.5, clip_end=7.5,
                         created_at=1234567890.0)
    write_metadata(tmp_path, meta)
    result = read_metadata(tmp_path, "riley")
    assert result is not None
    assert result.name == "riley"
    assert result.source_path == "/videos/interview.mp4"
    assert result.source_type == "video"
    assert result.clip_start == 1.5
    assert result.clip_end == 7.5
    assert result.created_at == 1234567890.0


def test_write_creates_directory(tmp_path):
    nested = tmp_path / "deep" / "refs"
    meta = VoiceMetadata(name="voice1")
    write_metadata(nested, meta)
    assert (nested / "voice1.json").exists()


# ---------------------------------------------------------------------------
# read_metadata — missing / corrupted
# ---------------------------------------------------------------------------

def test_read_metadata_missing_returns_none(tmp_path):
    result = read_metadata(tmp_path, "nonexistent")
    assert result is None


def test_read_metadata_corrupted_json_returns_none(tmp_path):
    (tmp_path / "broken.json").write_text("NOT { valid json", encoding="utf-8")
    result = read_metadata(tmp_path, "broken")
    assert result is None


def test_read_metadata_non_dict_json_returns_none(tmp_path):
    (tmp_path / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
    result = read_metadata(tmp_path, "list")
    assert result is None


# ---------------------------------------------------------------------------
# Unknown fields dropped, name always from filename
# ---------------------------------------------------------------------------

def test_unknown_fields_are_dropped(tmp_path):
    data = {
        "name": "IGNORED_NAME",
        "source_path": "/some/path.wav",
        "unknown_future_field": "should_be_dropped",
        "another_unknown": 999,
    }
    (tmp_path / "voice.json").write_text(json.dumps(data), encoding="utf-8")
    meta = read_metadata(tmp_path, "voice")
    assert meta is not None
    # name must come from the filename, not the JSON content
    assert meta.name == "voice"
    assert meta.source_path == "/some/path.wav"
    assert not hasattr(meta, "unknown_future_field")


# ---------------------------------------------------------------------------
# Atomic write — no .tmp file left behind on success
# ---------------------------------------------------------------------------

def test_atomic_write_no_tmp_leftover(tmp_path):
    meta = VoiceMetadata(name="clean")
    write_metadata(tmp_path, meta)
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"unexpected .tmp files: {tmp_files}"


# ---------------------------------------------------------------------------
# update_metadata
# ---------------------------------------------------------------------------

def test_update_metadata_creates_fresh_if_none(tmp_path):
    result = update_metadata(tmp_path, "new_voice", source_path="/foo.wav")
    assert result.name == "new_voice"
    assert result.source_path == "/foo.wav"
    # Sidecar was written
    assert (tmp_path / "new_voice.json").exists()


def test_update_metadata_modifies_existing(tmp_path):
    # Write an initial sidecar
    meta = VoiceMetadata(name="existing", source_path="/original.wav", clip_start=0.0)
    write_metadata(tmp_path, meta)

    # Modify a field
    updated = update_metadata(tmp_path, "existing", clip_start=2.5, clip_end=8.0)
    assert updated.clip_start == 2.5
    assert updated.clip_end == 8.0
    # Original field preserved
    assert updated.source_path == "/original.wav"


def test_update_metadata_ignores_unknown_keys(tmp_path):
    """Unknown keys passed to update_metadata should not raise."""
    result = update_metadata(tmp_path, "voice2", unknown_key="oops")
    assert result.name == "voice2"


# ---------------------------------------------------------------------------
# new_metadata
# ---------------------------------------------------------------------------

def test_new_metadata_fills_created_at(monkeypatch):
    monkeypatch.setattr(
        "claude_code_talker.voices.metadata.time",
        type("FakeTime", (), {"time": staticmethod(lambda: 9999.0)})(),
    )
    meta = new_metadata("riley", source_path="/vid.mp4", source_type="video",
                        clip_start=1.0, clip_end=5.0)
    assert meta.created_at == 9999.0
    assert meta.name == "riley"
    assert meta.source_type == "video"
