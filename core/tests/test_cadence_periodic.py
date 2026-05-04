import time
from claude_code_talker.event_buffer import Event
from claude_code_talker.cadence.periodic import PeriodicCadence, HIGH_SIG_THRESHOLD


def test_high_sig_event_fires_immediately():
    """Phase 13.9b Task 4: significance >= HIGH_SIG_THRESHOLD events bypass tick wait."""
    cadence = PeriodicCadence(period_seconds=60.0)  # large period — only fire_immediately should win
    high = Event(timestamp=1.0, type="POST_TOOL", metadata={"success": False}, significance=HIGH_SIG_THRESHOLD)
    decision = cadence.on_event(high)
    assert decision.fire_immediately is True
    assert high in decision.events


def test_high_sig_event_fires_immediately_explicit_0_85():
    """Phase 13.9b Task 4: significance=0.85 fires immediately (above threshold)."""
    cadence = PeriodicCadence(period_seconds=60.0)
    high = Event(timestamp=1.0, type="POST_TOOL", metadata={"success": False}, significance=0.85)
    decision = cadence.on_event(high)
    assert decision.fire_immediately is True
    assert high in decision.events


def test_low_sig_event_does_not_fire_immediately():
    """Phase 13.9b Task 4: significance < HIGH_SIG_THRESHOLD goes to buffer, not immediate."""
    cadence = PeriodicCadence(period_seconds=60.0)
    low = Event(timestamp=1.0, type="PRE_TOOL", metadata={}, significance=0.2)
    decision = cadence.on_event(low)
    assert decision.fire_immediately is False


def test_just_below_threshold_does_not_fire_immediately():
    """Phase 13.9b Task 4: significance just below threshold stays buffered."""
    cadence = PeriodicCadence(period_seconds=60.0)
    near = Event(timestamp=1.0, type="PRE_TOOL", metadata={}, significance=HIGH_SIG_THRESHOLD - 0.01)
    decision = cadence.on_event(near)
    assert decision.fire_immediately is False


def test_high_sig_event_not_added_to_buffer():
    """Phase 13.9b Task 4: high-sig events bypass the buffer, so they don't appear in periodic tick."""
    cadence = PeriodicCadence(period_seconds=0.05)
    high = Event(timestamp=1.0, type="POST_TOOL", metadata={}, significance=0.9)
    cadence.on_event(high)
    time.sleep(0.1)
    tick_d = cadence.tick()
    # Buffer was never populated with the high-sig event, so tick returns nothing
    assert tick_d.fire_periodic is False


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
