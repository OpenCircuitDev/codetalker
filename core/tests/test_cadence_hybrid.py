import time
from claude_code_talker.cadence.hybrid import HybridCadence
from claude_code_talker.event_buffer import Event


def test_hybrid_significant_fires_immediately():
    c = HybridCadence(threshold=0.5, period_seconds=10.0)
    e = Event(timestamp=time.time(), type="POST_TOOL", metadata={}, significance=0.7)
    d = c.on_event(e)
    assert d.fire_immediately is True


def test_hybrid_routine_periodic():
    c = HybridCadence(threshold=0.5, period_seconds=0.1)
    e = Event(timestamp=time.time(), type="POST_TOOL", metadata={}, significance=0.2)
    c.on_event(e)
    time.sleep(0.15)
    d = c.tick()
    assert d.fire_periodic is True
    assert len(d.events) == 1
