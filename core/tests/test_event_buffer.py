"""Tests for the rolling EventBuffer."""
import time
from claude_code_talker.event_buffer import Event, EventBuffer


def test_event_dataclass_fields():
    e = Event(timestamp=1.0, type="PRE_TOOL", metadata={"tool_name": "Read"}, significance=0.3)
    assert e.type == "PRE_TOOL"
    assert e.metadata["tool_name"] == "Read"
    assert e.significance == 0.3


def test_buffer_push_recent():
    b = EventBuffer(max_size=5)
    for i in range(3):
        b.push(Event(timestamp=float(i), type="PROSE", metadata={}, significance=0.5))
    recent = b.recent(2)
    assert len(recent) == 2
    assert recent[-1].timestamp == 2.0


def test_buffer_max_size_enforced():
    b = EventBuffer(max_size=3)
    for i in range(10):
        b.push(Event(timestamp=float(i), type="PROSE", metadata={}, significance=0.5))
    assert len(b.recent(100)) == 3
    assert b.recent(100)[0].timestamp == 7.0


def test_buffer_since():
    b = EventBuffer()
    t = time.time()
    b.push(Event(timestamp=t - 5, type="PROSE", metadata={}, significance=0.5))
    b.push(Event(timestamp=t + 1, type="PROSE", metadata={}, significance=0.5))
    after = b.since(t)
    assert len(after) == 1
    assert after[0].timestamp == t + 1
