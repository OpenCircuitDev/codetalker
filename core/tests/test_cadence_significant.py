from claude_code_talker.cadence.significant_only import SignificantOnlyCadence
from claude_code_talker.event_buffer import Event


def test_significant_fires_at_threshold():
    c = SignificantOnlyCadence(threshold=0.5)
    e = Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Edit"}, significance=0.6)
    d = c.on_event(e)
    assert d.fire_immediately is True


def test_significant_skips_below_threshold():
    c = SignificantOnlyCadence(threshold=0.5)
    e = Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Read"}, significance=0.2)
    d = c.on_event(e)
    assert d.fire_immediately is False
