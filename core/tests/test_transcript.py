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
