"""Phase 25b — Hyper3D Rodin Gen-2 adapter.

Hyper3D Rodin Gen-2 generates 3D meshes from text/image prompts. The API uses
multipart form posts with a Bearer token. Job IDs are UUIDs returned in the
``uuid`` field on submit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .provider import Mesh3DProvider, MeshJobStatus

BASE = "https://hyperhuman.deemos.com/api/v2"


class Hyper3DProvider(Mesh3DProvider):
    name = "hyper3d"

    def __init__(self, api_key: str, timeout: float = 60.0):
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def start(self, *, prompt: str, image_url: str | None = None, **opts: Any) -> str:
        files: dict = {"prompt": (None, prompt)}
        if image_url:
            files["image"] = (None, image_url)
        for k, v in opts.items():
            files[k] = (None, str(v))
        r = self._client.post(f"{BASE}/rodin", headers=self._headers(), files=files)
        r.raise_for_status()
        data = r.json()
        return data.get("uuid") or data.get("job_id") or ""

    def poll(self, job_id: str) -> MeshJobStatus:
        r = self._client.post(
            f"{BASE}/status",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"subscription_key": job_id},
        )
        r.raise_for_status()
        body = r.json()
        jobs = body.get("jobs") or []
        if not jobs:
            return MeshJobStatus("hyper3d", job_id, "queued", raw=body)
        j = jobs[0]
        s = (j.get("status") or "").lower()
        if s in ("queued", "waiting"):
            return MeshJobStatus("hyper3d", job_id, "queued", raw=j)
        if s in ("generating", "processing", "running"):
            return MeshJobStatus("hyper3d", job_id, "running", raw=j)
        if s in ("done", "succeeded"):
            d = self._client.post(
                f"{BASE}/download",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"task_uuid": job_id},
            )
            d.raise_for_status()
            items = d.json().get("list") or []
            url = items[0].get("url") if items else None
            return MeshJobStatus("hyper3d", job_id, "succeeded", model_url=url, raw=j)
        if s in ("failed", "error"):
            return MeshJobStatus(
                "hyper3d",
                job_id,
                "failed",
                error=j.get("msg") or j.get("error") or "failed",
                raw=j,
            )
        return MeshJobStatus("hyper3d", job_id, "running", raw=j)

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
            raise RuntimeError(f"hyper3d job {job_id} not ready ({s.status})")
        from .provider import extension_from_url
        if not dest.suffix or "?" in dest.name:
            dest = dest.with_name(f"{dest.stem}.{extension_from_url(s.model_url)}")
        return self._fetch_url(s.model_url, dest)
