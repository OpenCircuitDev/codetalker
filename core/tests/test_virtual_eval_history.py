"""Tests for virtual_eval.history (append-only tuning audit log)."""
import json
import pytest
import time
from pathlib import Path

from claude_code_talker.virtual_eval.history import (
    TuningHistory, TuningEntry,
)


@pytest.fixture
def history(tmp_path):
    return TuningHistory(log_path=tmp_path / "tuning.jsonl")


def test_append_creates_id_and_persists(history):
    entry = history.append(
        before={"depth_level": 3},
        after={"depth_level": 4},
        reasoning="3 personas asked for accessible language",
        applied=True,
    )
    assert entry.id  # nonempty
    assert entry.applied is True
    # Round-trip through file
    entries = history.list_all()
    assert len(entries) == 1
    assert entries[0].id == entry.id


def test_list_all_returns_oldest_first(history):
    history.append(before={"a": 1}, after={"a": 2}, reasoning="x", applied=True)
    history.append(before={"b": 1}, after={"b": 2}, reasoning="y", applied=True)
    entries = history.list_all()
    assert entries[0].after == {"a": 2}
    assert entries[1].after == {"b": 2}


def test_get_returns_entry_by_id(history):
    e = history.append(before={"x": 1}, after={"x": 2}, reasoning="r", applied=True)
    found = history.get(e.id)
    assert found is not None
    assert found.id == e.id


def test_get_missing_returns_none(history):
    assert history.get("nope") is None


def test_pending_approval_filter(history):
    history.append(before={"a": 1}, after={"a": 2}, reasoning="r1", applied=True)
    history.append(before={"b": 1}, after={"b": 2}, reasoning="r2", applied=False)
    pending = [e for e in history.list_all() if not e.applied]
    assert len(pending) == 1
    assert pending[0].after == {"b": 2}


def test_revert_returns_inverse_diff(history):
    e = history.append(before={"depth_level": 3}, after={"depth_level": 4},
                       reasoning="x", applied=True)
    inv = history.revert_diff(e.id)
    # Reverting means swapping before/after
    assert inv["fields_to_set"] == {"depth_level": 3}


def test_revert_unknown_id_raises(history):
    with pytest.raises(KeyError):
        history.revert_diff("nope")


def test_corrupted_lines_skipped(history, tmp_path):
    history.append(before={"a": 1}, after={"a": 2}, reasoning="ok", applied=True)
    # Inject corruption
    with history.path.open("a", encoding="utf-8") as f:
        f.write("not-json\n")
    history.append(before={"b": 1}, after={"b": 2}, reasoning="also ok", applied=True)
    entries = history.list_all()
    assert len(entries) == 2
