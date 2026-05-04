"""Watcher for active session transcript files. Polls mtime, parses new lines,
pre-populates per-session prose cache for the narrator."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from claude_code_talker.transcript import is_real_user_message, _SKIP_PROSE_PREFIXES


@dataclass
class _WatchedFile:
    path: Path
    last_mtime: float = 0.0
    last_size: int = 0
    cached_prose: list[str] = field(default_factory=list)  # cleaned assistant prose, newest last
    cached_user_prompts: list[str] = field(default_factory=list)


class TranscriptWatcher:
    """Polls active session transcripts for new lines and caches recent prose.

    Started/stopped by daemon lifecycle. Per-session caches accumulate over the
    daemon's lifetime; bounded by max_prose_per_session.
    """

    def __init__(self, *, poll_interval: float = 1.0, max_prose_per_session: int = 50,
                 on_new_user_prompt: Callable[[str, str], None] | None = None,
                 on_new_prose: Callable[[str, str], None] | None = None):
        self.poll_interval = poll_interval
        self.max_prose_per_session = max_prose_per_session
        self._files: dict[str, _WatchedFile] = {}  # session_id -> WatchedFile
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._on_new_user_prompt = on_new_user_prompt
        self._on_new_prose = on_new_prose

    def watch(self, session_id: str, transcript_path: Path) -> None:
        """Register a session for watching. Idempotent."""
        if session_id not in self._files:
            self._files[session_id] = _WatchedFile(path=Path(transcript_path))

    def get_cached_prose(self, session_id: str) -> list[str]:
        """Return cached prose for a session (newest last). Empty if not watched."""
        wf = self._files.get(session_id)
        return list(wf.cached_prose) if wf else []

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                if self._stop_event is not None and self._stop_event.is_set():
                    return
                for sid, wf in list(self._files.items()):
                    self._scan_one(sid, wf)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logging.warning("transcript watcher loop error: %s", e)
                await asyncio.sleep(self.poll_interval)

    def _scan_one(self, session_id: str, wf: _WatchedFile) -> None:
        try:
            stat = wf.path.stat()
        except OSError:
            return
        if stat.st_mtime <= wf.last_mtime and stat.st_size == wf.last_size:
            return  # no change
        # Read from last_size onward
        try:
            with wf.path.open("rb") as f:
                f.seek(wf.last_size)
                new_bytes = f.read()
        except OSError:
            return
        wf.last_mtime = stat.st_mtime
        wf.last_size = stat.st_size
        # Parse new lines (incomplete trailing line is skipped — picked up on next poll)
        try:
            text = new_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return
        for line in text.split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            self._process_entry(session_id, wf, entry)

    def _process_entry(self, session_id: str, wf: _WatchedFile, entry: dict) -> None:
        if is_real_user_message(entry):
            text = self._extract_user_text(entry)
            if text:
                wf.cached_user_prompts.append(text)
                if len(wf.cached_user_prompts) > self.max_prose_per_session:
                    wf.cached_user_prompts = wf.cached_user_prompts[-self.max_prose_per_session:]
                if self._on_new_user_prompt:
                    try:
                        self._on_new_user_prompt(session_id, text)
                    except Exception as e:
                        logging.debug("on_new_user_prompt callback error: %s", e)
        elif entry.get("type") == "assistant":
            content = entry.get("message", {}).get("content", [])
            if isinstance(content, list):
                buf = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        t = (c.get("text") or "").strip()
                        if t and not any(t.startswith(p) for p in _SKIP_PROSE_PREFIXES):
                            buf.append(t)
                if buf:
                    prose = "\n".join(buf)
                    wf.cached_prose.append(prose)
                    if len(wf.cached_prose) > self.max_prose_per_session:
                        wf.cached_prose = wf.cached_prose[-self.max_prose_per_session:]
                    if self._on_new_prose:
                        try:
                            self._on_new_prose(session_id, prose)
                        except Exception as e:
                            logging.debug("on_new_prose callback error: %s", e)

    def _extract_user_text(self, entry: dict) -> str:
        content = entry.get("message", {}).get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            texts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    t = c.get("text", "")
                    if t:
                        texts.append(t)
            return "\n".join(texts).strip()
        return ""
