"""Phase 23 — NarrationStream pub/sub round-trip tests."""
import asyncio
import pytest

from claude_code_talker.narration_stream import NarrationStream, NarrationEvent


@pytest.mark.asyncio
async def test_publish_reaches_one_subscriber():
    stream = NarrationStream()
    sub = stream.subscribe()
    ev = NarrationEvent(
        session_id="abc",
        timestamp=1.0,
        text="hello",
        voice="v1",
        mode="brief",
        status="queued",
    )
    await stream.publish(ev)
    received = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
    assert received.session_id == "abc"
    assert received.status == "queued"


@pytest.mark.asyncio
async def test_publish_fans_out_to_multiple_subscribers():
    stream = NarrationStream()
    a = stream.subscribe()
    b = stream.subscribe()
    ev = NarrationEvent(
        session_id="x", timestamp=0.0, text="t", voice="v", mode="m", status="queued",
    )
    await stream.publish(ev)
    ra = await asyncio.wait_for(a.__anext__(), timeout=1.0)
    rb = await asyncio.wait_for(b.__anext__(), timeout=1.0)
    assert ra.text == rb.text == "t"


@pytest.mark.asyncio
async def test_overflow_emits_sentinel():
    stream = NarrationStream(max_queue=2)
    sub = stream.subscribe()
    base = dict(session_id="x", timestamp=0.0, voice="v", mode="m")
    for i in range(5):
        await stream.publish(
            NarrationEvent(text=str(i), status="queued", **base)
        )
    # Drain — at least one event should be the overflow sentinel
    events = []
    for _ in range(3):
        try:
            events.append(await asyncio.wait_for(sub.__anext__(), timeout=0.5))
        except asyncio.TimeoutError:
            break
    statuses = {e.status for e in events}
    assert "overflow" in statuses


@pytest.mark.asyncio
async def test_narration_stream_available_on_api():
    """Verify the /api/narration-stream endpoint is registered and accessible."""
    from claude_code_talker.server import build_server_state, build_asgi_app
    from claude_code_talker.api import build_routes

    state = build_server_state()
    routes = build_routes(state)

    # Check that the narration-stream route exists
    narration_routes = [r for r in routes if hasattr(r, 'path') and '/narration-stream' in r.path]
    assert len(narration_routes) > 0, "narration-stream route not found in routes"
    assert narration_routes[0].path == "/api/narration-stream"
