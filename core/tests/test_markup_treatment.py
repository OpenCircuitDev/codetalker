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


# ============================================================================
# IP Address treatment tests
# ============================================================================

def test_apply_ip_address_describe():
    span = Span("ip_address", 0, 0, "192.168.1.132", parsed={"host": "192.168.1.132", "port": None})
    out = apply_treatment(span, Treatment("describe"), {})
    assert "address" in out.lower()


def test_apply_ip_address_describe_with_port():
    span = Span("ip_address", 0, 0, "192.168.1.132:40653", parsed={"host": "192.168.1.132", "port": 40653})
    out = apply_treatment(span, Treatment("describe"), {})
    assert "address" in out.lower()
    assert "40653" in out


def test_apply_ip_address_read():
    span = Span("ip_address", 0, 0, "192.168.1.132", parsed={"host": "192.168.1.132", "port": None})
    out = apply_treatment(span, Treatment("read"), {})
    assert "dot" in out.lower()
    assert "one hundred ninety" in out.lower() or "one hundred" in out.lower()


def test_apply_ip_address_read_with_port():
    span = Span("ip_address", 0, 0, "192.168.1.132:40653", parsed={"host": "192.168.1.132", "port": 40653})
    out = apply_treatment(span, Treatment("read"), {})
    assert "dot" in out.lower()
    assert "port" in out.lower()


# ============================================================================
# ISO Timestamp treatment tests
# ============================================================================

def test_apply_iso_timestamp_describe():
    span = Span("iso_timestamp", 0, 0, "2026-05-21", parsed={"raw": "2026-05-21"})
    out = apply_treatment(span, Treatment("describe"), {})
    assert "timestamp" in out.lower() or "recent" in out.lower()


def test_apply_iso_timestamp_read_date_only():
    span = Span("iso_timestamp", 0, 0, "2026-05-21", parsed={"raw": "2026-05-21"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "may" in out.lower()
    assert "21" in out
    assert "2026" in out


def test_apply_iso_timestamp_read_datetime():
    span = Span("iso_timestamp", 0, 0, "2026-05-21T15:08:00", parsed={"raw": "2026-05-21T15:08:00"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "may" in out.lower()
    assert "21" in out
    assert "2026" in out
    assert "3" in out or "pm" in out.lower()  # 15:00 = 3 PM


def test_apply_iso_timestamp_read_with_z():
    span = Span("iso_timestamp", 0, 0, "2026-05-21T15:08:00Z", parsed={"raw": "2026-05-21T15:08:00Z"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "may" in out.lower()


# ============================================================================
# Currency Amount treatment tests
# ============================================================================

def test_apply_currency_amount_describe():
    span = Span("currency_amount", 0, 0, "$10", parsed={"raw": "$10"})
    out = apply_treatment(span, Treatment("describe"), {})
    assert "amount" in out.lower() or "dollar" in out.lower()


def test_apply_currency_amount_read_plain():
    span = Span("currency_amount", 0, 0, "$10", parsed={"raw": "$10"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "ten" in out.lower()
    assert "dollar" in out.lower()


def test_apply_currency_amount_read_with_cents():
    span = Span("currency_amount", 0, 0, "$10.50", parsed={"raw": "$10.50"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "ten" in out.lower()
    assert "fifty" in out.lower()
    assert "cent" in out.lower()


def test_apply_currency_amount_read_with_thousands():
    span = Span("currency_amount", 0, 0, "$1,234.56", parsed={"raw": "$1,234.56"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "thousand" in out.lower()
    assert "fifty" in out.lower() or "fifty-six" in out.lower()


def test_apply_currency_amount_read_with_mo_suffix():
    span = Span("currency_amount", 0, 0, "$10/mo", parsed={"raw": "$10/mo"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "ten" in out.lower()
    assert "month" in out.lower()


def test_apply_currency_amount_read_with_year_suffix():
    span = Span("currency_amount", 0, 0, "$100/year", parsed={"raw": "$100/year"})
    out = apply_treatment(span, Treatment("read"), {})
    assert "hundred" in out.lower()
    assert "year" in out.lower()


# ============================================================================
# Numeric word conversion tests
# ============================================================================

def test_num_to_words_zero():
    from claude_code_talker.markup.describer import _num_to_words
    assert _num_to_words(0) == "zero"


def test_num_to_words_single_digit():
    from claude_code_talker.markup.describer import _num_to_words
    assert _num_to_words(5) == "five"


def test_num_to_words_teens():
    from claude_code_talker.markup.describer import _num_to_words
    assert _num_to_words(13) == "thirteen"


def test_num_to_words_tens():
    from claude_code_talker.markup.describer import _num_to_words
    assert _num_to_words(42) == "forty two"


def test_num_to_words_hundreds():
    from claude_code_talker.markup.describer import _num_to_words
    assert _num_to_words(567) == "five hundred sixty seven"


def test_num_to_words_thousands():
    from claude_code_talker.markup.describer import _num_to_words
    result = _num_to_words(1234)
    assert "thousand" in result.lower()
    assert "two hundred" in result.lower()
    assert "thirty" in result.lower()
    assert "four" in result.lower()


def test_num_to_words_large_number():
    from claude_code_talker.markup.describer import _num_to_words
    result = _num_to_words(999999)
    assert "thousand" in result.lower()


def test_num_to_words_out_of_range_fallback():
    from claude_code_talker.markup.describer import _num_to_words
    result = _num_to_words(1000000)
    # Should fall back to digit representation
    assert any(c.isdigit() for c in result)
