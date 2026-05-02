"""Tests for preset bundle definitions."""
from claude_code_talker.presets import PRESETS, get_preset


def test_known_presets_exist():
    expected = {"monitor", "synopsis", "conclusions", "brief", "verbose"}
    assert expected.issubset(PRESETS.keys())


def test_get_preset_returns_dict():
    p = get_preset("monitor")
    assert isinstance(p, dict)
    assert "text" in p
    assert "content_filter" in p


def test_get_preset_unknown_returns_empty():
    assert get_preset("nonsense") == {}


def test_monitor_preset_uses_paragraph_snap():
    p = get_preset("monitor")
    assert p["text"]["boundary_snap"] == "paragraph"
    assert p["text"]["max_chars"] == 3000


def test_brief_preset_uses_blacklist_filter():
    p = get_preset("brief")
    assert p["content_filter"]["mode"] == "blacklist"
    assert p["text"]["max_chars"] == 1000


def test_synopsis_preset_suppresses_prose():
    p = get_preset("synopsis")
    assert p["content_filter"]["mode"] == "suppress"
