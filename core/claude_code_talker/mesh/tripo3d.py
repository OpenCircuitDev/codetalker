"""Phase 25b — Tripo3D adapter.

Tripo3D v2 generates 3D meshes from text or image prompts. API uses Bearer
auth and JSON bodies. Job IDs are returned in ``data.task_id``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .provider import Mesh3DProvider, MeshJobStatus

BASE = "https://api.tripo3d.ai/v2/openapi"


class Tripo3DProvider(Mesh3DProvider):
    name = "tripo3d"

    def __init__(self, api_key: str, timeout: float = 60.0):
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def start(self, *, prompt: str, image_url: str | None = None, **opts: Any) -> str:
        body: dict[str, Any]
        if image_url:
            body = {"type": "image_to_model", "file": {"url": image_url}, "prompt": prompt}
        else:
            body = {"type": "text_to_model", "prompt": prompt}
        for k, v in opts.items():
            body[k] = v
        r = self._client.post(f"{BASE}/task", headers=self._headers(), json=body)
        r.raise_for_status()
        return (r.json().get("data") or {}).get("task_id") or ""

    def poll(self, job_id: str) -> MeshJobStatus:
        r = self._client.get(f"{BASE}/task/{job_id}", headers=self._headers())
        r.raise_for_status()
        data = r.json().get("data") or {}
        s = (data.get("status") or "").lower()
        if s in ("queued", "pending"):
            return MeshJobStatus("tripo3d", job_id, "queued", raw=data)
        if s in ("running", "processing"):
            return MeshJobStatus(
                "tripo3d",
                job_id,
                "running",
                progress=(data.get("progress") or 0) / 100,
                raw=data,
            )
        if s in ("success", "succeeded"):
            url = (data.get("output") or {}).get("model")
            return MeshJobStatus("tripo3d", job_id, "succeeded", model_url=url, raw=data)
        if s in ("failed", "error"):
            return MeshJobStatus(
                "tripo3d",
                job_id,
                "failed",
                error=data.get("error") or "failed",
                raw=data,
            )
        return MeshJobStatus("tripo3d", job_id, "running", raw=data)

    def _fetch_url(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dest

    def download(self, job_id: str, dest: Path) -> Path:
        s = self.poll(job_id)
        if s.status != "succeeded" or not s.model_url:
            raise RuntimeError(f"tripo3d job {job_id} not ready ({s.status})")
        suffix = s.model_url.rsplit(".", 1)[-1].lower()
        if not dest.suffix:
            dest = dest.with_suffix(f".{suffix}")
        return self._fetch_url(s.model_url, dest)
