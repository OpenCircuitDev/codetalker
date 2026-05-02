"""Tests for config loading and merging."""
from pathlib import Path
import pytest
from claude_tts.config import deep_merge, load_global_config


FIXTURES = Path(__file__).parent / "fixtures"


def test_deep_merge_overrides_leaves():
    a = {"x": 1, "y": {"z": 2}}
    b = {"y": {"z": 3, "w": 4}}
    assert deep_merge(a, b) == {"x": 1, "y": {"z": 3, "w": 4}}


def test_deep_merge_replaces_lists():
    a = {"items": [1, 2]}
    b = {"items": [3]}
    assert deep_merge(a, b) == {"items": [3]}


def test_deep_merge_handles_none_override():
    a = {"x": 1}
    assert deep_merge(a, None) == {"x": 1}
    assert deep_merge(a, {}) == {"x": 1}


def test_load_global_config_applies_preset(tmp_path):
    cfg_path = tmp_path / "tts_config.yaml"
    cfg_path.write_text("preset: brief\nvoice:\n  model: foo\n")
    cfg = load_global_config(cfg_path)
    assert cfg["voice"]["model"] == "foo"
    assert cfg["text"]["max_chars"] == 1000  # from brief preset
    assert cfg["content_filter"]["mode"] == "blacklist"


def test_load_global_config_user_wins_over_preset(tmp_path):
    cfg_path = tmp_path / "tts_config.yaml"
    cfg_path.write_text("preset: brief\ntext:\n  max_chars: 500\n")
    cfg = load_global_config(cfg_path)
    assert cfg["text"]["max_chars"] == 500  # user override beats preset 1000


def test_load_global_config_missing_file_returns_defaults(tmp_path):
    cfg = load_global_config(tmp_path / "nonexistent.yaml")
    assert cfg.get("enabled", True) is True
