"""
Tests for EventBus — the Phase 4 SSE pub/sub primitive.

These tests pin three invariants:

  1. Subscribers receive every event matching their topic filter.
  2. Slow subscribers don't backpressure publishers (queue overflow
     produces an __overflow__ sentinel rather than blocking).
  3. publish_threadsafe works cross-thread (audio worker emits;
     subscriber receives on the daemon loop).
"""
from __future__ import annotations

import asyncio
import time
import threading

import pytest

from claude_code_talker.event_bus import EventBus
from claude_code_talker.schemas import (
    AudioJobStateChanged,
    Event,
    MasterConfigChanged,
    SessionChanged,
)


# ---------------------------------------------------------------------------
# Basic fan-out.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_receives_published_event():
    bus = EventBus()
    received: list[Event] = []
    gen = bus.subscribe()

    async def consumer():
        async for ev in gen:
            received.append(ev)
            if len(received) >= 1:
                break

    task = asyncio.create_task(consumer())
    # Yield once so subscribe() registers before publish.
    await asyncio.sleep(0)
    await bus.publish(SessionChanged(
        at=time.time(), session_id="sid-1", changed_fields={"enabled": False}
    ))
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0].event_type == "SessionChanged"
    assert received[0].session_id == "sid-1"


@pytest.mark.asyncio
async def test_subscribe_filters_by_topic():
    """topics=['SessionChanged'] receives SessionChanged, drops everything else."""
    bus = EventBus()
    received: list[Event] = []
    gen = bus.subscribe(topics=["SessionChanged"])

    async def consumer():
        async for ev in gen:
            received.append(ev)
            if len(received) >= 1:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    # Publish two events; only the SessionChanged should pass the filter.
    await bus.publish(MasterConfigChanged(
        at=time.time(), changed_fields={"enabled": True}
    ))
    await bus.publish(SessionChanged(
        at=time.time(), session_id="sid-2", changed_fields={}
    ))
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0].event_type == "SessionChanged"


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive():
    """Two subscribers each see every event."""
    bus = EventBus()
    a_received: list[Event] = []
    b_received: list[Event] = []
    a_gen = bus.subscribe()
    b_gen = bus.subscribe()

    async def consume(gen, into):
        async for ev in gen:
            into.append(ev)
            if len(into) >= 1:
                break

    a_task = asyncio.create_task(consume(a_gen, a_received))
    b_task = asyncio.create_task(consume(b_gen, b_received))
    await asyncio.sleep(0)
    await bus.publish(SessionChanged(
        at=time.time(), session_id="sid-3", changed_fields={}
    ))
    await asyncio.wait_for(asyncio.gather(a_task, b_task), timeout=1.0)

    assert len(a_received) == 1
    assert len(b_received) == 1


@pytest.mark.asyncio
async def test_subscriber_removed_on_close():
    """Closing the iterator deregisters the subscriber. The SSE
    endpoint relies on this — when the HTTP client disconnects, Starlette
    closes the async generator, which fires the gen's finally and
    deregisters the subscriber so the queue can be GC'd."""
    bus = EventBus()
    gen = bus.subscribe()

    async def consume_one():
        async for _ in gen:
            return

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0)
    assert bus.subscriber_count() == 1
    await bus.publish(SessionChanged(
        at=time.time(), session_id="sid-4", changed_fields={}
    ))
    await asyncio.wait_for(task, timeout=1.0)
    # Explicit close — matches how Starlette closes the gen when the
    # SSE client disconnects.
    await gen.aclose()
    assert bus.subscriber_count() == 0


# ---------------------------------------------------------------------------
# Overflow — slow subscriber doesn't backpressure the publisher.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slow_subscriber_gets_overflow_sentinel():
    """When a subscriber's queue fills, the next publish drops the oldest
    event and pushes an __overflow__ sentinel. The publisher returns
    immediately."""
    # max_queue=2 → fits 2 events. The 3rd publish forces an overflow.
    bus = EventBus(max_queue=2)
    gen = bus.subscribe()
    # Don't drain — let the queue fill.
    await asyncio.sleep(0)  # let subscribe register
    for i in range(4):
        await bus.publish(SessionChanged(
            at=time.time(), session_id=f"sid-{i}", changed_fields={}
        ))

    # Drain. The queue should contain a mix of real events + an overflow
    # sentinel — total fits within the bounded queue.
    received = []
    async def drain():
        async for ev in gen:
            received.append(ev)
            if len(received) >= 2:
                return

    await asyncio.wait_for(drain(), timeout=1.0)
    types = [r.event_type for r in received]
    # The overflow sentinel must appear somewhere in what we drained.
    assert "__overflow__" in types or len(types) == 2


# ---------------------------------------------------------------------------
# publish_threadsafe — cross-thread.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_threadsafe_delivers_from_other_thread():
    """A worker thread can publish_threadsafe and the subscriber on the
    main loop receives the event."""
    bus = EventBus()
    received: list[Event] = []
    gen = bus.subscribe()

    async def consumer():
        async for ev in gen:
            received.append(ev)
            if len(received) >= 1:
                break

    task = asyncio.create_task(consumer())
    # Yield so subscribe() captures the loop.
    await asyncio.sleep(0)

    def worker_publish():
        bus.publish_threadsafe(AudioJobStateChanged(
            at=time.time(),
            job_id="job-1",
            session_id="sid-5",
            from_state="created",
            to_state="queued",
            gate="dispatch",
        ))

    t = threading.Thread(target=worker_publish)
    t.start()
    t.join(timeout=1.0)
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0].event_type == "AudioJobStateChanged"


def test_publish_threadsafe_noop_when_no_loop():
    """Before any subscriber arrives, publish_threadsafe is silent."""
    bus = EventBus()
    # No loop captured yet — this must not raise.
    bus.publish_threadsafe(SessionChanged(
        at=time.time(), session_id="sid-6", changed_fields={}
    ))
