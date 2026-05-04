import time
from claude_code_talker.cadence.per_cluster import PerClusterCadence, HIGH_SIG_THRESHOLD
from claude_code_talker.event_buffer import Event


def _ev():
    return Event(timestamp=time.time(), type="POST_TOOL", metadata={}, significance=0.3)


def test_high_sig_event_fires_immediately_in_cluster():
    """Phase 13.9b Task 4: significance >= HIGH_SIG_THRESHOLD bypasses cluster grouping."""
    c = PerClusterCadence(cluster_gap_seconds=60.0, max_cluster_size=100)
    high = Event(timestamp=1.0, type="POST_TOOL", metadata={"success": False}, significance=HIGH_SIG_THRESHOLD)
    decision = c.on_event(high)
    assert decision.fire_immediately is True
    assert high in decision.events


def test_high_sig_event_not_added_to_cluster_buffer():
    """Phase 13.9b Task 4: high-sig event is not buffered; cluster remains empty."""
    c = PerClusterCadence(cluster_gap_seconds=0.05, max_cluster_size=100)
    high = Event(timestamp=1.0, type="POST_TOOL", metadata={}, significance=0.9)
    c.on_event(high)
    time.sleep(0.1)
    tick_d = c.tick()
    # Cluster buffer was never populated, so tick returns nothing
    assert tick_d.fire_periodic is False


def test_low_sig_event_still_clusters():
    """Phase 13.9b Task 4: low-sig events remain in cluster, unaffected by the threshold change."""
    c = PerClusterCadence(cluster_gap_seconds=60.0, max_cluster_size=100)
    low = Event(timestamp=1.0, type="PRE_TOOL", metadata={}, significance=0.2)
    decision = c.on_event(low)
    assert decision.fire_immediately is False


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
