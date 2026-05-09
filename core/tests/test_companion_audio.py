"""CCT-31 — audio stream multiplexer tests."""
from __future__ import annotations

import asyncio
import pytest

from claude_code_talker.companion.audio_stream import AudioStreamHub


@pytest.mark.asyncio
async def test_subscribe_yields_published_frames():
    hub = AudioStreamHub()
    sub = hub.subscribe("sid-1")
    await hub.publish("sid-1", b"frame1")
    await hub.publish("sid-1", b"frame2")
    await hub.close("sid-1")
    frames = []
    async for f in sub:
        frames.append(f)
    assert frames == [b"frame1", b"frame2"]


@pytest.mark.asyncio
async def test_publish_to_other_session_isolated():
    hub = AudioStreamHub()
    sub_a = hub.subscribe("sid-a")
    sub_b = hub.subscribe("sid-b")
    await hub.publish("sid-a", b"a-only")
    await hub.close("sid-a")
    await hub.close("sid-b")
    a_frames = [f async for f in sub_a]
    b_frames = [f async for f in sub_b]
    assert a_frames == [b"a-only"]
    assert b_frames == []


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_frames():
    hub = AudioStreamHub()
    s1 = hub.subscribe("sid-x")
    s2 = hub.subscribe("sid-x")
    await hub.publish("sid-x", b"shared")
    await hub.close("sid-x")
    f1 = [f async for f in s1]
    f2 = [f async for f in s2]
    assert f1 == [b"shared"]
    assert f2 == [b"shared"]


@pytest.mark.asyncio
async def test_unsubscribed_after_close_yields_nothing():
    hub = AudioStreamHub()
    sub = hub.subscribe("sid-1")
    await hub.close("sid-1")
    assert [f async for f in sub] == []


@pytest.mark.asyncio
async def test_publish_to_unknown_session_silent():
    hub = AudioStreamHub()
    await hub.publish("ghost", b"frame")  # no raise
