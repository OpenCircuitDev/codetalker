"""Phase 26 — treatment dispatch tests."""
from __future__ import annotations

from claude_code_talker.markup.forms import Treatment
from claude_code_talker.markup.recognizers import Span
from claude_code_talker.markup.treatment import apply_treatment


def test_apply_skip_returns_none():
    span = Span("code_fence", 0, 5, "```\nx\n```", parsed={"language": "", "line_count": 1})
    assert apply_treatment(span, Treatment("skip"), {}) is None


def test_apply_describe_code_fence():
    span = Span("code_fence", 0, 5, "```py\na\nb\nc\n```", parsed={"language": "py", "line_count": 3})
    out = apply_treatment(span, Treatment("describe"), {})
    assert "code" in out.lower()
    assert "3" in out or "three" in out.lower()


def test_apply_inline_code_identifier_only_keeps_identifier():
    span = Span("inline_code", 0, 8, "`foo_bar`", parsed={"is_identifier": True})
    out = apply_treatment(span, Treatment("identifier_only"), {})
    assert "foo_bar" in out


def test_apply_inline_code_identifier_only_drops_non_identifier():
    span = Span("inline_code", 0, 8, "`not code`", parsed={"is_identifier": False})
    assert apply_treatment(span, Treatment("identifier_only"), {}) == ""


def test_apply_file_path_filename():
    span = Span("file_path", 0, 0, "src/foo/bar.py:42", parsed={"path": "src/foo/bar.py:42"})
    out = apply_treatment(span, Treatment("filename"), {})
    assert "bar.py" in out


def test_apply_long_numeral_describe():
    span = Span("long_numeral", 0, 0, "1234567")
    out = apply_treatment(span, Treatment("describe"), {})
    assert "long" in out.lower() or "number" in out.lower()


def test_apply_todo_update_count_only():
    span = Span("todo_update", 0, 0, "", parsed={"completed": 3, "in_progress": 1, "pending": 2, "todos": []})
    out = apply_treatment(span, Treatment("count_only"), {})
    assert "3" in out and "1" in out


def test_apply_unknown_kind_returns_none():
    span = Span("code_fence", 0, 5, "```\nx\n```", parsed={"language": "", "line_count": 1})
    assert apply_treatment(span, Treatment("unknown"), {}) is None
