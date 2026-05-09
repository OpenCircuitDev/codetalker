"""Phase 25b — Mesh3DProvider abstract base class + MeshJobStatus."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JobStatus = str  # "queued" | "running" | "succeeded" | "failed"


@dataclass
class MeshJobStatus:
    provider: str
    job_id: str
    status: JobStatus
    model_url: str | None = None
    progress: float | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("succeeded", "failed")


class Mesh3DProvider(ABC):
    name: str = ""

    @abstractmethod
    def start(self, *, prompt: str, image_url: str | None = None, **opts: Any) -> str:
        """Submit a job, return provider-side job_id."""

    @abstractmethod
    def poll(self, job_id: str) -> MeshJobStatus:
        """Get latest status."""

    @abstractmethod
    def download(self, job_id: str, dest: Path) -> Path:
        """Stream the model to ``dest``, return the final path (may include extension)."""
