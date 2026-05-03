"""Tests for TokenTracker (Phase 12)."""
import time
import pytest
from pathlib import Path

from claude_code_talker.token_tracker import TokenTracker, UsageEvent


@pytest.fixture
def tracker(tmp_path):
    return TokenTracker(log_path=tmp_path / "usage.jsonl")


def test_estimate_cost_for_known_model(tracker):
    # gpt-4o-mini: $0.15 prompt, $0.60 completion per 1M tokens
    cost = tracker.estimate_cost("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=500_000)
    # 1M * 0.15 + 0.5M * 0.60 = 0.15 + 0.30 = 0.45
    assert abs(cost - 0.45) < 1e-9


def test_estimate_cost_unknown_model_returns_zero(tracker):
    assert tracker.estimate_cost("not-a-real-model", 1000, 1000) == 0.0


def test_estimate_cost_handles_openrouter_prefix(tracker):
    # OpenRouter "openai/gpt-4o-mini" should map through to gpt-4o-mini pricing
    cost = tracker.estimate_cost("openai/gpt-4o-mini", 1_000_000, 0)
    assert abs(cost - 0.15) < 1e-9


def test_estimate_cost_local_provider_is_free(tracker):
    assert tracker.estimate_cost("ollama", 1_000_000, 1_000_000) == 0.0


def test_record_writes_event(tracker):
    event = tracker.record(
        session_id="abc", provider="openai", model="gpt-4o-mini",
        prompt_tokens=100, completion_tokens=50, purpose="live",
    )
    assert event.total_tokens == 150
    assert event.cost_usd > 0
    assert tracker.path.exists()


def test_rollup_aggregates_by_session_and_provider(tracker):
    tracker.record(session_id="a", provider="openai", model="gpt-4o-mini",
                   prompt_tokens=1_000_000, completion_tokens=0, purpose="live")
    tracker.record(session_id="a", provider="openai", model="gpt-4o-mini",
                   prompt_tokens=1_000_000, completion_tokens=0, purpose="brief")
    tracker.record(session_id="b", provider="anthropic", model="claude-haiku-4-5-20251001",
                   prompt_tokens=1_000_000, completion_tokens=1_000_000, purpose="chat")
    r = tracker.rollup()
    assert r["event_count"] == 3
    # Session a: 2 events, both gpt-4o-mini, prompt-only = 0.30 total
    assert abs(r["by_session"]["a"]["cost"] - 0.30) < 1e-6
    # Session b: claude haiku, 1M prompt ($1) + 1M completion ($5) = $6
    assert abs(r["by_session"]["b"]["cost"] - 6.00) < 1e-6
    # by_purpose
    assert "live" in r["by_purpose"]
    assert "brief" in r["by_purpose"]
    assert "chat" in r["by_purpose"]


def test_rollup_since_filters_old_events(tracker):
    tracker.record(session_id="a", provider="openai", model="gpt-4o-mini",
                   prompt_tokens=1_000_000, completion_tokens=0)
    cutoff = time.time()
    time.sleep(0.05)
    tracker.record(session_id="b", provider="openai", model="gpt-4o-mini",
                   prompt_tokens=1_000_000, completion_tokens=0)
    r = tracker.rollup(since=cutoff)
    assert r["event_count"] == 1
    assert "b" in r["by_session"]
    assert "a" not in r["by_session"]


def test_rollup_empty_log(tracker):
    r = tracker.rollup()
    assert r["event_count"] == 0
    assert r["total_cost_usd"] == 0.0
    assert r["total_tokens"] == 0


def test_rollup_skips_corrupted_lines(tracker):
    tracker.record(session_id="a", provider="openai", model="gpt-4o-mini",
                   prompt_tokens=100, completion_tokens=50)
    with tracker.path.open("a", encoding="utf-8") as f:
        f.write("not-json\n")
    tracker.record(session_id="b", provider="openai", model="gpt-4o-mini",
                   prompt_tokens=100, completion_tokens=50)
    r = tracker.rollup()
    assert r["event_count"] == 2


def test_custom_price_table_extends_defaults():
    tracker = TokenTracker(price_table={"my-private-model": (5.0, 25.0)})
    cost = tracker.estimate_cost("my-private-model", 1_000_000, 0)
    assert abs(cost - 5.0) < 1e-9
    # Default models still work
    cost2 = tracker.estimate_cost("gpt-4o-mini", 1_000_000, 0)
    assert abs(cost2 - 0.15) < 1e-9
