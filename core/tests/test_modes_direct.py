"""Tests for Mode A: direct read."""
from claude_code_talker.modes.direct import DirectMode


def _basic_cfg():
    return {
        "elements": {
            "heading": True, "code_block": False, "inline_code": True,
            "link": True, "list": True, "blockquote": True,
            "emphasis": True, "table": False, "insight_block": False,
        },
        "urls": {"shorten_to_host": True},
        "paths": {"handling": "filename"},
        "content_filter": {"mode": "off"},
        "text": {"max_chars": 5000, "boundary_snap": "sentence", "truncation_marker": "..."},
        "synopsis": {"enabled": False},
    }


def test_direct_speaks_plain_prose():
    mode = DirectMode()
    cfg = _basic_cfg()
    result = mode.build(prose_entries=["Hello world."], tool_uses=[], todos=None, cfg=cfg)
    assert result == "Hello world."


def test_direct_strips_code_blocks():
    mode = DirectMode()
    cfg = _basic_cfg()
    text = "Before.\n\n```python\nprint('hi')\n```\n\nAfter."
    result = mode.build(prose_entries=[text], tool_uses=[], todos=None, cfg=cfg)
    assert "print" not in result
    assert "code block omitted" in result


def test_direct_keeps_inline_code():
    mode = DirectMode()
    cfg = _basic_cfg()
    result = mode.build(prose_entries=["The `var` is set."], tool_uses=[], todos=None, cfg=cfg)
    assert "var" in result


def test_direct_shortens_url():
    mode = DirectMode()
    cfg = _basic_cfg()
    result = mode.build(
        prose_entries=["See https://www.example.com/foo for details."],
        tool_uses=[], todos=None, cfg=cfg
    )
    assert "example.com" in result
    assert "https" not in result
    assert "/foo" not in result


def test_direct_shortens_path_to_filename():
    mode = DirectMode()
    cfg = _basic_cfg()
    result = mode.build(
        prose_entries=["Open c:/Users/foo/bar.py to fix it."],
        tool_uses=[], todos=None, cfg=cfg
    )
    assert "bar.py" in result
    assert "c:/Users" not in result


def test_direct_skips_tool_descriptor_paragraph_when_blacklist():
    mode = DirectMode()
    cfg = _basic_cfg()
    cfg["content_filter"]["mode"] = "blacklist"
    cfg["content_filter"]["skip_paragraph_patterns"] = [r"^Read\s+\S"]
    text = "Read c:/foo/bar.py\n\nThe real prose follows."
    result = mode.build(prose_entries=[text], tool_uses=[], todos=None, cfg=cfg)
    assert "real prose" in result
    assert "Read c:" not in result


def test_direct_truncates_at_sentence_boundary():
    mode = DirectMode()
    cfg = _basic_cfg()
    cfg["text"]["max_chars"] = 40
    cfg["text"]["boundary_snap"] = "sentence"
    text = "First sentence. Second sentence. Third sentence."  # 48 chars
    result = mode.build(prose_entries=[text], tool_uses=[], todos=None, cfg=cfg)
    assert result.endswith("...")
    assert "Third" not in result
    # Sentence-snap should keep "Second sentence." in the result
    assert "Second sentence" in result
