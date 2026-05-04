"""Tests for transcript parsing."""
import json
from pathlib import Path
from claude_code_talker.transcript import collect_turn, is_real_user_message, recent_assistant_prose, strip_urls


FIXTURES = Path(__file__).parent / "fixtures"
TRANSCRIPT = FIXTURES / "synthetic_turn.jsonl"


def test_is_real_user_message_text():
    e = {"type": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}
    assert is_real_user_message(e) is True


def test_is_real_user_message_tool_result_is_not():
    e = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}
    assert is_real_user_message(e) is False


def test_is_real_user_message_string_content():
    e = {"type": "user", "message": {"content": "hi"}}
    assert is_real_user_message(e) is True


def test_collect_turn_returns_three_lists():
    prose, tool_uses, todos = collect_turn(str(TRANSCRIPT))
    assert isinstance(prose, list)
    assert isinstance(tool_uses, list)
    assert isinstance(todos, list) or todos is None


def test_collect_turn_finds_all_prose_entries():
    prose, _, _ = collect_turn(str(TRANSCRIPT))
    assert len(prose) == 3
    assert "Resuming after compaction" in prose[0]
    assert "Smoking gun found" in prose[1]
    assert "ROOT CAUSE" in prose[2]


def test_collect_turn_finds_all_tool_uses():
    _, tool_uses, _ = collect_turn(str(TRANSCRIPT))
    names = [tu["name"] for tu in tool_uses]
    assert names == ["TodoWrite", "Read", "Edit"]


def test_collect_turn_extracts_todos_from_todowrite():
    _, _, todos = collect_turn(str(TRANSCRIPT))
    assert todos is not None
    assert len(todos) == 3
    assert {t["status"] for t in todos} == {"completed", "in_progress", "pending"}


def test_collect_turn_missing_file_returns_empty():
    prose, tool_uses, todos = collect_turn("/nonexistent/path.jsonl")
    assert prose == []
    assert tool_uses == []
    assert todos is None


# ---------------------------------------------------------------------------
# Tests for recent_assistant_prose
# ---------------------------------------------------------------------------

def _write_transcript(p: Path, entries: list) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def test_returns_empty_when_session_id_empty():
    assert recent_assistant_prose("", catalog=None) == []


def test_returns_empty_when_catalog_none():
    assert recent_assistant_prose("sess-A", catalog=None) == []


def test_returns_empty_when_catalog_has_no_entry():
    class FakeCatalog:
        def get(self, sid):
            return None
    assert recent_assistant_prose("sess-A", catalog=FakeCatalog()) == []


def test_returns_assistant_prose_in_order(tmp_path):
    transcript = tmp_path / "sess.jsonl"
    _write_transcript(transcript, [
        {"type": "user", "message": {"content": "do the thing"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Starting on the menu refactor."},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit"},
            {"type": "text", "text": "Edited Menu.tsx to add multi-select."},
        ]}},
    ])
    class FakeEntry:
        transcript_path = transcript
    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()
    out = recent_assistant_prose("any", catalog=FakeCatalog(), max_messages=5)
    assert len(out) == 2
    assert "menu refactor" in out[0]
    assert "multi-select" in out[1]


def test_caps_to_max_messages(tmp_path):
    transcript = tmp_path / "sess.jsonl"
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": f"Message {i}"},
        ]}}
        for i in range(10)
    ]
    _write_transcript(transcript, entries)
    class FakeEntry:
        transcript_path = transcript
    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()
    out = recent_assistant_prose("any", catalog=FakeCatalog(), max_messages=3)
    assert len(out) == 3
    # Last 3, oldest-first within the window
    assert out == ["Message 7", "Message 8", "Message 9"]


def test_truncates_per_message(tmp_path):
    transcript = tmp_path / "sess.jsonl"
    long_text = "x" * 5000
    _write_transcript(transcript, [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": long_text},
        ]}},
    ])
    class FakeEntry:
        transcript_path = transcript
    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()
    out = recent_assistant_prose("any", catalog=FakeCatalog(),
                                 max_messages=1, max_chars_per_message=200)
    assert len(out[0]) <= 200


def test_skips_ide_injected_wrapper_prefixes(tmp_path):
    """If a transcript line starts with a known IDE-injected wrapper prefix
    (e.g. system reminders bleeding through), it should be skipped."""
    transcript = tmp_path / "sess.jsonl"
    _write_transcript(transcript, [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "<system-reminder>internal goo</system-reminder>"},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Real reasoning here."},
        ]}},
    ])
    class FakeEntry:
        transcript_path = transcript
    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()
    out = recent_assistant_prose("any", catalog=FakeCatalog(), max_messages=5)
    # The system-reminder line should be filtered; only the real reasoning remains.
    assert len(out) == 1
    assert "Real reasoning" in out[0]


def test_handles_corrupted_transcript_lines(tmp_path):
    transcript = tmp_path / "sess.jsonl"
    transcript.write_text(
        "not json\n" +
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "good message"},
        ]}}) + "\n" +
        "{invalid\n",
        encoding="utf-8",
    )
    class FakeEntry:
        transcript_path = transcript
    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()
    out = recent_assistant_prose("any", catalog=FakeCatalog(), max_messages=5)
    assert len(out) == 1
    assert "good message" in out[0]


# ---------------------------------------------------------------------------
# Tests for strip_urls (Phase 13.7d)
# ---------------------------------------------------------------------------

def test_strip_urls_replaces_https():
    assert strip_urls("see https://github.com/foo/bar for details") == "see [link] for details"


def test_strip_urls_replaces_http():
    assert strip_urls("the page http://example.com/x lives") == "the page [link] lives"


def test_strip_urls_replaces_bare_www():
    assert strip_urls("visit www.python.org/docs") == "visit [link]"


def test_strip_urls_handles_multiple():
    out = strip_urls("https://a.com and https://b.com both work")
    assert out == "[link] and [link] both work"


def test_strip_urls_passthrough_when_no_url():
    assert strip_urls("plain text only") == "plain text only"


def test_strip_urls_does_not_match_version_numbers():
    """Dotted tokens like '1.2.3' must NOT be matched — they lack http:// or www."""
    assert strip_urls("version 1.2.3 released") == "version 1.2.3 released"


def test_strip_urls_handles_empty_string():
    assert strip_urls("") == ""


def test_strip_urls_handles_none_gracefully():
    # strip_urls guards against falsy input
    result = strip_urls(None)  # type: ignore[arg-type]
    assert result is None


def test_recent_assistant_prose_strips_urls(tmp_path):
    """Returned prose lines must have URLs replaced before narrator sees them."""
    transcript = tmp_path / "sess.jsonl"
    transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Filed at https://github.com/foo/bar/issues/123"},
    ]}}) + "\n", encoding="utf-8")

    class FakeEntry:
        transcript_path = transcript

    class FakeCatalog:
        def get(self, sid):
            return FakeEntry()

    out = recent_assistant_prose("any", catalog=FakeCatalog(), max_messages=5)
    assert len(out) == 1
    assert "https" not in out[0]
    assert "[link]" in out[0]


# ---------------------------------------------------------------------------
# Phase 14b: extended URL-stripping for markdown links + file paths
# ---------------------------------------------------------------------------

def test_strip_markdown_link_keeps_label_drops_url():
    from claude_code_talker.transcript import strip_urls
    assert strip_urls("see [the docs](https://example.com/x) for details") \
        == "see the docs for details"


def test_strip_markdown_link_with_local_path():
    from claude_code_talker.transcript import strip_urls
    assert strip_urls("Edit [live.py](modes/live.py) to fix the bug") \
        == "Edit live.py to fix the bug"


def test_strip_bare_posix_path_to_basename():
    from claude_code_talker.transcript import strip_urls
    assert strip_urls("editing src/auth/login.py now") \
        == "editing login.py now"


def test_strip_bare_windows_path_to_basename():
    from claude_code_talker.transcript import strip_urls
    out = strip_urls(r"see C:/Users/brand/file.ts for the change")
    assert "C:" not in out
    assert "file.ts" in out


def test_strip_does_not_touch_plain_words():
    from claude_code_talker.transcript import strip_urls
    assert strip_urls("version 1.2.3 of the library") == "version 1.2.3 of the library"
    assert strip_urls("plain words only") == "plain words only"


def test_strip_handles_combined_markdown_and_bare_url():
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("Filed [issue](https://github.com/foo/bar/issues/1) plus see https://other.com")
    assert "github.com" not in out
    assert "other.com" not in out
    assert "[link]" in out
    assert "issue" in out


# ---------------------------------------------------------------------------
# Phase 13.8 R1: backtick code-span normalizer
# ---------------------------------------------------------------------------

def test_backtick_snake_case_underscores_to_spaces():
    """snake_case inside backticks → underscores replaced with spaces, backticks stripped."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("calling `probe_actors_with_mount` now")
    assert "`" not in out
    assert "probe actors with mount" in out


def test_backtick_path_reduces_to_basename():
    """Paths inside backticks → only the basename, backticks stripped."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("see `src/modes/live.py` for details")
    assert "`" not in out
    assert "live.py" in out
    assert "src" not in out


def test_backtick_camelcase_preserved():
    """CamelCase inside backticks → backticks stripped, word left intact."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("using `AudioStreamer` class here")
    assert "`" not in out
    assert "AudioStreamer" in out


def test_backtick_multiple_spans_in_one_string():
    """Multiple backtick spans in one string — all stripped and normalised."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("call `strip_urls` then `emit_chunk`")
    assert "`" not in out
    assert "strip urls" in out
    assert "emit chunk" in out


def test_backtick_passthrough_when_no_backticks():
    """Strings without backticks pass through unchanged."""
    from claude_code_talker.transcript import strip_urls
    text = "plain text with no backticks"
    assert strip_urls(text) == text


# ---------------------------------------------------------------------------
# Phase 13.8 R2: long-numeric token stripper
# ---------------------------------------------------------------------------

def test_long_numeric_7plus_digits_replaced():
    """Standalone 7-digit numeric token → 'a long number'."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("tmp dir 1777879 here")
    assert "1777879" not in out
    assert "a long number" in out


def test_long_numeric_6_digits_not_replaced():
    """6-digit numeric NOT replaced — too short to be a timestamp."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("version 123456 released")
    assert "123456" in out
    assert "a long number" not in out


def test_long_numeric_inside_basename_replaced():
    """Long numeric inside a basename (e.g. win071_v3_vision_1777879631) → replaced."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("file `win071_v3_vision_1777879631.py` done")
    assert "1777879631" not in out
    assert "a long number" in out


def test_long_numeric_multiple_in_string():
    """Two standalone long-numeric tokens both replaced."""
    from claude_code_talker.transcript import strip_urls
    out = strip_urls("ids 1234567890 and 9876543210 seen")
    assert "1234567890" not in out
    assert "9876543210" not in out
    assert out.count("a long number") == 2
