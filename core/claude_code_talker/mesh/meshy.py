"""Phase 25b — Meshy v2 adapter.

Meshy v2 generates 3D meshes from text prompts (preview pass, optional refine
pass). API uses Bearer auth and JSON bodies. Job IDs are returned in the
``result`` field of the submit response.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .provider import Mesh3DProvider, MeshJobStatus

BASE = "https://api.meshy.ai/openapi/v2"


class MeshyProvider(Mesh3DProvider):
    name = "meshy"

    def __init__(self, api_key: str, timeout: float = 60.0):
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def start(self, *, prompt: str, image_url: str | None = None, **opts: Any) -> str:
        body: dict[str, Any] = {"mode": "preview", "prompt": prompt}
        if image_url:
            body["image_url"] = image_url
        for k in ("negative_prompt", "art_style", "ai_model"):
            if k in opts:
                body[k] = opts[k]
        r = self._client.post(f"{BASE}/text-to-3d", headers=self._headers(), json=body)
        r.raise_for_status()
        return r.json().get("result") or ""

    def poll(self, job_id: str) -> MeshJobStatus:
        r = self._client.get(f"{BASE}/text-to-3d/{job_id}", headers=self._headers())
        r.raise_for_status()
        data = r.json()
        s = (data.get("status") or "").upper()
        if s in ("PENDING", "QUEUED"):
            return MeshJobStatus("meshy", job_id, "queued", raw=data)
        if s == "IN_PROGRESS":
            return MeshJobStatus(
                "meshy",
                job_id,
                "running",
                progress=(data.get("progress") or 0) / 100,
                raw=data,
            )
        if s == "SUCCEEDED":
            urls = data.get("model_urls") or {}
            url = urls.get("glb") or urls.get("fbx") or urls.get("usdz")
            return MeshJobStatus("meshy", job_id, "succeeded", model_url=url, raw=data)
        if s == "FAILED":
            err = (data.get("task_error") or {}).get("message") or "failed"
            return MeshJobStatus("meshy", job_id, "failed", error=err, raw=data)
        return MeshJobStatus("meshy", job_id, "running", raw=data)

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
            raise RuntimeError(f"meshy job {job_id} not ready ({s.status})")
        from .provider import extension_from_url
        if not dest.suffix or "?" in dest.name:
            dest = dest.with_name(f"{dest.stem}.{extension_from_url(s.model_url)}")
        return self._fetch_url(s.model_url, dest)
