"""Phase 25b — MeshJobTracker with crash-safe sidecar JSON.

Each job is persisted as ``<root>/<job_id>.json`` so an in-flight job
survives daemon restarts and can be reattached to a polling loop.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MeshJob:
    job_id: str
    provider: str
    character_id: str
    prompt: str
    status: str = "queued"
    provider_job_id: str | None = None
    model_path: str | None = None
    progress: float | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class MeshJobTracker:
    """File-backed job tracker. One JSON sidecar per job."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _save(self, job: MeshJob) -> None:
        job.updated_at = time.time()
        tmp = self._path(job.job_id).with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(asdict(job)), encoding="utf-8")
            tmp.replace(self._path(job.job_id))
        except OSError:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise

    def create(self, *, provider: str, character_id: str, prompt: str) -> MeshJob:
        job_id = uuid.uuid4().hex[:12]
        job = MeshJob(
            job_id=job_id,
            provider=provider,
            character_id=character_id,
            prompt=prompt,
        )
        self._save(job)
        return job

    def get(self, job_id: str) -> MeshJob | None:
        p = self._path(job_id)
        if not p.exists():
            return None
        try:
            return MeshJob(**json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return None

    def list(self) -> list[MeshJob]:
        out: list[MeshJob] = []
        for p in sorted(self.root.glob("*.json")):
            try:
                out.append(MeshJob(**json.loads(p.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError, OSError):
                continue
        return out

    def set_provider_job_id(self, job_id: str, pid: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.provider_job_id = pid
        self._save(job)

    def set_status(self, job_id: str, status: str, progress: float | None = None) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = status
        if progress is not None:
            job.progress = progress
        self._save(job)

    def set_succeeded(self, job_id: str, model_path: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "succeeded"
        job.model_path = model_path
        self._save(job)

    def set_failed(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "failed"
        job.error = error
        self._save(job)
