import time
from claude_code_talker.cadence.per_cluster import PerClusterCadence
from claude_code_talker.event_buffer import Event


def _ev():
    return Event(timestamp=time.time(), type="POST_TOOL", metadata={}, significance=0.3)


def test_cluster_fires_after_idle_gap():
    c = PerClusterCadence(cluster_gap_seconds=0.1, max_cluster_size=10)
    c.on_event(_ev())
    c.on_event(_ev())
    time.sleep(0.15)
    d = c.tick()
    assert d.fire_periodic is True
    assert len(d.events) == 2


def test_cluster_fires_at_max_size():
    c = PerClusterCadence(cluster_gap_seconds=10.0, max_cluster_size=3)
    c.on_event(_ev()); c.on_event(_ev())
    d = c.on_event(_ev())  # third event hits the cap
    assert d.fire_immediately is True
    assert len(d.events) == 3
