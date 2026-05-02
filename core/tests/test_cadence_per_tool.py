from claude_code_talker.cadence.per_tool_call import PerToolCallCadence
from claude_code_talker.event_buffer import Event


def test_per_tool_fires_immediately_on_event():
    c = PerToolCallCadence()
    e = Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Edit"}, significance=0.6)
    d = c.on_event(e)
    assert d.fire_immediately is True
    assert d.events == [e]


def test_per_tool_tick_no_fire():
    c = PerToolCallCadence()
    d = c.tick()
    assert d.fire_periodic is False
