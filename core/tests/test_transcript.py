"""Tests for transcript parsing."""
from pathlib import Path
from claude_tts.transcript import collect_turn, is_real_user_message


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
