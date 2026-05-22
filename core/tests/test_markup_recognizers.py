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


def test_detect_todo_update_from_tool_event():
    from claude_code_talker.markup.recognizers import detect_todo_update
    event = {
        "kind": "tool_use",
        "name": "TodoWrite",
        "input": {"todos": [{"content": "a", "status": "completed"}, {"content": "b", "status": "in_progress"}]},
    }
    spans = detect_todo_update(event)
    assert len(spans) == 1
    assert spans[0].parsed["completed"] == 1
    assert spans[0].parsed["in_progress"] == 1


def test_detect_todo_update_ignores_non_todo_events():
    from claude_code_talker.markup.recognizers import detect_todo_update
    event = {"kind": "tool_use", "name": "Bash", "input": {}}
    assert detect_todo_update(event) == []


def test_detect_tool_output_post_event():
    from claude_code_talker.markup.recognizers import detect_tool_output
    event = {
        "kind": "post_tool",
        "name": "Bash",
        "exit_code": 0,
        "stdout": "line1\nline2\nline3\n",
    }
    spans = detect_tool_output(event)
    assert len(spans) == 1
    assert spans[0].parsed["tool_name"] == "Bash"
    assert spans[0].parsed["line_count"] == 3
    assert spans[0].parsed["exit_code"] == 0


def test_detect_subagent_dispatch_pre_and_post():
    from claude_code_talker.markup.recognizers import detect_subagent_dispatch
    pre = {"kind": "tool_use", "name": "Task", "id": "abc", "input": {"subagent_type": "Explore"}}
    post = {"kind": "post_tool", "name": "Task", "id": "abc"}
    assert detect_subagent_dispatch(pre)[0].parsed["phase"] == "pre"
    assert detect_subagent_dispatch(post)[0].parsed["phase"] == "post"


# ============================================================================
# IP Address recognition tests
# ============================================================================

def test_detect_ip_address_basic():
    from claude_code_talker.markup.recognizers import detect_ip_address
    text = "Connect to 192.168.1.132 to debug."
    spans = detect_ip_address(text)
    assert len(spans) == 1
    assert spans[0].form == "ip_address"
    assert spans[0].parsed["host"] == "192.168.1.132"
    assert spans[0].parsed["port"] is None


def test_detect_ip_address_with_port():
    from claude_code_talker.markup.recognizers import detect_ip_address
    text = "Server at 192.168.1.132:40653 is running."
    spans = detect_ip_address(text)
    assert len(spans) == 1
    assert spans[0].parsed["host"] == "192.168.1.132"
    assert spans[0].parsed["port"] == 40653


def test_detect_ip_address_localhost():
    from claude_code_talker.markup.recognizers import detect_ip_address
    text = "Bind to 127.0.0.1 for localhost."
    spans = detect_ip_address(text)
    assert len(spans) == 1
    assert spans[0].parsed["host"] == "127.0.0.1"


def test_detect_ip_address_rejects_invalid_octets():
    from claude_code_talker.markup.recognizers import detect_ip_address
    text = "Invalid IP 999.999.999.999 should not match."
    spans = detect_ip_address(text)
    assert len(spans) == 0


def test_detect_ip_address_multiple_in_text():
    from claude_code_talker.markup.recognizers import detect_ip_address
    text = "Primary: 192.168.1.1, Backup: 10.0.0.1"
    spans = detect_ip_address(text)
    assert len(spans) == 2


# ============================================================================
# ISO Timestamp recognition tests
# ============================================================================

def test_detect_iso_timestamp_date_only():
    from claude_code_talker.markup.recognizers import detect_iso_timestamp
    text = "Created on 2026-05-21 for the project."
    spans = detect_iso_timestamp(text)
    assert len(spans) == 1
    assert spans[0].form == "iso_timestamp"
    assert spans[0].text == "2026-05-21"


def test_detect_iso_timestamp_with_time():
    from claude_code_talker.markup.recognizers import detect_iso_timestamp
    text = "Logged at 2026-05-21T15:08:00 UTC."
    spans = detect_iso_timestamp(text)
    assert len(spans) == 1
    assert spans[0].text == "2026-05-21T15:08:00"


def test_detect_iso_timestamp_with_z_suffix():
    from claude_code_talker.markup.recognizers import detect_iso_timestamp
    text = "Timestamp: 2026-05-21T15:08:00Z"
    spans = detect_iso_timestamp(text)
    assert len(spans) == 1
    assert spans[0].text == "2026-05-21T15:08:00Z"


def test_detect_iso_timestamp_with_offset():
    from claude_code_talker.markup.recognizers import detect_iso_timestamp
    text = "Time: 2026-05-21T15:08:00-06:00"
    spans = detect_iso_timestamp(text)
    assert len(spans) == 1
    assert spans[0].text == "2026-05-21T15:08:00-06:00"


def test_detect_iso_timestamp_rejects_invalid_date():
    from claude_code_talker.markup.recognizers import detect_iso_timestamp
    text = "Invalid: 999-99-99 should not match."
    spans = detect_iso_timestamp(text)
    assert len(spans) == 0


def test_detect_iso_timestamp_rejects_invalid_month():
    from claude_code_talker.markup.recognizers import detect_iso_timestamp
    text = "Invalid: 2026-13-01 should not match."
    spans = detect_iso_timestamp(text)
    assert len(spans) == 0


# ============================================================================
# Currency Amount recognition tests
# ============================================================================

def test_detect_currency_amount_plain():
    from claude_code_talker.markup.recognizers import detect_currency_amount
    text = "Cost is $10 per item."
    spans = detect_currency_amount(text)
    assert len(spans) == 1
    assert spans[0].form == "currency_amount"
    assert "$10" in spans[0].text


def test_detect_currency_amount_with_cents():
    from claude_code_talker.markup.recognizers import detect_currency_amount
    text = "Price: $1,234.56 total"
    spans = detect_currency_amount(text)
    assert len(spans) == 1
    assert "$1,234.56" in spans[0].text


def test_detect_currency_amount_with_month_suffix():
    from claude_code_talker.markup.recognizers import detect_currency_amount
    text = "Subscription: $10/mo"
    spans = detect_currency_amount(text)
    assert len(spans) == 1
    assert "$10/mo" in spans[0].text


def test_detect_currency_amount_with_year_suffix():
    from claude_code_talker.markup.recognizers import detect_currency_amount
    text = "Annual fee: $100/year"
    spans = detect_currency_amount(text)
    assert len(spans) == 1
    assert "$100/year" in spans[0].text


def test_detect_currency_amount_with_usd_suffix():
    from claude_code_talker.markup.recognizers import detect_currency_amount
    text = "Amount: $50 USD"
    spans = detect_currency_amount(text)
    assert len(spans) == 1
    assert "$50" in spans[0].text


def test_detect_currency_amount_multiple():
    from claude_code_talker.markup.recognizers import detect_currency_amount
    text = "Options: $10/mo or $100/yr"
    spans = detect_currency_amount(text)
    assert len(spans) == 2
