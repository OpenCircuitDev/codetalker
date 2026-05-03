"""Mode C: live narration."""
from __future__ import annotations

import asyncio
import logging

from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.event_buffer import Event, EventBuffer
from claude_code_talker.cadence.base import CadenceStrategy
from claude_code_talker.audio import AudioJob
from claude_code_talker.teacher_mode import merge_teacher_into_prompt


LIVE_NARRATION_PROMPT = """\
You are a sportscaster narrating Claude's work in real time. Translate the
recent events below into ONE short sentence (max 30 words) of accessible spoken
English. Use present tense for ongoing work, past tense for completed actions.
Highlight findings, errors, and decisions. Skip routine reads unless they
matter to the narrative. No markdown, no lists. Just spoken English.

RECENT EVENTS (most recent last):
{events}

NARRATION:"""


class LiveMode(ModeStrategy):
    name = "live"

    def __init__(self, provider, cadence: CadenceStrategy, event_buffer: EventBuffer, audio_queue, cfg: dict):
        self.provider = provider
        self.cadence = cadence
        self.event_buffer = event_buffer
        self.audio_queue = audio_queue
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # build() satisfies ModeStrategy; not used in production
    def build(self, prose_entries, tool_uses, todos, cfg):
        return ""

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self.event_buffer.subscribe(self._on_event)
        self._task = asyncio.create_task(self._cadence_loop())

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _on_event(self, event: Event) -> None:
        # runs in EventBuffer's caller's thread (the MCP tool handler)
        decision = self.cadence.on_event(event)
        if decision.fire_immediately and self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._narrate(decision.events, priority="alert"),
                self._loop,
            )

    async def _cadence_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(0.5)
                decision = self.cadence.tick()
                if decision.fire_periodic:
                    await self._narrate(decision.events, priority="normal")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning("live cadence loop: %s", e)

    async def _narrate(self, events, priority):
        if not events:
            return
        prompt = self._build_prompt(events)
        budget = float((self.cfg.get("live") or {}).get("llm_latency_budget_seconds", 8.0))
        try:
            text = await asyncio.wait_for(
                self.provider.complete(prompt, max_tokens=150),
                timeout=budget,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logging.debug("live narration skipped: %s", e)
            return

        text = (text or "").strip()
        if not text:
            return

        voice_cfg = self.cfg.get("voice") or {}
        voice = voice_cfg.get("model")
        rate = float(voice_cfg.get("rate", 1.0))
        if not voice:
            return

        self.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, priority=priority,
        ))

    def _build_prompt(self, events) -> str:
        lines = []
        if not events:
            lines.append("(no events)")
        else:
            t0 = events[0].timestamp
            for ev in events[-12:]:
                dt = ev.timestamp - t0
                meta = ev.metadata
                if ev.type == "PROSE":
                    snippet = (meta.get("text") or "")[:120]
                    lines.append(f"[T+{dt:.1f}s PROSE] {snippet}")
                elif ev.type == "NOTIFICATION":
                    lines.append(f"[T+{dt:.1f}s NOTIFICATION] {meta.get('message', '')[:120]}")
                elif ev.type == "PRE_TOOL":
                    lines.append(f"[T+{dt:.1f}s PRE_TOOL {meta.get('tool_name', '?')}]")
                elif ev.type == "POST_TOOL":
                    ok = "ok" if meta.get('success', True) else "FAILED"
                    lines.append(f"[T+{dt:.1f}s POST_TOOL {meta.get('tool_name', '?')} {ok}]")
        base = LIVE_NARRATION_PROMPT.format(events="\n".join(lines))
        return merge_teacher_into_prompt(base, self.cfg.get("teacher_mode"))
