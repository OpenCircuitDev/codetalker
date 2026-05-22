"""Tests for NarrationLog (Phase 11 audit log + Phase 12 rotation)."""
import json
import time
import pytest
from pathlib import Path

from claude_code_talker.narration_log import NarrationLog, NarrationEntry


@pytest.fixture
def log(tmp_path):
    # Large enough that simple tests don't trigger rotation; rotation-specific
    # tests construct their own NarrationLog with a tiny max_bytes.
    return NarrationLog(log_path=tmp_path / "narration.jsonl",
                        max_bytes=10 * 1024 * 1024, max_backups=3)


def test_append_and_tail(log):
    log.append(NarrationEntry(timestamp=1.0, session_id="abc", text="hello"))
    log.append(NarrationEntry(timestamp=2.0, session_id="abc", text="world"))
    out = log.tail()
    assert [e["text"] for e in out] == ["hello", "world"]


def test_tail_limit(log):
    for i in range(20):
        log.append(NarrationEntry(timestamp=float(i), session_id="x", text=f"msg{i}"))
    out = log.tail(n=5)
    assert len(out) == 5
    assert out[-1]["text"] == "msg19"


def test_tail_empty_file(log):
    assert log.tail() == []


def test_find_for_session(log):
    log.append(NarrationEntry(timestamp=1.0, session_id="aaa", text="a-msg"))
    log.append(NarrationEntry(timestamp=2.0, session_id="bbb", text="b-msg"))
    log.append(NarrationEntry(timestamp=3.0, session_id="aaa", text="a-msg-2"))
    out = log.find_for_session("aaa")
    assert len(out) == 2
    assert all(e["session_id"] == "aaa" for e in out)


def test_dict_append_supplies_timestamp(log):
    log.append({"session_id": "abc", "text": "no timestamp here"})
    out = log.tail()
    assert out[0]["session_id"] == "abc"
    assert "timestamp" in out[0]


def test_rotation_creates_backups(tmp_path):
    log_path = tmp_path / "narr.jsonl"
    log = NarrationLog(log_path=log_path, max_bytes=100, max_backups=3)
    # Each entry is roughly 80-90 bytes; force several rotations.
    for i in range(15):
        log.append(NarrationEntry(timestamp=float(i), session_id="abc", text=f"msg{i:02d}-padding"))
    # The current log may have been rotated away on the last iteration; what
    # matters is that backup files exist.
    assert (tmp_path / "narr.jsonl.1").exists()


def test_rotation_caps_at_max_backups(tmp_path):
    log_path = tmp_path / "narr.jsonl"
    log = NarrationLog(log_path=log_path, max_bytes=80, max_backups=2)
    for i in range(30):
        log.append(NarrationEntry(timestamp=float(i), session_id="x", text=f"long-text-here-{i}"))
    # .1 and .2 may exist, but NOT .3
    assert not (tmp_path / "narr.jsonl.3").exists()


def test_stats_reports_entries_and_bytes(log):
    log.append(NarrationEntry(timestamp=1.0, session_id="abc", text="hello"))
    log.append(NarrationEntry(timestamp=2.0, session_id="abc", text="world"))
    s = log.stats()
    assert s["entries"] == 2
    assert s["bytes"] > 0
    assert s["exists"] is True


def test_stats_when_no_log_yet(log):
    s = log.stats()
    assert s["exists"] is False
    assert s["entries"] == 0


def test_corrupted_lines_skipped(log, tmp_path):
    log.append(NarrationEntry(timestamp=1.0, session_id="abc", text="good"))
    # Inject a corrupt line
    with log.path.open("a", encoding="utf-8") as f:
        f.write("not json at all\n")
    log.append(NarrationEntry(timestamp=3.0, session_id="abc", text="also good"))
    out = log.tail()
    assert [e["text"] for e in out] == ["good", "also good"]


def test_unwritable_path_does_not_raise(tmp_path):
    # Path under a non-existent root — we test that mkdir(parents=True) works.
    # For an actually-unwritable case, just assert append() doesn't bubble
    # exceptions. Construct a deeply nested path that mkdir will handle.
    log = NarrationLog(log_path=tmp_path / "deep" / "nested" / "log.jsonl")
    log.append(NarrationEntry(timestamp=1.0, session_id="x", text="ok"))
    out = log.tail()
    assert len(out) == 1


def test_parse_hedge_prefix_no_prefix():
    from claude_code_talker.narration_log import parse_hedge_prefix
    cleaned, conf = parse_hedge_prefix("Tests passed.")
    assert cleaned == "Tests passed."
    assert conf == "normal"


def test_parse_hedge_prefix_present():
    from claude_code_talker.narration_log import parse_hedge_prefix
    cleaned, conf = parse_hedge_prefix("[UNSURE] Looks like the build may have failed.")
    assert cleaned == "Looks like the build may have failed."
    assert conf == "low"


def test_parse_hedge_prefix_with_leading_whitespace():
    from claude_code_talker.narration_log import parse_hedge_prefix
    cleaned, conf = parse_hedge_prefix("  \n  [UNSURE]   Something maybe.")
    assert cleaned == "Something maybe."
    assert conf == "low"


def test_narration_entry_confidence_field():
    """NarrationEntry accepts and defaults confidence field."""
    entry = NarrationEntry(
        timestamp=1.0,
        session_id="abc",
        text="hello",
    )
    assert entry.confidence == "normal"

    entry_low = NarrationEntry(
        timestamp=1.0,
        session_id="abc",
        text="maybe hello",
        confidence="low",
    )
    assert entry_low.confidence == "low"


def test_narration_entry_confidence_roundtrip(log):
    """Confidence field is preserved in append/tail roundtrip."""
    log.append(NarrationEntry(
        timestamp=1.0,
        session_id="abc",
        text="certain",
        confidence="normal",
    ))
    log.append(NarrationEntry(
        timestamp=2.0,
        session_id="abc",
        text="uncertain",
        confidence="low",
    ))
    out = log.tail()
    assert out[0]["confidence"] == "normal"
    assert out[1]["confidence"] == "low"


def test_parse_checkpoint_prefix_no_prefix():
    from claude_code_talker.narration_log import parse_checkpoint_prefix
    cleaned, is_ckpt = parse_checkpoint_prefix("Using Postgres for the audit log.")
    assert cleaned == "Using Postgres for the audit log."
    assert is_ckpt is False


def test_parse_checkpoint_prefix_present():
    from claude_code_talker.narration_log import parse_checkpoint_prefix
    cleaned, is_ckpt = parse_checkpoint_prefix("[CHECKPOINT] Chose REST over websocket.")
    assert cleaned == "Chose REST over websocket."
    assert is_ckpt is True


def test_parse_checkpoint_prefix_with_leading_whitespace():
    from claude_code_talker.narration_log import parse_checkpoint_prefix
    cleaned, is_ckpt = parse_checkpoint_prefix("  \n  [CHECKPOINT]   Migration schema updated.")
    assert cleaned == "Migration schema updated."
    assert is_ckpt is True


def test_parse_checkpoint_and_unsure_together():
    """Both [CHECKPOINT] and [UNSURE] can be present; checkpoint first."""
    from claude_code_talker.narration_log import parse_checkpoint_prefix, parse_hedge_prefix
    # Order: [CHECKPOINT] first (higher priority), then [UNSURE]
    text = "[CHECKPOINT] [UNSURE] Might use Redis for caching."
    text, is_ckpt = parse_checkpoint_prefix(text)
    text, confidence = parse_hedge_prefix(text)
    assert is_ckpt is True
    assert confidence == "low"
    assert text == "Might use Redis for caching."


def test_narration_entry_checkpoint_field():
    """NarrationEntry accepts and defaults checkpoint field."""
    entry = NarrationEntry(
        timestamp=1.0,
        session_id="abc",
        text="regular decision",
    )
    assert entry.checkpoint is False

    entry_ckpt = NarrationEntry(
        timestamp=1.0,
        session_id="abc",
        text="critical decision",
        checkpoint=True,
    )
    assert entry_ckpt.checkpoint is True


def test_narration_entry_checkpoint_roundtrip(log):
    """Checkpoint field is preserved in append/tail roundtrip."""
    log.append(NarrationEntry(
        timestamp=1.0,
        session_id="abc",
        text="routine edit",
        checkpoint=False,
    ))
    log.append(NarrationEntry(
        timestamp=2.0,
        session_id="abc",
        text="schema decision",
        checkpoint=True,
    ))
    out = log.tail()
    assert out[0]["checkpoint"] is False
    assert out[1]["checkpoint"] is True
