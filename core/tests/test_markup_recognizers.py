"""Phase 26 — markup.recognizers tests (prose-only forms)."""
from __future__ import annotations

from claude_code_talker.markup.recognizers import (
    Span,
    detect_audible_block,
    detect_code_fence,
    detect_file_path,
    detect_inline_code,
    detect_long_numeral,
    detect_plan_block,
    detect_system_reminder,
)


def test_detect_code_fence_finds_triple_backticks():
    text = "before\n```python\nprint('x')\nprint('y')\n```\nafter"
    spans = detect_code_fence(text)
    assert len(spans) == 1
    assert spans[0].form == "code_fence"
    assert spans[0].parsed["language"] == "python"
    assert spans[0].parsed["line_count"] == 2


def test_detect_code_fence_no_language():
    text = "```\nfoo\n```"
    spans = detect_code_fence(text)
    assert spans[0].parsed["language"] == ""


def test_detect_inline_code_marks_identifier():
    text = "Call `foo_bar` then `not an identifier`."
    spans = detect_inline_code(text)
    assert len(spans) == 2
    assert spans[0].parsed["is_identifier"] is True
    assert spans[1].parsed["is_identifier"] is False


def test_detect_inline_code_dotted_identifier():
    text = "Use `module.func` directly."
    spans = detect_inline_code(text)
    assert spans[0].parsed["is_identifier"] is True


def test_detect_system_reminder_html_form():
    text = "<system-reminder>do this</system-reminder> rest"
    spans = detect_system_reminder(text)
    assert len(spans) == 1
    assert spans[0].form == "system_reminder"


def test_detect_file_path_basic():
    text = "Open `src/foo/bar.py:42` to see it."
    spans = detect_file_path(text)
    assert any(s.form == "file_path" for s in spans)


def test_detect_long_numeral_seven_digits():
    text = "Order 1234567 was placed."
    spans = detect_long_numeral(text)
    assert len(spans) == 1
    assert spans[0].text == "1234567"


def test_detect_long_numeral_ignores_short():
    text = "Order 12345 was placed."
    assert detect_long_numeral(text) == []


def test_detect_plan_block_header():
    text = "Intro\n\n## Plan\nstep 1\nstep 2"
    spans = detect_plan_block(text)
    assert len(spans) == 1


def test_detect_audible_block_passthrough():
    text = "## Audible Summary\nHello there.\n\nMore prose."
    spans = detect_audible_block(text)
    assert len(spans) == 1
    assert "Hello there" in spans[0].text
