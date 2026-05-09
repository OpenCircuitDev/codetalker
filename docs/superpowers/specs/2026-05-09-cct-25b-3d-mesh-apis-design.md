# CCT Phase 25b — 3D Model API Adapters (Hyper3D / Meshy / Tripo3D)

**Status**: approved 2026-05-09 (autonomous overnight build with API-key handoff), awaiting user verification.
**Scope**: provider adapter layer + async job tracker + REST endpoints + storage. Populates `Character.mesh_path` from external 3D generation services.
**Reference**: parent roadmap entry in [2026-05-08-cct-v1-design.md](./2026-05-08-cct-v1-design.md). Phase 25a Character record already shipped.

## Context

Phase 25a's Character record has `mesh_path`, `mesh_provider`, `mesh_prompt`, `mesh_prompt_history` fields ready to populate. Phase 25b adds the integration layer that calls Hyper3D (Rodin Gen-2), Meshy (v2 OpenAPI), and Tripo3D (v2 OpenAPI) on user request to generate 3D meshes from text prompts, downloads the results, and updates the Character record.

This phase is built so the user can drop in API keys at one specific point and let the rest run autonomously. Tasks 1–12 are testable with mocks; only the final smoke test (Task 13) needs real keys.

## Decisions locked in

- **Provider adapter pattern** mirroring `engines/` and `providers/`. New `core/claude_code_talker/mesh_providers/`.
- **Synchronous HTTP calls** (httpx.Client). Long-running work happens in the tracker's polling loop, which IS async.
- **Three providers in v1**: Hyper3D (Rodin Gen-2), Meshy v2, Tripo3D v2.
- **In-process tracker + filesystem-backed sidecar JSON** for crash recovery (no SQLite).
- **Storage** at `~/.claude/scripts/codetalker/models/<character_id>/<job_id>.<ext>`.
- **Cost transparency**: `MeshUsageTracker` appends to `~/.claude/scripts/codetalker/mesh_usage.jsonl`; `/api/usage` rolls it up.
- **API keys via secrets_store** — extends `KNOWN_KEYS` with `hyper3d_api_key`, `meshy_api_key`, `tripo3d_api_key`.
- **Auto-update Character on completion** — `mesh_path` populated automatically when job succeeds.

## Architecture

```
core/claude_code_talker/mesh_providers/
├── __init__.py            # registry + re-exports
├── base.py                # Mesh3DProvider ABC + JobStatus + error hierarchy
├── tracker.py             # MeshJobTracker — async polling loop + character update
├── storage.py             # ModelFileStore — atomic write GLB/FBX storage
├── usage.py               # MeshUsageTracker — append-only cost log
├── hyper3d.py             # Hyper3DProvider (Rodin Gen-2)
├── meshy.py               # MeshyProvider (Meshy v2)
└── tripo.py               # TripoProvider (Tripo3D v2)

server.py                  # MODIFY — instantiate providers when keys present
secrets_store.py           # MODIFY — KNOWN_KEYS += three API keys; iterate ENV_OVERRIDES in get_secrets
api.py                     # MODIFY — 5 new routes
characters.py              # MODIFY — auto-update on job completion (called by tracker)

~/.claude/scripts/codetalker/
├── models/<character_id>/<job_id>.glb        # the actual mesh
├── models/<character_id>/<job_id>.json       # sidecar metadata
└── models/_jobs/<job_id>.json                # tracker sidecar (for crash recovery)
└── mesh_usage.jsonl                          # cost log

core/tests/
├── test_mesh_providers_base.py
├── test_mesh_provider_hyper3d.py
├── test_mesh_provider_meshy.py
├── test_mesh_provider_tripo.py
├── test_mesh_tracker.py
├── test_mesh_storage.py
├── test_api_mesh.py
└── smoke/test_mesh_smoke.py    # gated by env vars; skipped without keys
```

## Section 1 — Mesh3DProvider interface

```python
JobId = str  # opaque, provider-specific


@dataclass
class JobStatus:
    state: str              # "queued" | "running" | "done" | "failed" | "canceled"
    progress: float | None  # 0.0–1.0 if known
    message: str | None
    raw: dict | None        # provider-specific payload


class MeshProviderError(RuntimeError): ...
class MeshAuthError(MeshProviderError): ...        # 401 / 403
class MeshRateLimitError(MeshProviderError): ...   # 429 — retry_after attr
class MeshPaymentError(MeshProviderError): ...     # 402
class MeshInvalidInputError(MeshProviderError): ...  # 400


class Mesh3DProvider(ABC):
    name: str = "base"
    output_format: str = "glb"

    @abstractmethod
    def submit_generation(self, prompt: str, **opts) -> JobId: ...
    @abstractmethod
    def poll_status(self, job_id: JobId) -> JobStatus: ...
    @abstractmethod
    def download_result(self, job_id: JobId, dest: Path) -> Path: ...
    def cancel(self, job_id: JobId) -> bool: return False
    @abstractmethod
    def estimated_cost(self, opts: dict) -> float | None: ...
```

## Section 2 — Provider-specific adapters

### Hyper3D (Rodin Gen-2)

- **Submit**: `POST https://api.hyper3d.com/api/v2/rodin` (multipart, `Authorization: Bearer <key>`)
  - Required: `tier=Gen-2`, `prompt=<text>`
  - Optional opts: `geometry_file_format` (glb|fbx|obj|stl|usdz), `material` (PBR|Shaded|All|None), `quality` (high|medium|low|extra-low), `mesh_mode` (Raw|Quad), `seed`
  - Response: `{uuid, jobs: {subscription_key, uuids}}` — store `subscription_key` as JobId
- **Poll**: `POST /api/v2/status` body `{subscription_key}` → `{jobs: [{uuid, status}]}` (Waiting/Generating/Done/Failed)
- **Download**: `POST /api/v2/download` body `{task_uuid}` → `{list: [{url, name}]}` — pick matching format, stream-download
- **Cancel**: not supported → returns False
- **Cost**: unknown publicly → returns None; surface from `consumed_credits` if returned

### Meshy v2

- **Submit**: `POST https://api.meshy.ai/openapi/v2/text-to-3d` (Bearer auth, JSON)
  - Body: `{mode: "preview", prompt, ai_model: "meshy-6", art_style?, seed?, target_polycount?, topology?}`
  - Response: `{result: <task_id>}`
  - Refine: two-step `{mode: "refine", preview_task_id}` chained internally when `quality="refine"`
- **Poll**: `GET /openapi/v2/text-to-3d/{id}` → `{id, status, progress, model_urls: {glb, fbx, obj, ...}, finished_at, consumed_credits}`
- **Download**: presigned URL from `model_urls.<output_format>`
- **Cancel/Delete**: `DELETE /openapi/v2/text-to-3d/{id}` — supported
- **Cost**: static table — preview ~5 credits ($0.10), refine ~10 credits ($0.20)

### Tripo3D v2

- **Submit**: `POST https://api.tripo3d.ai/v2/openapi/task` (Bearer, JSON)
  - Body: `{type: "text_to_model", prompt, negative_prompt?, model_version?: "v2.5"|"Tripo P1"}`
  - Response: `{code: 0, data: {task_id}}` — non-zero code is error
- **Poll**: `GET /v2/openapi/task/{task_id}` → `{code, data: {task_id, status, output: {model, pbr_model}}}`
- **Download**: presigned URL from `output.model` or `output.pbr_model`
- **Cancel**: not supported → returns False
- **Cost**: static table — base ~20 credits ($0.20), Tripo P1 ~60 credits + texture costs

## Section 3 — Storage

`ModelFileStore`:
- Root: `Path.home() / ".claude" / "scripts" / "codetalker" / "models"`
- Layout: `<root>/<character_id>/<job_id>.<ext>`
- Atomic write: `<job_id>.<ext>.tmp` → `tmp.replace(final)`
- Sidecar `<job_id>.json` next to mesh: `{provider, prompt, opts, submitted_at, finished_at, cost_usd, file_size}`
- `prune(character_id, keep_latest=10)` exposed but not auto-run in v1

## Section 4 — MeshJobTracker

```python
@dataclass
class MeshJob:
    job_id: str                    # tracker-internal UUID
    provider_job_id: str
    provider: str
    character_id: str
    prompt: str
    opts: dict
    state: str
    progress: float | None
    message: str | None
    submitted_at: float
    finished_at: float | None
    file_path: str | None
    cost_usd: float | None
    error: str | None
```

In-memory dict + per-job sidecar at `<models>/_jobs/<job_id>.json` written on every state change. On daemon startup, reads all sidecars to restore state; active jobs re-attach to polling loop.

**Polling**: single asyncio task iterates active jobs every 5s, calls `provider.poll_status` per job. On `done`: triggers `download_result` via `asyncio.to_thread`, atomically updates Character via `state.characters.save()`. On `failed`: records error, stops polling.

**Backoff**: exponential — 5s start, double up to 60s.

**Character update on completion**:
1. Load Character via `state.characters.get(char_id)`.
2. Append prompt to `mesh_prompt_history` (cap 20).
3. Set `mesh_path`, `mesh_provider`, `mesh_prompt`.
4. `state.characters.save(char)` — atomic write + bumps `updated_at`.

If character deleted between submit + completion: file written but character update skipped (WARNING log).

## Section 5 — REST endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/characters/{id}/generate-mesh` | `{prompt, provider?, opts?}` | `{job_id, provider, estimated_cost_usd, status_url}` |
| GET | `/api/mesh-jobs` | query: `?character_id=&state=` | `[MeshJob…]` |
| GET | `/api/mesh-jobs/{job_id}` | — | MeshJob DTO + raw status |
| POST | `/api/mesh-jobs/{job_id}/cancel` | — | `{canceled, reason?}` |
| GET | `/api/characters/{id}/mesh-file` | — | 200 with mesh body, `Content-Type: model/gltf-binary` |
| GET | `/api/mesh-providers` | — | `[{name, configured, supports_cancel, formats, default_quality}]` |

## Section 6 — Secrets

`secrets_store.py` extends `ENV_OVERRIDES`:

```python
ENV_OVERRIDES = {
    # ...existing...
    "HYPER3D_API_KEY": "hyper3d_api_key",
    "MESHY_API_KEY": "meshy_api_key",
    "TRIPO3D_API_KEY": "tripo3d_api_key",
}
```

`KNOWN_KEYS` derived from `ENV_OVERRIDES.values()` (small refactor — currently hardcoded). `GET /api/secrets` redact loop iterates dynamic list. Existing `/api/secrets` PUT picks up new keys automatically.

`server.py` `build_server_state` instantiates providers conditionally:

```python
if secrets.get("hyper3d_api_key"):
    state.mesh_providers["hyper3d"] = Hyper3DProvider(api_key=...)
# ...etc
```

## Section 7 — Error handling

| HTTP | Exception | API response | UI surface |
|---|---|---|---|
| 401/403 | MeshAuthError | 400 `{error: "API key invalid for <provider>"}` | "Re-enter API key" |
| 402 | MeshPaymentError | 402 `{error: "<provider> account out of credits"}` | "Top up account" |
| 400 | MeshInvalidInputError | 400 `{error: <msg>}` | Inline form error |
| 429 | MeshRateLimitError | 429 `{error: "rate limited", retry_after: N}` | Retry banner; tracker auto-retries |
| 5xx/network | MeshProviderError | 502 `{error: "<provider> unavailable: <msg>"}` | Toast + auto-retry |
| Unknown format | MeshProviderError | 500 `{error: "expected glb in download list"}` | Bug-report style |

## Section 8 — Cost transparency

`MeshUsageTracker` appends to `~/.claude/scripts/codetalker/mesh_usage.jsonl`:

```json
{"timestamp", "character_id", "provider", "job_id", "provider_job_id", "model", "prompt", "cost_usd", "credits_consumed", "duration_seconds", "format"}
```

`GET /api/usage` extends to include `mesh: {by_provider, by_character, total_cost_usd}` rollup.

Optional config: `mesh.daily_cost_cap_usd` — return 402 when exceeded.

## Section 9 — Tests (~25 new)

All using `httpx.MockTransport` or `respx`. Zero real API calls in CI.

| File | Tests |
|---|---|
| `test_mesh_providers_base.py` | 3 — ABC enforcement, JobStatus shape |
| `test_mesh_provider_hyper3d.py` | 6 — submit, poll, download, error mapping, multi-job aggregate |
| `test_mesh_provider_meshy.py` | 5 — preview submit, refine chain, poll mapping, download, cancel/delete |
| `test_mesh_provider_tripo.py` | 4 — submit, poll, code=0 vs error, download |
| `test_mesh_tracker.py` | 4 — submit→poll→done→character update, sidecar persist + recovery, failed handling, cancel propagation |
| `test_mesh_storage.py` | 2 — atomic write, sidecar JSON |
| `test_api_mesh.py` | 6 — POST validation, GET filtering, cancel, providers listing, character auto-update |

Plus `core/tests/smoke/test_mesh_smoke.py` (gated by env vars; skipped without keys) for Task 13.

## Section 10 — Implementation phases (14 TDD tasks)

| # | Task | Notes |
|---|---|---|
| 1 | Mesh3DProvider ABC + error hierarchy + JobStatus | base.py, 3 tests |
| 2 | ModelFileStore atomic-write + sidecar | storage.py, 2 tests |
| 3 | MeshUsageTracker | usage.py, 3 tests |
| 4 | Hyper3DProvider — submit + poll | hyper3d.py partial, 4 tests |
| 5 | Hyper3DProvider — download + error mapping | hyper3d.py complete, 2 tests |
| 6 | MeshyProvider — submit (preview) + poll + download | meshy.py partial, 4 tests |
| 7 | MeshyProvider — refine chain + cancel | meshy.py complete, 1 test |
| 8 | TripoProvider — submit + poll + download | tripo.py, 4 tests |
| 9 | MeshJobTracker — submit, poll loop, character update | tracker.py partial, 4 tests |
| 10 | Tracker — sidecar persist + crash recovery | tracker.py complete, 1 test |
| 11 | Wire into ServerState + secrets registration | server.py, secrets_store.py, 2 tests |
| 12 | REST endpoints (5 routes) | api.py, 6 tests |
| 13 | **Smoke test with real API keys (manual gate)** | smoke/, 3 tests (skip if missing) |
| 14 | Documentation update | spec/roadmap, no code |

**Critical structural decision**: Tasks 1–12 are testable with mocks. Task 13 is the ONE point where real API keys are needed. The user wakes up, drops keys via `PUT /api/secrets`, runs `pytest core/tests/smoke/`, and verifies one mesh per provider lands in the storage path.

## Risks / open questions

- **Provider API drift** — version-suffixed test fixtures; pin docs URLs in adapter docstrings.
- **Format mismatch** (caller wants GLB, provider returns FBX) — `output_format` per-call; fall back gracefully; Character.mesh_path carries actual extension.
- **Cost runaway** — every generation requires explicit POST; no auto-trigger. Pre-flight `estimated_cost_usd`. UI defers to Phase 27 for confirm dialog above $1. `mesh.daily_cost_cap_usd` knob optional.
- **Long jobs vs daemon restart** — sidecar JSON enables crash recovery (Task 10).
- **`get_secrets` redact list** — currently hardcoded; refactor to iterate `ENV_OVERRIDES` (must land same PR as Task 11).
- **Hyper3D pricing unknown** — `estimated_cost` returns None; UI handles null.
- **Tripo cancel not supported** — `mesh_providers[].supports_cancel` flag; UI greys cancel button.
- **Concurrent jobs per character** — allowed; later one becomes `mesh_path` if it finishes second. UI shows "1 in flight" badge.

## Out of scope

- Image-to-3D mode (text-to-3D only in v1)
- Local mesh viewer in dashboard (Phase 27 might add)
- Animation rigging (separate phase)
- Per-character cost budget enforcement
- Webhook callbacks from providers (poll-based only)

## Verification

1. `pytest core/tests/test_mesh_*.py` — all mocked tests pass
2. Full backend regression — all existing tests stay green
3. **API key handoff (manual gate at Task 13)**:
   - User provides `hyper3d_api_key`, `meshy_api_key`, `tripo3d_api_key` via `PUT /api/secrets`
   - Daemon restart picks them up; `state.mesh_providers` populates
   - `pytest core/tests/smoke/test_mesh_smoke.py` — one mesh per provider lands at `~/.claude/scripts/codetalker/models/<test-character>/<job_id>.glb`
   - Verify Character.mesh_path/mesh_provider/mesh_prompt populated automatically
   - Verify `mesh_usage.jsonl` records cost entries

## Success criteria

A user can: (1) drop API keys via `/api/secrets`; (2) POST a generate-mesh request for a character; (3) poll status; (4) on completion, find the mesh at the storage path AND see the Character record updated; (5) check `mesh_usage.jsonl` for cost record.
