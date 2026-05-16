"""
AudioJobRegistry — in-memory ring buffer of recent audio jobs.

Every audio job born from a hook, buddy inject, or direct synth
gets registered here. Each gate the job passes through (audibility
check, routing decision, synth, publish) appends a StateTransition.
Terminal states (played, skipped, errored) freeze the job's
state_history.

The registry is queryable:

  - registry.get(job_id)        -> the full AudioJob with trace
  - registry.recent(limit)      -> last N jobs (any session)
  - registry.recent_for_session -> last N jobs for one session

Drives:

  - GET /api/audio-jobs/recent (Phase 3)
  - GET /api/audio-jobs/{job_id} (Phase 3)
  - Pro Android Diagnostics audio trace view (Phase 5)
  - Webui Diagnostics tab (Phase 5)

NOT persisted to SQLite — these are diagnostic ephemera, not user
config. The ring buffer evicts older jobs to keep memory bounded.
If a persistent audit log is needed later, add it as a separate
sink.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Deque, Dict, List, Optional

from claude_code_talker.schemas import (
    AudioJob,
    AudioJobState,
    StateTransition,
    VoiceConfig,
)


DEFAULT_RING_BUFFER_SIZE = 200


class AudioJobRegistry:
    """
    Bounded in-memory registry. Thread-safe. The audio worker, hook
    handlers, and inject endpoint all interact with the same
    instance constructed at daemon startup.
    """

    def __init__(self, max_size: int = DEFAULT_RING_BUFFER_SIZE) -> None:
        self._max_size = max_size
        self._lock = threading.Lock()
        # Ordered ring of (job_id, AudioJob). Newest at the right.
        self._ring: Deque[str] = deque(maxlen=max_size)
        self._jobs: Dict[str, AudioJob] = {}

    # ------------------------------------------------------------------
    # Creation + transitions.
    # ------------------------------------------------------------------

    def create(
        self,
        session_id: str,
        text: str,
        voice: VoiceConfig,
        *,
        _now_fn=time.time,
    ) -> AudioJob:
        """Register a brand-new job. State starts at 'created'."""
        job_id = uuid.uuid4().hex
        now = _now_fn()
        job = AudioJob(
            job_id=job_id,
            session_id=session_id,
            text=text,
            voice=voice,
            state="created",
            state_history=[],
            created_at=now,
        )
        with self._lock:
            if len(self._ring) == self._ring.maxlen:
                # Ring full: oldest job_id gets evicted from the
                # deque, drop from the jobs dict too.
                evicted = self._ring[0]
                self._jobs.pop(evicted, None)
            self._ring.append(job_id)
            self._jobs[job_id] = job
        return job

    def transition(
        self,
        job_id: str,
        *,
        to_state: AudioJobState,
        gate: str,
        reason: Optional[str] = None,
        publish_key: Optional[str] = None,
        bytes_synthesized: Optional[int] = None,
        error: Optional[str] = None,
        _now_fn=time.time,
    ) -> Optional[AudioJob]:
        """
        Advance a job to a new state. Records the transition with
        gate + reason. Returns the updated job, or None if the
        job_id has been evicted.

        Idempotent on terminal states: once played/skipped/errored,
        further transitions are recorded but the terminal state
        stays.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            now = _now_fn()
            transition = StateTransition(
                from_state=job.state,
                to_state=to_state,
                at=now,
                gate=gate,
                reason=reason,
            )
            updated = job.model_copy(
                update={
                    "state": to_state,
                    "state_history": job.state_history + [transition],
                    "publish_key": publish_key if publish_key is not None else job.publish_key,
                    "bytes_synthesized": bytes_synthesized if bytes_synthesized is not None else job.bytes_synthesized,
                    "error": error if error is not None else job.error,
                }
            )
            self._jobs[job_id] = updated
            return updated

    # ------------------------------------------------------------------
    # Read methods.
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Optional[AudioJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 50) -> List[AudioJob]:
        """Newest-first list of up to `limit` jobs."""
        with self._lock:
            return [
                self._jobs[jid]
                for jid in list(self._ring)[::-1][:limit]
                if jid in self._jobs
            ]

    def recent_for_session(self, session_id: str, limit: int = 20) -> List[AudioJob]:
        """Newest-first list of jobs for one session."""
        with self._lock:
            out = []
            for jid in list(self._ring)[::-1]:
                job = self._jobs.get(jid)
                if job is None:
                    continue
                if job.session_id == session_id:
                    out.append(job)
                if len(out) >= limit:
                    break
            return out

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)
