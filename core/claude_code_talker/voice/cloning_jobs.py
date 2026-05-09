"""Phase 25c — voice cloning job tracker with sidecar JSON persistence.

A lightweight tracker for voice-cloning jobs.  In Phase 25c v1 the job
is set to "succeeded" immediately (stub clone path) — Phase 25b will
plug a real cloner that runs asynchronously and updates state via
``set_running`` / ``set_succeeded`` / ``set_failed``.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CloneJob:
    job_id: str
    character_id: str
    mime_type: str
    status: str  # queued | running | succeeded | failed
    voice_ref: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class CloneJobTracker:
    """Persist clone-voice job state as one JSON file per job under *root*."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _save(self, job: CloneJob) -> None:
        job.updated_at = time.time()
        self._path(job.job_id).write_text(json.dumps(asdict(job)), encoding="utf-8")

    def create(self, character_id: str, _audio: bytes, mime_type: str) -> CloneJob:
        job_id = uuid.uuid4().hex[:12]
        job = CloneJob(
            job_id=job_id,
            character_id=character_id,
            mime_type=mime_type,
            status="queued",
        )
        self._save(job)
        return job

    def get(self, job_id: str) -> CloneJob | None:
        p = self._path(job_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return CloneJob(**data)

    def set_running(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "running"
        self._save(job)

    def set_succeeded(self, job_id: str, voice_ref: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "succeeded"
        job.voice_ref = voice_ref
        self._save(job)

    def set_failed(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "failed"
        job.error = error
        self._save(job)
