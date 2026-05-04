"""Tests for event_render.summarize_tool_input / summarize_tool_response."""
import pytest

from claude_code_talker.event_render import (
    summarize_tool_input, summarize_tool_response,
)


def test_summarize_input_edit_extracts_file_path():
    raw = str({"file_path": "src/auth.py", "old_string": "foo", "new_string": "bar"})
    out = summarize_tool_input("Edit", raw)
    assert "auth.py" in out
    assert "old_string" not in out


def test_summarize_input_write_extracts_file_path():
    raw = str({"file_path": "/abs/path/spec.md", "content": "huge body of text" * 200})
    out = summarize_tool_input("Write", raw)
    assert "spec.md" in out
    assert "huge body" not in out


def test_summarize_input_bash_extracts_command():
    raw = str({"command": "npm run build && pytest"})
    out = summarize_tool_input("Bash", raw)
    assert "npm run build" in out


def test_summarize_input_bash_truncates_long_command():
    raw = str({"command": "echo " + "x" * 500})
    out = summarize_tool_input("Bash", raw)
    assert len(out) <= 90  # truncated


def test_summarize_input_grep_extracts_pattern():
    raw = str({"pattern": "TODO|FIXME", "path": "src/"})
    out = summarize_tool_input("Grep", raw)
    assert "TODO|FIXME" in out


def test_summarize_input_todowrite_counts_in_progress():
    raw = str({"todos": [
        {"content": "a", "status": "in_progress", "activeForm": "doing a"},
        {"content": "b", "status": "completed", "activeForm": "did b"},
        {"content": "c", "status": "in_progress", "activeForm": "doing c"},
    ]})
    out = summarize_tool_input("TodoWrite", raw)
    assert "in_progress" in out or "in progress" in out
    # Optionally mention count
    assert "2" in out or "two" in out


def test_summarize_input_unknown_tool_uses_truncated_raw():
    raw = "{'something': 'else'}"
    out = summarize_tool_input("MysteryTool", raw)
    assert len(out) <= 80
    assert out  # nonempty


def test_summarize_input_invalid_dict_string_falls_back_to_truncation():
    raw = "not a dict at all just a string with no braces"
    out = summarize_tool_input("Edit", raw)
    assert len(out) <= 80


def test_summarize_input_empty_returns_empty():
    assert summarize_tool_input("Edit", "") == ""
    assert summarize_tool_input("Bash", "") == ""


def test_summarize_response_bash_includes_stdout_when_short():
    raw = str({"stdout": "5 tests passed", "exit_code": 0})
    out = summarize_tool_response("Bash", raw, success=True)
    assert "5 tests passed" in out


def test_summarize_response_bash_truncates_long_stdout():
    # Cap was raised from 80 → 200 in Phase 13.9a Task 2
    raw = str({"stdout": "x" * 1000, "exit_code": 0})
    out = summarize_tool_response("Bash", raw, success=True)
    assert len(out) <= 200


def test_summarize_response_failure_surfaces_error():
    raw = str({"error": "permission denied"})
    out = summarize_tool_response("Bash", raw, success=False)
    assert "permission denied" in out.lower() or "FAILED" in out


def test_summarize_response_edit_just_ok():
    raw = str({"new_lines": 5})
    out = summarize_tool_response("Edit", raw, success=True)
    assert out  # nonempty
    # Edit doesn't need to surface response details


def test_summarize_response_empty_returns_minimal_status():
    out = summarize_tool_response("Edit", "", success=True)
    assert out  # something meaningful (probably "ok")
    out_fail = summarize_tool_response("Edit", "", success=False)
    assert "FAIL" in out_fail.upper() or "fail" in out_fail.lower()


# ---------------------------------------------------------------------------
# URL-strip tests (Phase 13.7d)
# ---------------------------------------------------------------------------

def test_summarize_tool_input_bash_strips_urls():
    raw = str({"command": "curl https://api.example.com/data > out.json"})
    out = summarize_tool_input("Bash", raw)
    assert "https" not in out
    assert "[link]" in out


def test_summarize_tool_input_webfetch_returns_domain_only():
    raw = str({"url": "https://github.com/owner/repo/blob/main/path/to/file.py"})
    out = summarize_tool_input("WebFetch", raw)
    assert "/blob/" not in out   # path stripped
    assert "github.com" in out


def test_summarize_tool_input_webfetch_bare_or_empty_url():
    # If url is missing / empty, fall back to "[link]"
    raw = str({"url": ""})
    out = summarize_tool_input("WebFetch", raw)
    assert out == "[link]"


def test_summarize_tool_input_bash_no_url_unchanged():
    raw = str({"command": "pytest core/tests --tb=short"})
    out = summarize_tool_input("Bash", raw)
    assert "pytest" in out
    assert "[link]" not in out


# ---------------------------------------------------------------------------
# Phase 13.9a Task 2 — Bash response enrichment
# ---------------------------------------------------------------------------

def test_summarize_response_bash_truncates_at_200():
    """Long stdout must be capped at ≤200 chars (raised from 80)."""
    long_stdout = "x" * 500
    raw = str({"stdout": long_stdout, "exit_code": 0})
    out = summarize_tool_response("Bash", raw, success=True)
    assert len(out) <= 200


def test_summarize_response_bash_detects_passed():
    """stdout containing 'tests passed' should prepend ✓."""
    raw = str({"stdout": "5 tests passed", "exit_code": 0})
    out = summarize_tool_response("Bash", raw, success=True)
    assert out.startswith("✓")


def test_summarize_response_bash_detects_failed():
    """stdout containing 'FAILED:' should prepend ✗."""
    raw = str({"stdout": "FAILED: test_foo", "exit_code": 1})
    out = summarize_tool_response("Bash", raw, success=True)
    assert out.startswith("✗")


def test_summarize_response_bash_includes_exit_code_on_failure():
    """success=False + exit_code in response dict → text starts with '(exit N)'."""
    raw = str({"stdout": "something went wrong", "exit_code": 1})
    out = summarize_tool_response("Bash", raw, success=False)
    assert out.startswith("(exit 1)")


def test_summarize_response_bash_built_successfully_detected():
    """'Built successfully' in stdout should prepend ✓ (case-insensitive)."""
    raw = str({"stdout": "Built successfully in 3.2s", "exit_code": 0})
    out = summarize_tool_response("Bash", raw, success=True)
    assert out.startswith("✓")
