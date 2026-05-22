import asyncio
import pytest
from unittest.mock import MagicMock
from claude_code_talker.modes.live import LiveMode
from claude_code_talker.event_buffer import EventBuffer, Event
from claude_code_talker.cadence.periodic import PeriodicCadence


def test_live_mode_subclass_name():
    assert LiveMode.name == "live"


@pytest.mark.asyncio
async def test_live_mode_start_subscribes():
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    mode = LiveMode(provider=None, cadence=cadence, event_buffer=buf, audio_queue=MagicMock(), cfg={})
    mode.start()
    assert len(buf._subscribers) == 1
    await mode.shutdown()


@pytest.mark.asyncio
async def test_live_narrate_calls_provider_and_enqueues():
    from unittest.mock import AsyncMock
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    audio_q = MagicMock()
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="Reading the orchestrator file.")

    cfg = {
        "live": {"llm_latency_budget_seconds": 5.0},
        "voice": {"model": "jenny", "rate": 1.0},
    }
    mode = LiveMode(provider=provider, cadence=cadence, event_buffer=buf, audio_queue=audio_q, cfg=cfg)
    # significance=0.6 is above the cadence-aware skip threshold (0.3) and concise threshold (0.5)
    events = [Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Read"}, significance=0.6, session_id="test-session")]
    await mode._narrate(events, priority="normal", session_id="test-session")

    provider.complete.assert_called_once()
    audio_q.submit.assert_called_once()
    job = audio_q.submit.call_args[0][0]
    assert "orchestrator" in job.text.lower() or "Reading" in job.text
    assert job.priority == "normal"


@pytest.mark.asyncio
async def test_live_narrate_skips_on_provider_error():
    from unittest.mock import AsyncMock
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    audio_q = MagicMock()
    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("ollama down"))
    cfg = {"live": {}, "voice": {"model": "j", "rate": 1.0}}
    mode = LiveMode(provider=provider, cadence=cadence, event_buffer=buf, audio_queue=audio_q, cfg=cfg)
    await mode._narrate([Event(timestamp=0.0, type="PROSE", metadata={}, significance=0.5, session_id="test-session")], "normal", session_id="test-session")
    audio_q.submit.assert_not_called()


@pytest.mark.asyncio
async def test_live_narrate_skips_on_timeout():
    from unittest.mock import AsyncMock
    import asyncio
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    audio_q = MagicMock()
    provider = AsyncMock()

    async def slow(*a, **kw):
        await asyncio.sleep(2.0)
        return "too late"
    provider.complete = slow

    cfg = {"live": {"llm_latency_budget_seconds": 0.1}, "voice": {"model": "j", "rate": 1.0}}
    mode = LiveMode(provider=provider, cadence=cadence, event_buffer=buf, audio_queue=audio_q, cfg=cfg)
    await mode._narrate([Event(timestamp=0.0, type="PROSE", metadata={}, significance=0.5, session_id="test-session")], "normal", session_id="test-session")
    audio_q.submit.assert_not_called()


@pytest.mark.asyncio
async def test_live_cadence_loop_fires_periodic():
    from unittest.mock import AsyncMock
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=0.1)
    audio_q = MagicMock()
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="narration")
    cfg = {"live": {}, "voice": {"model": "j", "rate": 1.0}}

    mode = LiveMode(provider=provider, cadence=cadence, event_buffer=buf, audio_queue=audio_q, cfg=cfg)
    mode.start()

    # Push an event into the buffer; cadence will gather it
    buf.push(Event(timestamp=0.0, type="PROSE", metadata={"text": "hi"}, significance=0.5))

    # Wait for periodic tick to fire
    await asyncio.sleep(0.7)
    await mode.shutdown()

    audio_q.submit.assert_called()


@pytest.mark.asyncio
async def test_live_narrate_strips_hedge_prefix_non_streaming():
    """Non-streaming path: [UNSURE] prefix is stripped and confidence='low' is set."""
    from unittest.mock import AsyncMock
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    audio_q = MagicMock()
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="[UNSURE] Maybe the build is still running.")
    provider.supports_streaming = False

    cfg = {
        "live": {"llm_latency_budget_seconds": 5.0},
        "voice": {"model": "jenny", "rate": 1.0},
    }
    mode = LiveMode(provider=provider, cadence=cadence, event_buffer=buf, audio_queue=audio_q, cfg=cfg)
    events = [Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Read"}, significance=0.6, session_id="test-session")]
    await mode._narrate(events, priority="normal", session_id="test-session")

    audio_q.submit.assert_called_once()
    job = audio_q.submit.call_args[0][0]
    assert "[UNSURE]" not in job.text
    assert "Maybe the build is still running" in job.text
    assert job.confidence == "low"


@pytest.mark.asyncio
async def test_live_narrate_streaming_strips_hedge_prefix():
    """Streaming path: [UNSURE] prefix is stripped from first chunk and confidence='low' is set."""
    from unittest.mock import AsyncMock, MagicMock as Mock
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    audio_q = Mock()
    provider = Mock()
    provider.supports_streaming = True

    # Simulate streaming chunks where [UNSURE] is at the start of the first chunk
    async def mock_stream(prompt, **kwargs):
        yield "[UNSURE] Maybe the"
        yield " build is"
        yield " running."

    provider.stream = MagicMock(return_value=mock_stream(None))

    cfg = {
        "live": {"llm_latency_budget_seconds": 5.0},
        "voice": {"model": "jenny", "rate": 1.0},
    }
    mode = LiveMode(provider=provider, cadence=cadence, event_buffer=buf, audio_queue=audio_q, cfg=cfg)
    events = [Event(timestamp=0.0, type="POST_TOOL", metadata={"tool_name": "Read"}, significance=0.6, session_id="test-session")]
    await mode._narrate(events, priority="normal", session_id="test-session")

    # Should have submitted chunks via the streaming path
    assert audio_q.submit.called
    # First submitted job should have confidence="low"
    first_job = audio_q.submit.call_args_list[0][0][0]
    assert first_job.confidence == "low"
    # Text should not contain [UNSURE]
    assert "[UNSURE]" not in first_job.text
    assert "Maybe the" in first_job.text
