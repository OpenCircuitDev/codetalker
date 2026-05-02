import time
from claude_code_talker.event_buffer import Event
from claude_code_talker.cadence.periodic import PeriodicCadence


def test_periodic_no_fire_when_no_events():
    c = PeriodicCadence(period_seconds=0.1)
    time.sleep(0.15)
    d = c.tick()
    assert d.fire_periodic is False


def test_periodic_fires_after_period_with_events():
    c = PeriodicCadence(period_seconds=0.1)
    c.on_event(Event(timestamp=time.time(), type="PROSE", metadata={}, significance=0.5))
    time.sleep(0.15)
    d = c.tick()
    assert d.fire_periodic is True
    assert len(d.events) == 1


def test_periodic_no_double_fire():
    c = PeriodicCadence(period_seconds=0.05)
    c.on_event(Event(timestamp=time.time(), type="PROSE", metadata={}, significance=0.5))
    time.sleep(0.1)
    d1 = c.tick()
    assert d1.fire_periodic is True
    d2 = c.tick()
    assert d2.fire_periodic is False  # already fired; no new events since
