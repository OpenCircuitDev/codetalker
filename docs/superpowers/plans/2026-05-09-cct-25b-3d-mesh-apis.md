# CCT Phase 25b — 3D Mesh APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**⚠️ API KEYS REQUIRED:** Task 13 (real-key smoke test) is a **manual gate**. The user must provide Hyper3D, Meshy, or Tripo3D API keys before that task. All other tasks pass on mocked HTTP.

**Goal:** Add `Mesh3DProvider` ABC + three adapters (Hyper3D Rodin Gen-2, Meshy v2, Tripo3D v2) plus a `MeshJobTracker` with sidecar persistence and 5 REST endpoints, giving Characters a `mesh_path` populated from a text-or-image prompt.

**Architecture:** New `core/claude_code_talker/mesh/` package. `provider.py` defines the `Mesh3DProvider` ABC. Each adapter (`hyper3d.py`, `meshy.py`, `tripo3d.py`) implements `start(prompt, ...) → job_id`, `poll(job_id) → MeshJobStatus`, `download(job_id, dest) → Path`. `MeshJobTracker` persists job sidecars to `~/.claude/scripts/codetalker/models/_jobs/<job_id>.json` for crash recovery. REST endpoints surface jobs to the React UI. API keys live in the existing keychain via `secrets_store` (extended).

**Tech Stack:** Python 3.11+, `httpx` (already in pyproject), `pydantic` for response models (optional), pytest with `respx` for HTTP mocking.

**Reference spec:** [docs/superpowers/specs/2026-05-09-cct-25b-3d-mesh-apis-design.md](../specs/2026-05-09-cct-25b-3d-mesh-apis-design.md) — read before starting.

**File structure**:
```
core/claude_code_talker/mesh/                  # NEW package (~700 LOC total)
├── __init__.py
├── provider.py            # Mesh3DProvider ABC + MeshJobStatus dataclass
├── hyper3d.py             # Hyper3D Rodin Gen-2 adapter
├── meshy.py               # Meshy v2 adapter
├── tripo3d.py             # Tripo3D v2 adapter
├── tracker.py             # MeshJobTracker with sidecar JSON
└── registry.py            # provider name → class

core/claude_code_talker/
├── secrets_store.py       # MODIFY — add hyper3d_api_key, meshy_api_key, tripo3d_api_key
├── server.py              # MODIFY — wire MeshJobTracker into ServerState
└── api.py                 # MODIFY — 5 new mesh REST routes

core/claude_code_talker/webui/src/features/characters/
└── MeshGenerator.tsx      # NEW — provider+prompt picker, kicked from CharacterDetail

core/tests/
├── test_mesh_provider_abc.py     # NEW — 3 tests
├── test_mesh_hyper3d.py          # NEW — 6 tests
├── test_mesh_meshy.py            # NEW — 5 tests
├── test_mesh_tripo3d.py          # NEW — 5 tests
├── test_mesh_tracker.py          # NEW — 6 tests
└── test_api_mesh.py              # NEW — 4 tests
```

---

## Task 1: Mesh3DProvider ABC + MeshJobStatus dataclass (TDD)

**Files:**
- Create: `core/claude_code_talker/mesh/__init__.py`
- Create: `core/claude_code_talker/mesh/provider.py`
- Create: `core/tests/test_mesh_provider_abc.py`

- [ ] **Step 1: Write failing tests**

```python
"""Phase 25b — Mesh3DProvider ABC tests."""
from __future__ import annotations

import pytest

from claude_code_talker.mesh.provider import Mesh3DProvider, MeshJobStatus


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        Mesh3DProvider()  # cannot instantiate


def test_mesh_job_status_default_status_is_queued():
    s = MeshJobStatus(provider="x", job_id="j", status="queued")
    assert s.status == "queued"
    assert s.model_url is None


def test_mesh_job_status_terminal_helpers():
    queued = MeshJobStatus("x", "j", "queued")
    running = MeshJobStatus("x", "j", "running")
    succeeded = MeshJobStatus("x", "j", "succeeded", model_url="https://...")
    failed = MeshJobStatus("x", "j", "failed", error="boom")
    assert not queued.is_terminal
    assert not running.is_terminal
    assert succeeded.is_terminal
    assert failed.is_terminal
```

- [ ] **Step 2: Implement provider.py**

```python
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
        """Stream the model to `dest`, return the final path (may include extension)."""
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_mesh_provider_abc.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/mesh/__init__.py core/claude_code_talker/mesh/provider.py core/tests/test_mesh_provider_abc.py
git commit -m "feat(mesh): Mesh3DProvider ABC + MeshJobStatus (Phase 25b Task 1)"
```

---

## Task 2: secrets_store.py — add three new key slots (TDD)

**Files:**
- Modify: `core/claude_code_talker/secrets_store.py`
- Modify: `core/tests/test_secrets_store.py` (or create if missing)

- [ ] **Step 1: Add slots**

In `secrets_store.py`, find the existing list of supported secret keys and add:

```python
SUPPORTED_KEYS = {
    # ... existing ...
    "hyper3d_api_key",
    "meshy_api_key",
    "tripo3d_api_key",
}
```

Or wherever the validation lives. If the store is generic (any string key), add only test coverage.

- [ ] **Step 2: Add a test for the new slots**

```python
def test_secrets_store_accepts_mesh_provider_keys(tmp_path):
    from claude_code_talker.secrets_store import SecretsStore
    s = SecretsStore(tmp_path / "secrets")
    s.set("hyper3d_api_key", "sk-1")
    s.set("meshy_api_key", "sk-2")
    s.set("tripo3d_api_key", "sk-3")
    assert s.get("hyper3d_api_key") == "sk-1"
```

Run: `pytest core/tests/test_secrets_store.py -v`

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/secrets_store.py core/tests/test_secrets_store.py
git commit -m "feat(secrets): add hyper3d/meshy/tripo3d api_key slots (Phase 25b Task 2)"
```

---

## Task 3: MeshJobTracker (TDD)

**Files:**
- Create: `core/claude_code_talker/mesh/tracker.py`
- Create: `core/tests/test_mesh_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
"""Phase 25b — MeshJobTracker tests."""
from __future__ import annotations

import pytest

from claude_code_talker.mesh.tracker import MeshJob, MeshJobTracker


def test_create_persists_a_job(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="hyper3d", character_id="char-buddy", prompt="a fox")
    assert job.status == "queued"
    assert job.provider == "hyper3d"
    assert job.character_id == "char-buddy"


def test_set_provider_job_id_updates_record(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="hyper3d", character_id="x", prompt="x")
    t.set_provider_job_id(job.job_id, "hyper3d-abc")
    assert t.get(job.job_id).provider_job_id == "hyper3d-abc"


def test_set_status_running(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="meshy", character_id="x", prompt="x")
    t.set_status(job.job_id, "running", progress=0.5)
    assert t.get(job.job_id).status == "running"
    assert t.get(job.job_id).progress == 0.5


def test_set_succeeded_records_model_path(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="meshy", character_id="x", prompt="x")
    t.set_succeeded(job.job_id, model_path=str(tmp_path / "x.glb"))
    j = t.get(job.job_id)
    assert j.status == "succeeded"
    assert j.model_path.endswith("x.glb")


def test_set_failed_records_error(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="meshy", character_id="x", prompt="x")
    t.set_failed(job.job_id, error="api down")
    j = t.get(job.job_id)
    assert j.status == "failed"
    assert j.error == "api down"


def test_persists_across_instances(tmp_path):
    t1 = MeshJobTracker(tmp_path)
    job = t1.create(provider="tripo3d", character_id="x", prompt="x")
    t2 = MeshJobTracker(tmp_path)
    assert t2.get(job.job_id) is not None
```

- [ ] **Step 2: Implement tracker**

```python
"""Phase 25b — MeshJobTracker with crash-safe sidecar JSON."""
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
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _save(self, job: MeshJob) -> None:
        job.updated_at = time.time()
        self._path(job.job_id).write_text(json.dumps(asdict(job)), encoding="utf-8")

    def create(self, *, provider: str, character_id: str, prompt: str) -> MeshJob:
        job_id = uuid.uuid4().hex[:12]
        job = MeshJob(job_id=job_id, provider=provider, character_id=character_id, prompt=prompt)
        self._save(job)
        return job

    def get(self, job_id: str) -> MeshJob | None:
        p = self._path(job_id)
        if not p.exists():
            return None
        return MeshJob(**json.loads(p.read_text(encoding="utf-8")))

    def list(self) -> list[MeshJob]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            try:
                out.append(MeshJob(**json.loads(p.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def set_provider_job_id(self, job_id: str, pid: str) -> None:
        job = self.get(job_id)
        if not job: return
        job.provider_job_id = pid
        self._save(job)

    def set_status(self, job_id: str, status: str, progress: float | None = None) -> None:
        job = self.get(job_id)
        if not job: return
        job.status = status
        if progress is not None:
            job.progress = progress
        self._save(job)

    def set_succeeded(self, job_id: str, model_path: str) -> None:
        job = self.get(job_id)
        if not job: return
        job.status = "succeeded"
        job.model_path = model_path
        self._save(job)

    def set_failed(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if not job: return
        job.status = "failed"
        job.error = error
        self._save(job)
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_mesh_tracker.py -v`
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/mesh/tracker.py core/tests/test_mesh_tracker.py
git commit -m "feat(mesh): MeshJobTracker with sidecar persistence (Phase 25b Task 3)"
```

---

## Task 4: Hyper3D adapter (TDD with respx)

**Files:**
- Create: `core/claude_code_talker/mesh/hyper3d.py`
- Create: `core/tests/test_mesh_hyper3d.py`

- [ ] **Step 1: Install respx if missing**

Run: `pip show respx || pip install respx`

- [ ] **Step 2: Write failing tests with respx mocks**

```python
"""Phase 25b — Hyper3D Rodin Gen-2 adapter tests."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from claude_code_talker.mesh.hyper3d import Hyper3DProvider


@pytest.fixture
def provider():
    return Hyper3DProvider(api_key="test-key")


@respx.mock
def test_start_posts_to_rodin_with_prompt(provider):
    route = respx.post("https://hyperhuman.deemos.com/api/v2/rodin").mock(
        return_value=httpx.Response(200, json={"uuid": "abc-123", "subscription_key": "sub-456"})
    )
    job_id = provider.start(prompt="a fox sitting on a log")
    assert job_id == "abc-123"
    assert route.called


@respx.mock
def test_start_passes_image_url_when_provided(provider):
    captured = {}
    def cap(req):
        captured["body"] = req.read()
        return httpx.Response(200, json={"uuid": "abc"})
    respx.post("https://hyperhuman.deemos.com/api/v2/rodin").mock(side_effect=cap)
    provider.start(prompt="x", image_url="https://img/foo.png")
    assert b"image" in captured["body"]


@respx.mock
def test_poll_returns_running(provider):
    respx.post("https://hyperhuman.deemos.com/api/v2/status").mock(
        return_value=httpx.Response(200, json={"jobs": [{"uuid": "abc", "status": "Generating"}]})
    )
    s = provider.poll("abc")
    assert s.status == "running"


@respx.mock
def test_poll_returns_succeeded_with_model_url(provider):
    respx.post("https://hyperhuman.deemos.com/api/v2/status").mock(
        return_value=httpx.Response(200, json={"jobs": [{"uuid": "abc", "status": "Done"}]})
    )
    respx.post("https://hyperhuman.deemos.com/api/v2/download").mock(
        return_value=httpx.Response(200, json={"list": [{"name": "model.glb", "url": "https://cdn/x.glb"}]})
    )
    s = provider.poll("abc")
    assert s.status == "succeeded"
    assert s.model_url == "https://cdn/x.glb"


@respx.mock
def test_poll_failure_status(provider):
    respx.post("https://hyperhuman.deemos.com/api/v2/status").mock(
        return_value=httpx.Response(200, json={"jobs": [{"uuid": "abc", "status": "Failed", "msg": "bad prompt"}]})
    )
    s = provider.poll("abc")
    assert s.status == "failed"
    assert "bad prompt" in (s.error or "")


@respx.mock
def test_download_streams_to_disk(tmp_path, provider):
    # Stub download URL to return bytes
    respx.get("https://cdn/x.glb").mock(return_value=httpx.Response(200, content=b"GLB-BYTES"))
    p = provider._fetch_url("https://cdn/x.glb", tmp_path / "out.glb")
    assert p.exists()
    assert p.read_bytes() == b"GLB-BYTES"
```

- [ ] **Step 3: Implement hyper3d.py**

```python
"""Phase 25b — Hyper3D Rodin Gen-2 adapter."""
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
            return MeshJobStatus("hyper3d", job_id, "failed", error=j.get("msg") or j.get("error") or "failed", raw=j)
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
        suffix = s.model_url.rsplit(".", 1)[-1].lower()
        if not dest.suffix:
            dest = dest.with_suffix(f".{suffix}")
        return self._fetch_url(s.model_url, dest)
```

- [ ] **Step 4: Tests pass**

Run: `pytest core/tests/test_mesh_hyper3d.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/mesh/hyper3d.py core/tests/test_mesh_hyper3d.py
git commit -m "feat(mesh): Hyper3D Rodin Gen-2 adapter (Phase 25b Task 4)"
```

---

## Task 5: Meshy adapter (TDD)

**Files:**
- Create: `core/claude_code_talker/mesh/meshy.py`
- Create: `core/tests/test_mesh_meshy.py`

- [ ] **Step 1: Write failing tests**

```python
"""Phase 25b — Meshy v2 adapter tests."""
from __future__ import annotations

import httpx
import pytest
import respx

from claude_code_talker.mesh.meshy import MeshyProvider


@pytest.fixture
def provider():
    return MeshyProvider(api_key="m-test")


@respx.mock
def test_start_text_to_3d(provider):
    respx.post("https://api.meshy.ai/openapi/v2/text-to-3d").mock(
        return_value=httpx.Response(200, json={"result": "task-789"})
    )
    job_id = provider.start(prompt="a robot")
    assert job_id == "task-789"


@respx.mock
def test_poll_running(provider):
    respx.get("https://api.meshy.ai/openapi/v2/text-to-3d/task-789").mock(
        return_value=httpx.Response(200, json={"status": "IN_PROGRESS", "progress": 42})
    )
    s = provider.poll("task-789")
    assert s.status == "running"
    assert s.progress == 0.42


@respx.mock
def test_poll_succeeded_extracts_glb_url(provider):
    respx.get("https://api.meshy.ai/openapi/v2/text-to-3d/task-789").mock(
        return_value=httpx.Response(200, json={
            "status": "SUCCEEDED",
            "model_urls": {"glb": "https://meshy.cdn/m.glb", "fbx": "https://meshy.cdn/m.fbx"},
        })
    )
    s = provider.poll("task-789")
    assert s.status == "succeeded"
    assert s.model_url == "https://meshy.cdn/m.glb"


@respx.mock
def test_poll_failed(provider):
    respx.get("https://api.meshy.ai/openapi/v2/text-to-3d/task-789").mock(
        return_value=httpx.Response(200, json={"status": "FAILED", "task_error": {"message": "rate limit"}})
    )
    s = provider.poll("task-789")
    assert s.status == "failed"
    assert "rate limit" in (s.error or "")


@respx.mock
def test_start_passes_negative_prompt(provider):
    captured = {}
    def cap(req):
        import json
        captured["body"] = json.loads(req.read())
        return httpx.Response(200, json={"result": "x"})
    respx.post("https://api.meshy.ai/openapi/v2/text-to-3d").mock(side_effect=cap)
    provider.start(prompt="hero", negative_prompt="ugly")
    assert captured["body"]["negative_prompt"] == "ugly"
```

- [ ] **Step 2: Implement meshy.py**

```python
"""Phase 25b — Meshy v2 adapter."""
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
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

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
            return MeshJobStatus("meshy", job_id, "running",
                                 progress=(data.get("progress") or 0) / 100,
                                 raw=data)
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
        suffix = s.model_url.rsplit(".", 1)[-1].lower()
        if not dest.suffix:
            dest = dest.with_suffix(f".{suffix}")
        return self._fetch_url(s.model_url, dest)
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_mesh_meshy.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/mesh/meshy.py core/tests/test_mesh_meshy.py
git commit -m "feat(mesh): Meshy v2 adapter (Phase 25b Task 5)"
```

---

## Task 6: Tripo3D adapter (TDD)

**Files:**
- Create: `core/claude_code_talker/mesh/tripo3d.py`
- Create: `core/tests/test_mesh_tripo3d.py`

- [ ] **Step 1: Write failing tests**

```python
"""Phase 25b — Tripo3D adapter tests."""
from __future__ import annotations

import httpx
import pytest
import respx

from claude_code_talker.mesh.tripo3d import Tripo3DProvider


@pytest.fixture
def provider():
    return Tripo3DProvider(api_key="t-test")


@respx.mock
def test_start_text_to_model(provider):
    respx.post("https://api.tripo3d.ai/v2/openapi/task").mock(
        return_value=httpx.Response(200, json={"data": {"task_id": "t-001"}})
    )
    job_id = provider.start(prompt="a sword")
    assert job_id == "t-001"


@respx.mock
def test_poll_running(provider):
    respx.get("https://api.tripo3d.ai/v2/openapi/task/t-001").mock(
        return_value=httpx.Response(200, json={"data": {"status": "running", "progress": 30}})
    )
    s = provider.poll("t-001")
    assert s.status == "running"
    assert s.progress == 0.3


@respx.mock
def test_poll_succeeded(provider):
    respx.get("https://api.tripo3d.ai/v2/openapi/task/t-001").mock(
        return_value=httpx.Response(200, json={"data": {
            "status": "success",
            "output": {"model": "https://tripo.cdn/m.glb"},
        }})
    )
    s = provider.poll("t-001")
    assert s.status == "succeeded"
    assert s.model_url == "https://tripo.cdn/m.glb"


@respx.mock
def test_poll_failed(provider):
    respx.get("https://api.tripo3d.ai/v2/openapi/task/t-001").mock(
        return_value=httpx.Response(200, json={"data": {"status": "failed", "error": "bad input"}})
    )
    s = provider.poll("t-001")
    assert s.status == "failed"


@respx.mock
def test_start_with_image_url_uses_image_to_model(provider):
    captured = {}
    def cap(req):
        import json
        captured["body"] = json.loads(req.read())
        return httpx.Response(200, json={"data": {"task_id": "t-img"}})
    respx.post("https://api.tripo3d.ai/v2/openapi/task").mock(side_effect=cap)
    provider.start(prompt="x", image_url="https://img/x.png")
    assert captured["body"]["type"] == "image_to_model"
```

- [ ] **Step 2: Implement tripo3d.py**

```python
"""Phase 25b — Tripo3D adapter."""
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
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

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
        data = (r.json().get("data") or {})
        s = (data.get("status") or "").lower()
        if s in ("queued", "pending"):
            return MeshJobStatus("tripo3d", job_id, "queued", raw=data)
        if s in ("running", "processing"):
            return MeshJobStatus("tripo3d", job_id, "running",
                                 progress=(data.get("progress") or 0) / 100,
                                 raw=data)
        if s in ("success", "succeeded"):
            url = (data.get("output") or {}).get("model")
            return MeshJobStatus("tripo3d", job_id, "succeeded", model_url=url, raw=data)
        if s in ("failed", "error"):
            return MeshJobStatus("tripo3d", job_id, "failed", error=data.get("error") or "failed", raw=data)
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
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_mesh_tripo3d.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/mesh/tripo3d.py core/tests/test_mesh_tripo3d.py
git commit -m "feat(mesh): Tripo3D adapter (Phase 25b Task 6)"
```

---

## Task 7: Provider registry

**Files:**
- Create: `core/claude_code_talker/mesh/registry.py`

- [ ] **Step 1: Implement**

```python
"""Phase 25b — provider registry by name."""
from __future__ import annotations

from .hyper3d import Hyper3DProvider
from .meshy import MeshyProvider
from .provider import Mesh3DProvider
from .tripo3d import Tripo3DProvider


PROVIDERS: dict[str, type[Mesh3DProvider]] = {
    "hyper3d": Hyper3DProvider,
    "meshy": MeshyProvider,
    "tripo3d": Tripo3DProvider,
}


def make_provider(name: str, api_key: str) -> Mesh3DProvider:
    cls = PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"unknown mesh provider: {name}")
    return cls(api_key=api_key)
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/mesh/registry.py
git commit -m "feat(mesh): provider registry (Phase 25b Task 7)"
```

---

## Task 8: REST endpoints — 5 mesh routes (TDD)

**Files:**
- Modify: `core/claude_code_talker/api.py`
- Modify: `core/claude_code_talker/server.py` (wire MeshJobTracker)
- Create: `core/tests/test_api_mesh.py`

- [ ] **Step 1: Write failing API tests**

```python
"""Phase 25b — mesh REST tests with mocked providers."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from claude_code_talker.server import build_app
from claude_code_talker.mesh.provider import MeshJobStatus


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_TALKER_HOME", str(tmp_path))
    app = build_app()
    return TestClient(app)


def test_post_mesh_jobs_starts_a_job(client, monkeypatch):
    client.post("/api/characters", json={"id": "x", "display_name": "X", "voice_ref": "v"})
    monkeypatch.setattr(
        "claude_code_talker.mesh.registry.make_provider",
        lambda name, api_key: type("P", (), {
            "start": lambda self, **k: "p-job-1",
            "poll": lambda self, jid: MeshJobStatus(name, jid, "queued"),
        })(),
    )
    r = client.post("/api/mesh-jobs", json={"character_id": "x", "provider": "hyper3d", "prompt": "fox"})
    assert r.status_code == 202
    assert r.json()["status"] == "queued"


def test_get_mesh_job_returns_job(client):
    client.post("/api/characters", json={"id": "x", "display_name": "X", "voice_ref": "v"})
    # bypass real provider via a direct tracker call would be cleaner — patch make_provider as above
    # ... assert via list endpoint
    r = client.get("/api/mesh-jobs")
    assert r.status_code == 200


def test_get_unknown_mesh_job_404(client):
    assert client.get("/api/mesh-jobs/nope").status_code == 404


def test_post_mesh_jobs_unknown_character_404(client):
    r = client.post("/api/mesh-jobs", json={"character_id": "no", "provider": "hyper3d", "prompt": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Implement endpoints**

In `api.py`, add:

```python
from .mesh.registry import make_provider, PROVIDERS
from .mesh.provider import MeshJobStatus
from pathlib import Path


async def mesh_jobs_post(request: Request) -> Response:
    body = await request.json()
    cid = body.get("character_id")
    provider_name = body.get("provider")
    prompt = body.get("prompt") or ""
    image_url = body.get("image_url")
    if not cid or not provider_name or not prompt:
        return JSONResponse({"error": "character_id, provider, prompt required"}, status_code=400)
    if provider_name not in PROVIDERS:
        return JSONResponse({"error": f"unknown provider: {provider_name}"}, status_code=400)
    char = state.characters.get(cid)
    if not char:
        return JSONResponse({"error": "character not found"}, status_code=404)
    api_key = state.secrets.get(f"{provider_name}_api_key")
    if not api_key:
        return JSONResponse({"error": f"missing {provider_name}_api_key in keychain"}, status_code=400)

    job = state.mesh_jobs.create(provider=provider_name, character_id=cid, prompt=prompt)
    try:
        provider = make_provider(provider_name, api_key)
        pjid = provider.start(prompt=prompt, image_url=image_url)
        state.mesh_jobs.set_provider_job_id(job.job_id, pjid)
        # Update prompt history on character
        char.mesh_prompt = prompt
        history = list(char.mesh_prompt_history or [])
        history.append({"prompt": prompt, "provider": provider_name, "ts": time.time()})
        char.mesh_prompt_history = history[-20:]
        state.characters.save(char)
    except Exception as e:
        state.mesh_jobs.set_failed(job.job_id, error=str(e))
        return JSONResponse({"error": str(e)}, status_code=502)
    return JSONResponse({"job_id": job.job_id, "status": "queued"}, status_code=202)


async def mesh_jobs_get(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    job = state.mesh_jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "job not found"}, status_code=404)
    return JSONResponse(asdict(job))


async def mesh_jobs_list(request: Request) -> Response:
    return JSONResponse([asdict(j) for j in state.mesh_jobs.list()])


async def mesh_jobs_poll(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    job = state.mesh_jobs.get(job_id)
    if not job or not job.provider_job_id:
        return JSONResponse({"error": "job not ready to poll"}, status_code=404)
    api_key = state.secrets.get(f"{job.provider}_api_key")
    if not api_key:
        return JSONResponse({"error": "missing api key"}, status_code=400)
    provider = make_provider(job.provider, api_key)
    status = provider.poll(job.provider_job_id)
    if status.status == "running":
        state.mesh_jobs.set_status(job.job_id, "running", progress=status.progress)
    elif status.status == "succeeded":
        # download
        models_root = state.home / "models" / job.character_id
        models_root.mkdir(parents=True, exist_ok=True)
        ext = (status.model_url or "").rsplit(".", 1)[-1].lower()
        dest = models_root / f"{job.job_id}.{ext}"
        provider.download(job.provider_job_id, dest)
        state.mesh_jobs.set_succeeded(job.job_id, model_path=str(dest))
        char = state.characters.get(job.character_id)
        if char:
            char.mesh_path = str(dest)
            char.mesh_provider = job.provider
            state.characters.save(char)
    elif status.status == "failed":
        state.mesh_jobs.set_failed(job.job_id, error=status.error or "failed")
    return JSONResponse(asdict(state.mesh_jobs.get(job.job_id)))


async def mesh_providers_list(request: Request) -> Response:
    out = []
    for name in PROVIDERS:
        out.append({"name": name, "configured": bool(state.secrets.get(f"{name}_api_key"))})
    return JSONResponse(out)


routes.append(Route("/api/mesh-jobs", mesh_jobs_post, methods=["POST"]))
routes.append(Route("/api/mesh-jobs", mesh_jobs_list, methods=["GET"]))
routes.append(Route("/api/mesh-jobs/{job_id}", mesh_jobs_get, methods=["GET"]))
routes.append(Route("/api/mesh-jobs/{job_id}/poll", mesh_jobs_poll, methods=["POST"]))
routes.append(Route("/api/mesh-providers", mesh_providers_list, methods=["GET"]))
```

- [ ] **Step 3: Wire MeshJobTracker into ServerState**

In `server.py`:

```python
from .mesh.tracker import MeshJobTracker
state.mesh_jobs = MeshJobTracker(home / "models" / "_jobs")
```

- [ ] **Step 4: Tests pass**

Run: `pytest core/tests/test_api_mesh.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/api.py core/claude_code_talker/server.py core/tests/test_api_mesh.py
git commit -m "feat(api): 5 mesh REST endpoints (Phase 25b Task 8)"
```

---

## Task 9: MeshGenerator React component

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/MeshGenerator.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface Provider { name: string; configured: boolean }

async function listProviders(): Promise<Provider[]> {
  const r = await fetch("/api/mesh-providers");
  return r.json();
}

async function startMeshJob(input: { character_id: string; provider: string; prompt: string; image_url?: string }) {
  const r = await fetch("/api/mesh-jobs", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function pollMeshJob(jobId: string) {
  const r = await fetch(`/api/mesh-jobs/${jobId}/poll`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function MeshGenerator({ characterId }: { characterId: string }) {
  const [provider, setProvider] = useState("hyper3d");
  const [prompt, setPrompt] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const qc = useQueryClient();
  const { data: providers = [] } = useQuery({ queryKey: ["mesh-providers"], queryFn: listProviders });

  const start = useMutation({
    mutationFn: () => startMeshJob({ character_id: characterId, provider, prompt }),
    onSuccess: (j) => {
      setJobId(j.job_id); setStatus(j.status);
      const tick = setInterval(async () => {
        try {
          const fresh = await pollMeshJob(j.job_id);
          setStatus(fresh.status);
          if (fresh.status === "succeeded" || fresh.status === "failed") {
            clearInterval(tick);
            qc.invalidateQueries({ queryKey: ["characters"] });
          }
        } catch { clearInterval(tick); }
      }, 3000);
    },
  });

  return (
    <section className="space-y-2 border-t border-zinc-800 pt-3">
      <h3 className="font-bold text-sm">Generate 3D model</h3>
      <select value={provider} onChange={e => setProvider(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
        {providers.map(p => (
          <option key={p.name} value={p.name} disabled={!p.configured}>
            {p.name}{p.configured ? "" : " (no key)"}
          </option>
        ))}
      </select>
      <textarea
        value={prompt} onChange={e => setPrompt(e.target.value)}
        placeholder="describe the model"
        className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 h-20"
      />
      <button onClick={() => start.mutate()} disabled={!prompt || start.isPending} className="px-3 py-1 bg-cyan-600 text-white rounded disabled:opacity-50">
        {start.isPending ? "Starting…" : "Generate"}
      </button>
      {jobId && <p className="text-sm text-zinc-400">job {jobId}: <strong>{status}</strong></p>}
    </section>
  );
}
```

- [ ] **Step 2: Render in CharacterDetail**

```tsx
import { MeshGenerator } from "./MeshGenerator";
// inside CharacterDetail return:
<MeshGenerator characterId={character.id} />
```

- [ ] **Step 3: Build**

Run: `cd core/claude_code_talker/webui && npm run build`

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/MeshGenerator.tsx core/claude_code_talker/webui/src/features/characters/CharacterDetail.tsx
git commit -m "feat(webui): MeshGenerator component (Phase 25b Task 9)"
```

---

## Task 10: API key entry UI in Preferences

**Files:**
- Modify: existing preferences/secrets pane in webui (or add new SecretsPane.tsx)

- [ ] **Step 1: Find existing secrets handling**

Run: `grep -n "secrets" core/claude_code_talker/webui/src/components/*.tsx`

- [ ] **Step 2: Add three new password inputs for hyper3d/meshy/tripo3d api keys**

Pattern (in existing secrets pane):

```tsx
{["hyper3d", "meshy", "tripo3d"].map((name) => (
  <label key={name} className="block">
    <span className="text-sm">{name} API key</span>
    <input
      type="password"
      onBlur={(e) => fetch("/api/secrets", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: `${name}_api_key`, value: e.target.value }),
      })}
      className="block w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1"
    />
  </label>
))}
```

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/components/  # whichever file
git commit -m "feat(webui): API key inputs for mesh providers (Phase 25b Task 10)"
```

---

## Task 11: Update Character.mesh_path persistence

**Files:**
- Verify: `core/claude_code_talker/characters.py` already supports `mesh_path` field (Phase 25a)
- Verify: api.py mesh_jobs_poll writes to character correctly

- [ ] **Step 1: Add a regression test**

```python
def test_mesh_job_succeeded_writes_mesh_path_to_character(tmp_path, monkeypatch):
    # ... use API client with mocked provider succeeding ...
```

- [ ] **Step 2: Run regression**

Run: `pytest core/tests/test_api_mesh.py core/tests/test_characters.py -v`

- [ ] **Step 3: Commit if changes**

---

## Task 12: Full mock-based regression

- [ ] **Step 1: Run full backend suite**

Run: `pytest core/tests/ -x`
Expected: 906 + ~25 = ~931+ passing.

- [ ] **Step 2: Frontend type-check + build**

Run: `cd core/claude_code_talker/webui && npx tsc --noEmit && npm run build`

- [ ] **Step 3: Commit anything that fell out**

---

## Task 13: ⚠️ MANUAL GATE — real-key smoke test

**This task requires the user to provide live API keys.** Do not proceed past this without them.

**Files:**
- None (manual smoke)

- [ ] **Step 1: Stop and notify the user**

Print:

```
Phase 25b Task 13: ready for live smoke test.

I need API keys for at least one of:
  - hyper3d_api_key
  - meshy_api_key
  - tripo3d_api_key

Open the dashboard → Preferences → enter the keys, then say "go" to continue.
```

- [ ] **Step 2: After user signal, smoke test each configured provider**

For each configured provider:

1. Create character "smoke-{provider}" with persona warm.
2. Click MeshGenerator → enter prompt "a friendly dog" → Generate.
3. Watch job status: queued → running → succeeded.
4. Verify `~/.claude/scripts/codetalker/models/smoke-{provider}/<job_id>.glb` (or .fbx) exists.
5. Verify `state.characters.get("smoke-{provider}").mesh_path` is set.

- [ ] **Step 3: Document results**

Update `docs/superpowers/specs/2026-05-09-cct-25b-3d-mesh-apis-design.md` with a "Verified providers" footer listing which keys worked.

- [ ] **Step 4: Commit doc update**

```bash
git add docs/superpowers/specs/2026-05-09-cct-25b-3d-mesh-apis-design.md
git commit -m "docs(25b): mark verified mesh providers (Phase 25b Task 13)"
```

---

## Task 14: Hand off to Phase 27

After Task 13, the platform is complete: characters have voices and meshes. Proceed to Phase 27 UI/UX refinement.

---

## Notes for the implementer

- All HTTP responses must be parsed defensively. Provider docs change.
- Each adapter has its own response-mapping function — keep them isolated.
- `_fetch_url` must stream — don't `r.content` because models can be 50+ MB.
- `respx` mocks must use the EXACT base URL of the adapter; copy from production code.
- Don't write API keys to logs. The api.py error handler should redact.
- TDD: failing test first; mock the provider HTTP via respx; implement.
- YAGNI: skip provider feature flags (e.g., "low-poly", "PBR") in v1. Keep the prompt-only path simple.
- DRY: share `_fetch_url` between adapters via a small base helper if duplication grows past 3 places.
- Frequent commits: each task ends with a commit; long tasks split mid-task.
