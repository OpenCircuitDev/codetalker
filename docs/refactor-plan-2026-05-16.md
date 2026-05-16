# Codetalker Architectural Refactor Plan

**Date**: 2026-05-16
**Status**: PROPOSED — awaiting user approval before any code change
**Author**: Claude (under user direction: no workarounds, infrastructure-first)

---

## 1. Why this document exists

The user has accurately identified that the recent week has been a workaround spiral: each "no audio" report surfaces a different gate in a chain of 16, I fix that gate, the next report surfaces another. Total elapsed time on audio reliability is approaching the time a full refactor would have taken. The user has placed an **iron rule of no workarounds** and asked for a real infrastructure plan.

This document is the plan. **No code changes happen until the user approves it.**

---

## 2. Diagnosis — what's actually broken

### 2.1 No single source of truth for session state

A session is represented in **9 different shapes**:

| # | Shape | Lives in | Read by |
|---|---|---|---|
| 1 | `SessionState` dataclass | `sessions.py:18` (in-memory) | hooks, audio worker |
| 2 | `persistent_sessions/<sid>.yaml` | disk | api.py, companion/api.py |
| 3 | `resolve_for_session(...)` result | computed on demand | hook handlers |
| 4 | `state.cfg` (global) | `cfg-overlay.yaml` + `tts_config.yaml` | every audio gate |
| 5 | `companion_active_sessions: set` | in-memory | routing, list builders |
| 6 | `audio_hub._subscribers[sid]` | in-memory | misalignment computation |
| 7 | `/api/sessions/{id}` response | hand-built dict | webui SessionRow |
| 8 | `/api/companion/sessions` row | hand-built dict | Pro Android SessionLite |
| 9 | DataStore / localStorage | per-device | client-only views |

The shapes overlap but don't agree. Some fields exist in 3 places with different defaults. Adding a new field is a 5-file change with no test that asserts parity.

### 2.2 The audio chain is 16 sequential gates with no audit trail

```
hook fires → POST /api/hooks/dispatch → tts_handle_*  → check state.cfg.enabled
  → state.sessions.config_for(sid) → cfg.enabled → briefs.user_prompt_enabled
  → prompt.strip() non-empty → provider.complete → text non-empty
  → audio_queue.submit(AudioJob)
  → worker resolve_audio_outputs → companion_wanted
  → _decide_multi_session → opted_in check → has_subscribers check
  → engine.synthesize → wav bytes
  → publish_to_audio_hub_keyed → subscriber receives
  → ExoPlayer prepare/play → state=2/3 → STREAM_MUSIC routing → speaker
```

**Every gate can silently drop the audio.** Nothing records which gate killed a specific job. Diagnosing "I didn't hear that" requires manually tracing 6+ layers across 4 files.

### 2.3 Two list endpoints with drifting field coverage

`api.py::list_sessions` and `companion/api.py::list_sessions` are separately-maintained handlers that produce conceptually identical data. Today's audit found 3 fields missing from the Android side. No type or test prevents the next drift.

### 2.4 No event channel — polling everywhere

| Surface | Component | Interval | Workaround for |
|---|---|---|---|
| Pro Android | SessionListScreen | 3s | no event channel |
| Pro Android | SessionDetailScreen | 3s | no event channel |
| Pro Android | PreferencesScreen | 5s | no event channel |
| Pro Android | TTSPlayer (audio long-poll) | 55s | acceptable streaming pattern |
| Pro Android | AutoSubscribe scan | 3s | no event channel |
| webui | useSessions | 5s | no event channel |
| webui | useSessionConfig | 5s | no event channel |
| webui | useDaemonHealth | 5s | no event channel |
| webui | master-enabled query | 5s | no event channel |

**8 polling loops.** Each has its own interval, error handling, optimistic-update strategy. State is "eventually consistent" with multi-second latency.

### 2.5 Buddy/inject path duplicates the hook path

`/api/companion/inject` produces audio via a separate code path that eventually calls `audio_queue.submit` but with subtly different inputs (uses `bid` not source sid; doesn't check master enable; uses brief provider directly). This is why my "audio works" verification via buddy was misleading — it bypassed the gate that was killing hook audio.

### 2.6 No schema, no contract

- Daemon returns Python dicts assembled by hand.
- TypeScript declares types from memory in `webui/src/types.ts`.
- Kotlin parses JSON with `optString` / `optBoolean` in `DaemonClient.kt`.

Three independent representations of the same wire format. Any change requires editing three places. No CI check enforces alignment. Drift is built-in.

### 2.7 Inventory of workarounds shipped this week

Every one of these violates the iron rule. Documenting so they get reverted as the refactor lands:

1. **Master enable check duplicated 5 times** in `tts_handle_*` functions (server.py:496, 618, 684, 731, 758). Should be one decorator/helper.
2. **`opted_in` filter built differently** in `audio.py` vs. `companion/api.py`. Same concept, two implementations.
3. **`_derive_workspace_group` consolidated via import** rather than moving to a proper module. Still cross-imports between `api.py` and `companion/api.py`.
4. **`audio_misaligned` calculated inline in two files**. Should be on the Session model as a computed property.
5. **`is_live` checked via 3 different criteria** depending on caller (in-memory only, transcript mtime, or union). No single function.
6. **Three different "session_id" sources** for audio jobs: `companion_active_session`, `companion_active_sessions`, `bid`, `job.session_id`.
7. **Polling loops added** (SessionDetail 3s, Preferences 5s, AutoSubscribe recency gate) each as a workaround for absent events.
8. **Optimistic UI state** in MutedToggle, DestinationPicker, Auto-mode switch — workarounds for stale-props because parent isn't reactive.
9. **TTSPlayer setActiveSessions thrashing** — multiple LaunchedEffects write to `activeSessionIds` without coordination.
10. **AutoSubscribe** in SessionListScreen is a workaround for "daemon doesn't tell us which session to subscribe to."
11. **`muteToggle` + `setActiveMode` + `setWorkspaceGroup` etc. as separate DaemonClient methods** — all wrap the same PUT /overlay endpoint.
12. **`SessionState.enabled` vs `cfg.enabled` vs `persistent.enabled`** — three places to ask "is this session muted?"
13. **`live_overlay` catch-all + "promoted keys"** migration logic in `persistent_sessions.py` — workaround for inconsistent schema evolution.
14. **`audio.py::_resolve_audio_outputs` returns fleet default** when persistent has none — workaround for "no canonical opt-in registry."
15. **Companion list endpoint missing fields** (just fixed: pinned, cadence, last_user_interaction_at) — workaround for absent shared row-builder.
16. **Master toggle implemented 3 times** (daemon, webui pill, Pro Preferences row, Pro Sessions header pill) — should be one DataStore-able domain concept with one source.
17. **`/api/master-enabled` as a separate endpoint** from `/api/sessions/{id}/overlay` — workarounds together to handle "two scopes of config."
18. **Buddy audio job tagged with `bid`** instead of using a shared "audio job production" service.
19. **DataStore-based active set + daemon-side `companion_active_sessions` set** — two stores of the same fact.
20. **Reconciliation logic on launch** — workaround for two stores diverging.

---

## 3. Target architecture — what "proper" looks like

### 3.1 Layered domain

```
┌────────────────────────────────────────────────────────────┐
│  Pro Android  │  Webui  │  Future: AR glasses              │
│  Compose UI   │  React  │  Compose / Native                │
│  Generated Kotlin types  │  Generated TS types             │
└────────────────────────┬───────────────────────────────────┘
                         │ HTTP REST + SSE events
┌────────────────────────▼───────────────────────────────────┐
│  Daemon HTTP/SSE API layer (Starlette)                     │
│  Pydantic request/response validation                      │
└────────────────────────┬───────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────┐
│  Domain Services                                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ SessionSvc   │ │  AudioSvc    │ │  EventBus    │        │
│  └──────┬───────┘ └──────┬───────┘ └──────────────┘        │
│         │                │                                 │
│         │   ┌────────────┴──┐                              │
│         │   │ Decision fns: │                              │
│         │   │  is_audible() │                              │
│         │   │  route_audio()│                              │
│         │   └───────────────┘                              │
└─────────┼────────────────┼─────────────────────────────────┘
          │                │
┌─────────▼────────────────▼─────────────────────────────────┐
│  Storage: SessionStore (SQLite WAL)                        │
│  Hook ingest, TTS engines, AudioHub                        │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Single source of truth — `SessionStore`

- Backed by SQLite (WAL mode), one file in `~/.claude/scripts/codetalker/sessions.db`
- One write path: `SessionStore.update(sid, patch) -> Session`
- One read path: `SessionStore.get(sid) -> Session`
- Observable: `SessionStore.subscribe() -> AsyncIterator[SessionChanged]`
- Replaces: yaml overlay files, in-memory `state.sessions` dict, `companion_active_sessions` set, persistent_sessions module
- Schema: Pydantic `Session` model is the contract

### 3.3 Pydantic schemas

```python
# core/claude_code_talker/schemas/session.py
class Session(BaseModel):
    session_id: str
    display_name: str
    cwd: Optional[str]
    project_dir: Optional[str]
    project_slug: Optional[str]
    workspace_group: Optional[str]
    active_mode: Literal["live", "brief", "direct"]
    cadence: Optional[Cadence]
    enabled: bool
    auto_mode_enabled: bool
    audio_outputs: list[Literal["desktop", "phone", "glasses"]]
    voice: VoiceConfig
    attached_profile: Optional[str]
    attached_character: Optional[str]
    is_live: bool                 # computed
    is_speaking: bool              # transient
    last_hook_at: float
    last_modified: float
    last_user_interaction_at: float
    pinned: bool
    is_companion_active: bool      # computed per-listener
    audio_misaligned: bool          # computed

class SessionPatch(BaseModel):
    """Partial Session for PATCH operations. All fields optional."""
    # ... same fields, all Optional[]

class AudibleStatus(BaseModel):
    audible: bool
    reason: Literal[
        "audible",
        "master_disabled",
        "session_muted",
        "no_audio_outputs",
        "no_subscribers",
        "no_voice",
        "no_text",
        "briefs_disabled",
    ]
    gate: Optional[str]  # which check rejected it
```

### 3.4 Single decision functions

```python
def is_audible(session: Session, master: MasterConfig) -> AudibleStatus: ...
def route_audio(job: AudioJob, sessions: list[Session]) -> RoutingDecision | DropReason: ...
```

**Every audio-producing code path calls `is_audible` first.** No more scattered `cfg.get("enabled")`. Failures return an explicit reason.

### 3.5 Audio job state machine + audit trail

```python
class AudioJob(BaseModel):
    job_id: str
    session_id: str
    text: str
    state: AudioJobState  # enum
    state_history: list[StateTransition]
    publish_key: Optional[str]
    bytes_synthesized: Optional[int]
    error: Optional[str]
```

Every gate logs `(job_id, gate, decision, reason)` into the job's `state_history`. Queryable via `GET /api/audio-jobs/{job_id}` and surfaced in both clients' Diagnostics screens.

### 3.6 Event bus + SSE

```python
# Daemon emits
class SessionChanged(Event): session_id: str; fields: dict
class AudioJobStateChanged(Event): job_id: str; new_state: str
class MasterConfigChanged(Event): enabled: bool
class SubscriptionChanged(Event): session_id: str; subscribers: int
```

One endpoint: `GET /api/events?topics=sessions,audio,master` (SSE)
Both clients subscribe instead of poll. Cross-device sync latency: ~50ms.

### 3.7 One PATCH endpoint per resource

- `PATCH /api/sessions/{sid}` — accepts `SessionPatch`, validates, writes, emits `SessionChanged`
- `PATCH /api/master` — accepts `MasterConfigPatch`
- Replaces: `/api/sessions/{sid}/overlay`, `/api/master-enabled`, per-field setters in DaemonClient

### 3.8 Generated client types

- `datamodel-code-generator` produces TypeScript types from Pydantic
- `kotlinx-serialization-plugin` produces Kotlin data classes
- CI fails on drift
- Wire format becomes physically impossible to misrepresent

---

## 4. Refactor execution plan — 5 phases

Each phase is independently shippable, leaves the system in a working state, and reduces overall complexity rather than adding to it.

### Phase 1 — Schemas + SessionStore (2 days)

**Goal**: One canonical session model, one storage backend, no functional change yet.

- [ ] Define Pydantic schemas in `core/claude_code_talker/schemas/`
- [ ] Build `SessionStore` (SQLite WAL) with get/list/update/subscribe
- [ ] Migration script: read existing YAML files → write to SQLite
- [ ] Adapt existing code to use `SessionStore.get()` instead of dict access
- [ ] **Existing API responses unchanged** — backwards compat preserved
- [ ] Tests: store round-trip, schema validation, migration correctness

**Acceptance**: Daemon starts, all existing endpoints behave identically, sessions read from SQLite.

### Phase 2 — Decision functions + audio audit trail (1.5 days)

**Goal**: Replace scattered enabled/audio checks with single functions.

- [ ] `is_audible(session, master) -> AudibleStatus`
- [ ] `route_audio(job, sessions) -> RoutingDecision | DropReason`
- [ ] `AudioJob` with state machine
- [ ] Every `tts_handle_*` calls `is_audible` first; returns reason on skip
- [ ] Every audio gate logs to `AudioJob.state_history`
- [ ] New endpoint `GET /api/audio-jobs/recent` for diagnostics
- [ ] Delete the 8 scattered `cfg.get("enabled")` checks
- [ ] Delete duplicate `opted_in`, `audio_misaligned`, `_resolve_character` helpers

**Acceptance**: Trigger a hook with `enabled: false` → response includes `reason: "master_disabled"`. Triggers Diagnostics view shows the audio job's state machine.

### Phase 3 — Shared row-builder + single PATCH endpoint (1 day)

**Goal**: Both list endpoints return the SAME Pydantic model.

- [ ] `SessionView` Pydantic model (the wire format)
- [ ] `build_session_view(session) -> SessionView` shared helper
- [ ] `/api/sessions` and `/api/companion/sessions` both delegate to it
- [ ] `PATCH /api/sessions/{sid}` accepts `SessionPatch`, validates
- [ ] Mark `/api/sessions/{sid}/overlay` as deprecated alias
- [ ] Delete the dual `list_sessions` handlers — one implementation

**Acceptance**: webui + Android render the same data from the same handler. Adding a field requires changing one schema.

### Phase 4 — SSE event bus + client subscriptions (1.5 days)

**Goal**: Eliminate polling entirely.

- [ ] `EventBus` in daemon — async pub/sub
- [ ] `SessionStore.update` emits `SessionChanged`
- [ ] `MasterConfig.update` emits `MasterConfigChanged`
- [ ] `AudioJob` transitions emit `AudioJobStateChanged`
- [ ] New endpoint `GET /api/events` (SSE)
- [ ] webui: replace 5 useQuery polls with `useSubscription(topic)`
- [ ] Pro Android: replace 3 polling LaunchedEffects with SSE EventSource
- [ ] Delete the master-toggle poll loops, the SessionDetail poll, the AutoSubscribe scan timer

**Acceptance**: User changes mode in webui → Pro app renders new mode within 500ms. User toggles master in Pro Preferences → webui pill flips within 500ms.

### Phase 5 — Generated client types + E2E tests (1 day)

**Goal**: Drift becomes impossible.

- [ ] Configure `datamodel-code-generator` to emit TS from Pydantic
- [ ] Configure Kotlin code generation
- [ ] CI step: regenerate, assert no diff
- [ ] E2E tests:
  - [ ] `test_hook_to_audio`: POST hook → audio job completes → bytes published
  - [ ] `test_settings_sync_webui_to_pro`: PATCH from webui → SSE event → Pro state updates
  - [ ] `test_master_off_returns_reason`: master=false → hook returns `reason: "master_disabled"`
  - [ ] `test_audible_chain_audit`: produce job → query trace → assert all gates recorded

**Acceptance**: CI green on schema/codegen drift. E2E tests pass. Any future schema change breaks the build until clients regenerate.

### Phase 6 — Cleanup (1 day)

**Goal**: Delete the workarounds the refactor obsoleted.

- [ ] Delete duplicate helpers (`_resolve_character`, `_audio_misaligned`, etc.)
- [ ] Delete `companion_active_session` singular path
- [ ] Delete `live_overlay` "promoted keys" migration logic
- [ ] Delete optimistic-UI workarounds in MutedToggle/DestinationPicker/etc. (SSE makes them unnecessary)
- [ ] Delete reconciliation logic on app launch (single source of truth removes the need)
- [ ] Delete `/api/master-enabled` (folded into PATCH /api/master)
- [ ] Delete per-field DaemonClient methods (setMuted, setActiveMode, setWorkspaceGroup) → one `patch(sid, partial)`

**Acceptance**: LOC reduction ≥1500 lines net. No regressions.

---

## 5. Timeline + risk

**Total**: ~7 working days for a clean execution.

**Risks**:
- SQLite migration corrupts existing user data — mitigation: dry-run + backup before write
- SSE doesn't work over all network configurations — mitigation: keep polling as fallback for 1 release
- Generated types break existing manually-written code — mitigation: phase 5 last, after stable wire format

**Hard constraint**: at any point, the user must be able to abort the refactor and still have a working system. Each phase ends in a working build.

---

## 6. What this DOESN'T address

- Voice cloning improvements (separate workstream)
- New feature additions (frozen during refactor)
- Performance tuning (separate effort once stable)

## 6a. AR/XR — in scope for final delivery, deferred wiring

AR/XR (XREAL One Pro glasses, HUD captions + character avatars) is
**part of the distributed product** and must work in the final shipped
release. It is NOT being wired up during phases 1-6 because:

  1. The audio chain has to be stable first — the glasses are an audio
     + visual sink; if audio drops on phone speaker it also drops on
     glasses, so fixing the foundation fixes both.

  2. The Display 6 secondary-display rendering (Compose Presentation)
     is its own implementation effort that compounds risk if attempted
     alongside the schema/store refactor.

What the refactor MUST do to keep AR/XR a first-class consumer:

  - `audio_outputs` retains `"glasses"` as a valid Literal value.
    Routing logic treats it as a distinct sink from `"phone"` so a
    future USB-Audio detection can flip routing.

  - `Session` schema includes `attached_character` with the full
    character record (voice_ref, mesh_path, persona, emotive_states).
    The schema is glasses-ready; only the rendering is deferred.

  - SSE event types include `CharacterPoseChanged` and `AudioJobStateChanged`
    so a glasses client can subscribe to the same stream the webui uses.

  - Pairing model treats glasses as a distinct device (same pairing
    token flow). Pro Android pairing already works; glasses inherit
    the pattern without schema changes.

Phase 7 (post-refactor, separate workstream): Display 6 Compose
Presentation activity, caption layout, character avatar render. The
schema, store, and events are ready before phase 7 starts.

---

## 7. Decision required

User to choose one:

- **A. Full refactor** — phases 1-6, ~7 days, no feature work during. End state: a system that won't accumulate workarounds the way this week did.
- **B. Critical-path refactor** — phases 1, 2, 4 only (~5 days). End state: SSOT + decision functions + events. Skip codegen + cleanup for later.
- **C. Smaller cut** — user picks specific phases.
- **D. Different plan entirely** — user pushes back on scope/approach.

I will not write any production code until the user picks one of the above.
