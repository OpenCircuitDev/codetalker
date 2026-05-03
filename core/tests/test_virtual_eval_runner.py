"""Tests for virtual_eval.runner sample selection."""
import json
import pytest
import time
from pathlib import Path

from claude_code_talker.narration_log import NarrationLog, NarrationEntry
from claude_code_talker.virtual_eval.runner import (
    EvalRequest, select_narration_sample,
)


@pytest.fixture
def populated_log(tmp_path):
    log = NarrationLog(log_path=tmp_path / "narration.jsonl",
                       max_bytes=10 * 1024 * 1024)
    base_ts = 1000.0
    # 10 entries per mode across the 5 in-scope modes
    for mode in ("live", "live-stream", "brief", "prompt-brief", "chat"):
        for i in range(10):
            log.append(NarrationEntry(
                timestamp=base_ts + i, session_id=f"sid-{mode}",
                text=f"narration {mode} {i}", voice="v", engine="e", mode=mode,
            ))
    # Plus 5 entries with an out-of-scope mode (should be filtered out)
    for i in range(5):
        log.append(NarrationEntry(
            timestamp=base_ts + i, session_id="x", text="excluded",
            voice="v", engine="e", mode="some-other-mode",
        ))
    return log


def test_eval_request_defaults():
    req = EvalRequest()
    assert req.max_narrations == 50
    assert req.deployed_at == 0.0
    assert "live" in req.included_modes


def test_select_returns_all_when_under_cap(populated_log):
    req = EvalRequest(max_narrations=200, deployed_at=0.0)
    sample = select_narration_sample(populated_log, req)
    # 50 in-scope entries (10 per mode × 5 modes); 5 excluded
    assert len(sample) == 50
    assert all(s["mode"] != "some-other-mode" for s in sample)


def test_select_filters_by_deployed_at(populated_log):
    # Only entries with timestamp >= 1005 should survive
    req = EvalRequest(max_narrations=200, deployed_at=1005.0)
    sample = select_narration_sample(populated_log, req)
    assert len(sample) == 25  # 5 modes × 5 surviving entries each (i=5..9)
    assert all(s["timestamp"] >= 1005.0 for s in sample)


def test_select_stratified_when_over_cap(populated_log):
    # Cap = 10 → 2 per mode (10 / 5 modes)
    req = EvalRequest(max_narrations=10, deployed_at=0.0)
    sample = select_narration_sample(populated_log, req)
    assert len(sample) == 10
    by_mode: dict[str, int] = {}
    for s in sample:
        by_mode[s["mode"]] = by_mode.get(s["mode"], 0) + 1
    # All 5 modes represented
    assert len(by_mode) == 5
    # ~2 per mode
    for count in by_mode.values():
        assert 1 <= count <= 3


def test_select_returns_empty_when_log_empty(tmp_path):
    log = NarrationLog(log_path=tmp_path / "narration.jsonl")
    req = EvalRequest()
    assert select_narration_sample(log, req) == []


def test_select_cap_zero_returns_empty(populated_log):
    """max_narrations=0 yields an empty sample (defensive boundary)."""
    req = EvalRequest(max_narrations=0, deployed_at=0.0)
    sample = select_narration_sample(populated_log, req)
    assert sample == []
