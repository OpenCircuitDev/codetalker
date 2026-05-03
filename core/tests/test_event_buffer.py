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


from claude_code_talker.event_buffer import score_significance


def test_score_notification_max():
    e = Event(timestamp=0.0, type="NOTIFICATION", metadata={"message": "x"}, significance=0.0)
    assert score_significance(e, keywords=["smoking gun"]) == 1.0


def test_score_post_tool_failure():
    e = Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Bash", "success": False}, significance=0.0)
    assert score_significance(e, keywords=[]) >= 0.85


def test_score_prose_with_keyword():
    e = Event(timestamp=0.0, type="PROSE", metadata={"text": "Smoking gun found in the unit conversion"}, significance=0.0)
    assert score_significance(e, keywords=["smoking gun"]) >= 0.7


def test_score_post_tool_edit():
    e = Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Edit", "success": True}, significance=0.0)
    assert 0.5 <= score_significance(e, keywords=[]) <= 0.7


def test_score_routine_read_low():
    e = Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Read", "success": True}, significance=0.0)
    assert score_significance(e, keywords=[]) <= 0.3


def test_subscriber_called_on_push():
    b = EventBuffer()
    received = []
    b.subscribe(received.append)
    b.push(Event(timestamp=0.0, type="PROSE", metadata={}, significance=0.5))
    assert len(received) == 1


def test_subscriber_exception_doesnt_break_buffer():
    b = EventBuffer()
    b.subscribe(lambda e: 1/0)  # raises every call
    b.push(Event(timestamp=0.0, type="PROSE", metadata={}, significance=0.5))
    assert len(b.recent()) == 1  # buffer still got the event


def test_event_has_session_id_default_empty():
    e = Event(timestamp=1.0, type="PRE_TOOL", metadata={})
    assert e.session_id == ""


def test_event_session_id_persists_through_buffer():
    buf = EventBuffer(max_size=10)
    buf.push(Event(timestamp=1.0, type="PRE_TOOL", metadata={}, session_id="sess-A"))
    buf.push(Event(timestamp=2.0, type="PRE_TOOL", metadata={}, session_id="sess-B"))
    items = buf.recent(10)
    assert len(items) == 2
    assert items[0].session_id == "sess-A"
    assert items[1].session_id == "sess-B"
