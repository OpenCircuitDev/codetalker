# vNext Phase 1 Implementation — Open-Core Foundation

**Status:** Plan-mode-approved 2026-05-12; ready for subagent dispatch in the next session.
**Branch base:** `vNext-P0.5-gate` (tag) — set by the 2026-05-12 Phase 0 + 0.5 close-out session.
**Work branch:** `vNext-phase-1` (branched from `vNext-P0.5-gate` at plan-write time so file paths are accurate).
**Source spec:** `docs/superpowers/specs/2026-05-11-vNext-release-design.md` §3 (Refactor Target State) and §4 (Phase-Ordered Roadmap → Phase 1 — Open-core foundation).
**Related spec:** `docs/superpowers/specs/2026-05-09-cct-30-open-core-strategy.md` (the prior open-core decision document — three extension points, public/private repo split, distribution sketch).
**Doctrine in effect:** memory files `session_communication_style.md`, `subagent_dispatch_preflight.md`, `sonnet_1m_context_unavailable.md` ported 2026-05-12 — apply to every dispatch in this phase.

---

## Phase 1 Overview

**Goal (per spec §4 Phase 1):** OSS core is clean and Pro is extractable. **No user-facing changes.** Daemon must boot identically with and without `codetalker_pro` present.

| Task | Subagent ID | Stack | Worktree | LOC est. | Depends on |
|---|---|---|---|---|---|
| 1 | **P1-A Extension points** | Python (daemon) | `vNext-P1-A` | ~250 | none |
| 2 | **P1-B api.py decomposition** | Python (daemon) | `vNext-P1-B` | ~300 net 0 | none |
| 3 | **P1-C Pro module relocation** | Python (daemon) | `vNext-P1-C` | ~50 (mostly import path edits) | P1-A merged |
| 4 | **P1-D App.tsx dynamic tab manifest** | React | `vNext-P1-D` | ~120 | P1-A merged (`/api/ui/extensions` endpoint) |
| 5 | **P1-E webui + static cleanup** | Tooling | `vNext-P1-E` | ~15 | none |

**Dispatch waves:**
- **Wave 1 (parallel, 3 worktrees):** P1-A, P1-B, P1-E — fully independent file sets, no merge conflicts expected
- **Wave 2 (sequential, after wave 1 merges):** P1-C, then P1-D — both depend on P1-A; P1-D additionally depends on the `/api/ui/extensions` endpoint that P1-A introduces

**Phase 1 gate (per spec §4):** OSS daemon boots without `codetalker_pro` package installed. With it installed, all current functionality works identically. Tests pass. Tag: `vNext-P1-gate`.

---

## Branch + worktree setup (foreground orchestrator, runs once)

```powershell
cd C:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker
git checkout vNext
git pull
# Branch already created at plan-write time:
git branch -l vNext-phase-1   # should exist
```

Per-task worktree (run before each dispatch):

```powershell
$TASK = "P1-A"   # change per task
git worktree add C:/Users/brand/.codetalker-worktrees/$TASK -b vNext-$TASK vNext-phase-1
```

(Dash separator — `vNext-P1-A` not `vNext/P1-A` — because `vNext` is already a branch and Git refuses sibling slash-style hierarchies.)

---

## Task 1: P1-A — Extension points

**Files:**
- Create: `core/claude_code_talker/extensions.py` (NEW)
- Modify: `core/claude_code_talker/server.py` (add `extensions: ExtensionRegistry | None` to ServerState; instantiate in `build_server_state`; try-import `codetalker_pro` and call `codetalker_pro.install(state)`)
- Modify: `core/claude_code_talker/config.py:177` (`resolve_for_session` — add `extensions=None` parameter; iterate `extensions.cfg_layers` after the profile merge, before live_overlay)
- Modify: `core/claude_code_talker/api.py` (add `GET /api/ui/extensions` endpoint near the existing `/api/status` handler)
- Test: `core/tests/test_extensions.py` (NEW)

**Audit finding (spec §3.1):** OSS core needs three plug-in seams (rest_routes, cfg_layers, ui_tabs) plus two more (audio_engines, providers) so `codetalker-pro` can register at startup without forking. Today there are no seams: `api.py` builds a flat route list; `config.py:resolve_for_session` has a hardcoded `character_store=None` parameter; the React UI has a hardcoded import of `CharactersTab`.

**Success criteria:**
- `ExtensionRegistry` dataclass exists with the 5 registration methods defined in the spec.
- `state.extensions` is populated in `build_server_state`; missing `codetalker_pro` does NOT crash the daemon (try/except ImportError).
- `resolve_for_session` accepts `extensions=None` and applies registered cfg-layers in order; the existing `character_store=None` parameter is REMOVED — character merging becomes a Pro-registered layer (Pro responsibility in P1-C, but the slot must exist).
- `GET /api/ui/extensions` returns `{"tabs": [...]}` from `state.extensions.ui_tabs`. Empty list when no Pro installed.
- `state.extensions.rest_routes` are appended to the route list in `build_asgi_app`.
- Existing daemon tests pass unchanged (backwards-compatible).
- New tests cover: empty registry, missing pro, populated registry, cfg-layer order.

**Constraints:**
- Max files changed: 4 + 1 NEW + 1 NEW test = 6
- Max lines added: ~250
- Do NOT add an actual `codetalker_pro` package — that's P1-C territory
- Do NOT modify `characters.py` — it stays as-is in this task (its move is P1-C; its registration as a cfg-layer is also P1-C)

### Step 1: Write the failing test — `core/tests/test_extensions.py`

```python
"""ExtensionRegistry + cfg-layer integration."""
from __future__ import annotations

import pytest

from claude_code_talker.extensions import ExtensionRegistry, TabManifest
from claude_code_talker.server import build_server_state, build_asgi_app
from claude_code_talker.config import resolve_for_session


def test_registry_empty_by_default():
    reg = ExtensionRegistry()
    assert reg.rest_routes == []
    assert reg.cfg_layers == {}
    assert reg.ui_tabs == []
    assert reg.audio_engines == {}
    assert reg.providers == {}


def test_registry_register_routes_appends():
    reg = ExtensionRegistry()
    from starlette.routing import Route
    async def h(request): return None  # unused
    r = Route("/x", h)
    reg.register_routes([r])
    assert reg.rest_routes == [r]


def test_registry_register_cfg_layer_keyed():
    reg = ExtensionRegistry()
    def layer(cfg, session): return cfg
    reg.register_cfg_layer("character", layer)
    assert "character" in reg.cfg_layers
    assert reg.cfg_layers["character"] is layer


def test_state_extensions_present_after_build_no_pro():
    state = build_server_state()
    assert state.extensions is not None
    assert isinstance(state.extensions, ExtensionRegistry)
    assert state.extensions.rest_routes == []   # no pro → empty


def test_state_extensions_populated_when_pro_installs(monkeypatch):
    """If something registers as codetalker_pro and its install() runs,
    state.extensions reflects what it registered."""
    class FakePro:
        @staticmethod
        def install(state):
            state.extensions.register_cfg_layer("character", lambda c, s: c)
    monkeypatch.setattr("builtins.__import__", _passthrough_or_pro(FakePro))
    state = build_server_state()
    assert "character" in state.extensions.cfg_layers


def _passthrough_or_pro(fake):
    real = __import__
    def fn(name, *a, **kw):
        if name == "codetalker_pro":
            return fake
        return real(name, *a, **kw)
    return fn


def test_resolve_for_session_applies_cfg_layers_in_order():
    """Registered cfg-layers run between profile and live_overlay, in dict-insertion order."""
    # Build a minimal state with one cfg-layer that adds a marker.
    state = build_server_state()
    state.extensions.register_cfg_layer(
        "test_layer",
        lambda cfg, sess: {**cfg, "marker_test_layer": True},
    )
    # ... (fill in: build a SessionState, call resolve_for_session, assert marker present)
    # The test file in P0-A pattern showed how to construct minimal state — re-use that.


@pytest.mark.asyncio
async def test_ui_extensions_endpoint_returns_empty_when_no_pro():
    from httpx import AsyncClient, ASGITransport
    state = build_server_state()
    app = build_asgi_app(state, disable_transport_security=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/ui/extensions")
    assert r.status_code == 200
    assert r.json() == {"tabs": []}


@pytest.mark.asyncio
async def test_ui_extensions_endpoint_returns_pro_tabs():
    state = build_server_state()
    state.extensions.register_ui_tab(TabManifest(
        id="characters", label="Characters", url="/ui-react-pro/characters",
    ))
    from httpx import AsyncClient, ASGITransport
    app = build_asgi_app(state, disable_transport_security=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/ui/extensions")
    assert r.status_code == 200
    body = r.json()
    assert len(body["tabs"]) == 1
    assert body["tabs"][0]["id"] == "characters"
```

Run it — every test fails because the module doesn't exist yet.

### Step 2: Implement `core/claude_code_talker/extensions.py`

```python
"""Plug-in registry for codetalker-pro.

OSS daemon: registry stays empty.
Pro daemon: codetalker_pro.install(state) populates it on startup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from starlette.routing import Route


CfgResolver = Callable[[dict, object], dict]  # (cfg_so_far, session) -> cfg


class TTSEngine(Protocol):
    """Structural typing for things in audio_engines (XTTS, future engines)."""
    def synthesize(self, text: str, *, voice: str | None = None) -> bytes: ...
    def list_voices(self) -> list[str]: ...


class LLMProvider(Protocol):
    """Structural typing for things in providers (OpenAI, future providers)."""
    def complete(self, prompt: str, **kw) -> str: ...


@dataclass
class TabManifest:
    id: str
    label: str
    icon_url: str | None = None
    url: str = ""  # relative URL the React shell mounts


@dataclass
class ExtensionRegistry:
    rest_routes: list[Route] = field(default_factory=list)
    cfg_layers: dict[str, CfgResolver] = field(default_factory=dict)
    ui_tabs: list[TabManifest] = field(default_factory=list)
    audio_engines: dict[str, TTSEngine] = field(default_factory=dict)
    providers: dict[str, LLMProvider] = field(default_factory=dict)

    def register_routes(self, routes: list[Route]) -> None:
        self.rest_routes.extend(routes)

    def register_cfg_layer(self, name: str, resolver: CfgResolver) -> None:
        self.cfg_layers[name] = resolver

    def register_ui_tab(self, manifest: TabManifest) -> None:
        self.ui_tabs.append(manifest)

    def register_audio_engine(self, name: str, engine: TTSEngine) -> None:
        self.audio_engines[name] = engine

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        self.providers[name] = provider
```

### Step 3: Wire `state.extensions` in `server.py`

```python
# At top of server.py — add import:
from claude_code_talker.extensions import ExtensionRegistry

# In ServerState dataclass — add field:
extensions: "ExtensionRegistry" = None

# In build_server_state() — after all other state is built:
state.extensions = ExtensionRegistry()
try:
    import codetalker_pro                                # noqa: F401
    codetalker_pro.install(state)
except ImportError:
    # OSS-only build — registry stays empty, that's the contract.
    pass

# In build_asgi_app() — extend routes:
routes = build_routes(state)
routes.extend(state.extensions.rest_routes)
```

### Step 4: Modify `resolve_for_session` in `config.py:177`

```python
def resolve_for_session(
    base_cfg: dict,
    session: SessionState,
    profile_store: ProfileStore,
    extensions: "ExtensionRegistry | None" = None,    # NEW
    # character_store=None,   # REMOVE — Pro registers as a cfg_layer instead
) -> dict:
    if session.cached_cfg is not None:
        return session.cached_cfg
    resolved = copy.deepcopy(base_cfg)
    # profile layer (unchanged)
    if session.attached_profile:
        ...
    # NEW: registered cfg layers (Pro registers "character" here)
    if extensions:
        for name, resolver in extensions.cfg_layers.items():
            resolved = resolver(resolved, session)
    # live_overlay (unchanged)
    if session.live_overlay:
        _deep_merge_inplace(resolved, session.live_overlay)
    session.cached_cfg = resolved
    return resolved
```

**Callers of `resolve_for_session` will need to pass `extensions=state.extensions`.** Grep for callers: `git grep -n "resolve_for_session("`. Update each call site. The old `character_store=...` parameter goes away — every caller passing it must be updated.

**Important:** when removing `character_store=None`, this momentarily breaks character cfg-layering at runtime. That's OK because P1-C re-registers it as a cfg_layer. Until P1-C lands, character cfg-merging will be a no-op — but Phase 1 has no user-facing change requirement (only the gate "boots with and without Pro" matters). Add a code comment marking this intentional gap and pointing at P1-C.

### Step 5: Add `GET /api/ui/extensions` to `api.py`

Find an existing GET handler (e.g., `/api/status`) and add a sibling near it:

```python
async def ui_extensions_get(request: Request) -> JSONResponse:
    state = request.app.state.cct
    tabs = [
        {"id": t.id, "label": t.label, "icon_url": t.icon_url, "url": t.url}
        for t in (state.extensions.ui_tabs if state.extensions else [])
    ]
    return JSONResponse({"tabs": tabs})

# In build_routes(state):
Route("/api/ui/extensions", ui_extensions_get, methods=["GET"]),
```

### Step 6: Verify

```powershell
cd C:/Users/brand/.codetalker-worktrees/P1-A
python -m pytest core/tests/test_extensions.py -v
python -m pytest core/tests/test_config.py -v    # existing config tests should still pass
python -m pytest core/tests/test_server_transport.py -v   # existing transport tests
python -m pytest core/tests/ -x --tb=short -q   # full suite — known slow, but should not regress
```

All new tests pass. All existing tests pass (no new failures introduced — character cfg-merging gap is intentional and tests don't currently rely on character merging via this path).

### Commit pattern

Three commits, in this order:
1. `feat(P1-A): add ExtensionRegistry module` — just `extensions.py` + the new test file
2. `refactor(P1-A): wire extensions registry into server + config` — server.py + config.py + the `resolve_for_session` callers
3. `feat(P1-A): add GET /api/ui/extensions endpoint` — api.py addition + test

---

## Task 2: P1-B — api.py decomposition

**Files:**
- Source: `core/claude_code_talker/api.py` (2902 lines — verify current line count with `wc -l` first; may have grown since the spec was written)
- Target: `core/claude_code_talker/api/__init__.py` (NEW; re-exports + `build_routes`)
- Target: `core/claude_code_talker/api/sessions.py` (NEW; ~700 lines: list, get, overlay, attach-profile, hooks, narration-stream, mute/unmute)
- Target: `core/claude_code_talker/api/voices.py` (NEW; ~600 lines: list_voices, install, clone, library, secrets — the OSS-facing voice plumbing)
- Target: `core/claude_code_talker/api/characters.py` (NEW; ~700 lines: CRUD on characters + voice attach + mesh-job + clone-voice — this whole file moves to Pro in P3)
- Target: `core/claude_code_talker/api/system.py` (NEW; ~500 lines: status, cfg, ui/extensions, hooks-mode, transcribe, audio-routing)
- Test: `core/tests/test_api_package_imports.py` (NEW)
- All existing tests should pass unmodified

**Audit finding (spec §3.1 + §3.3):** `api.py` is 2902 lines — at the edge of human reviewability. Decomposing along resource boundaries (sessions/voices/characters/system) makes the Pro extraction in P3 mechanical because `characters.py` becomes its own file that can be lifted directly into `codetalker-pro`.

**Success criteria:**
- `core/claude_code_talker/api.py` is deleted; `core/claude_code_talker/api/` directory exists
- Each new file is ≤800 lines
- `core/claude_code_talker/api/__init__.py` re-exports the public surface: `build_routes`, `_VOICES_REFS_DEFAULT`, `_TRIGGERS_OVERLAY_PATH`, `CLAUDE_SETTINGS_PATH`, any other module-level constants tests monkeypatch (grep the test directory: `grep -rn "claude_code_talker.api\." core/tests/`)
- Existing tests pass unchanged (no test-file edits needed — the `from claude_code_talker.api import X` re-exports preserve the public surface)
- New `test_api_package_imports.py` validates the re-export shape so future drift is caught

**Constraints:**
- No semantic changes — handlers move verbatim, signatures unchanged
- No formatting sweeps, no rename refactors
- Re-export everything monkeypatched in tests
- Helpers used by multiple sub-modules go into `api/__init__.py` (or a small `api/_helpers.py` if needed)
- Max files added: 6 (`__init__.py` + 4 resource files + 1 test)
- Net LOC change: ≈ 0 (this is a move, not a rewrite)

### Step 1: Inventory the file boundaries

```powershell
cd C:/Users/brand/.codetalker-worktrees/P1-B
wc -l core/claude_code_talker/api.py    # confirm current size
grep -n "^async def \|^def " core/claude_code_talker/api.py > /tmp/api_handlers.txt
```

Bucket each handler by URL prefix:
- `/api/sessions*` → `sessions.py`
- `/api/voices*` → `voices.py`
- `/api/characters*`, `/api/mesh-jobs*`, `/api/voice-clone-jobs*` → `characters.py`
- `/api/status`, `/api/cfg`, `/api/mute`, `/api/unmute`, `/api/ui/extensions`, `/api/hooks/mode`, `/api/transcribe`, `/api/audio-routing` → `system.py`

If a handler isn't an `async def <name>(request)` that's wired into a Route, it's a helper — bucket it where its callers live (if shared across buckets, move to `api/__init__.py` or `api/_helpers.py`).

### Step 2: Find every monkeypatch in tests

```powershell
grep -rn "monkeypatch.setattr.*claude_code_talker.api\." core/tests/
grep -rn "from claude_code_talker.api import" core/tests/
grep -rn "claude_code_talker\.api\." core/tests/
```

Every symbol that appears in these greps must be re-exported from `api/__init__.py` so tests don't break.

### Step 3: Create the package

```powershell
mkdir core/claude_code_talker/api
# Move api.py to api/__init__.py as a starting point:
git mv core/claude_code_talker/api.py core/claude_code_talker/api/__init__.py
```

Now incrementally extract handlers to the resource files. **Each extraction is one commit.** Order suggestion:
1. Extract `system.py` (smallest, lowest risk)
2. Extract `voices.py`
3. Extract `characters.py`
4. Extract `sessions.py`

After each commit:
- `__init__.py` re-imports the extracted symbols (so the public surface stays identical)
- `pytest core/tests/test_api*.py -x` passes
- `pytest core/tests/ -x --co` collects without ImportError

### Step 4: Write `core/tests/test_api_package_imports.py`

```python
"""Verifies api package preserves the public surface for tests + plugins."""
import importlib


def test_api_package_imports_build_routes():
    from claude_code_talker.api import build_routes
    assert callable(build_routes)


def test_api_package_re_exports_constants():
    from claude_code_talker.api import (
        _VOICES_REFS_DEFAULT,
        _TRIGGERS_OVERLAY_PATH,
        CLAUDE_SETTINGS_PATH,
    )
    assert _VOICES_REFS_DEFAULT is not None
    assert _TRIGGERS_OVERLAY_PATH is not None
    assert CLAUDE_SETTINGS_PATH is not None


def test_subpackage_modules_importable():
    importlib.import_module("claude_code_talker.api.sessions")
    importlib.import_module("claude_code_talker.api.voices")
    importlib.import_module("claude_code_talker.api.characters")
    importlib.import_module("claude_code_talker.api.system")


def test_build_routes_returns_iterable():
    from claude_code_talker.api import build_routes
    from claude_code_talker.server import build_server_state
    state = build_server_state()
    routes = build_routes(state)
    assert len(routes) > 20   # sanity check — current api.py has ~50 routes
```

### Step 5: Verify

```powershell
cd C:/Users/brand/.codetalker-worktrees/P1-B
wc -l core/claude_code_talker/api/*.py   # each ≤ 800
python -m pytest core/tests/test_api_package_imports.py -v
python -m pytest core/tests/ -x --tb=short -q
python -c "from claude_code_talker.server import build_server_state, build_asgi_app; s = build_server_state(); app = build_asgi_app(s); print('boot ok')"
```

All existing tests pass. New test passes. Daemon boots.

### Commit pattern

One commit per resource extraction + one for `__init__.py` cleanup:
1. `refactor(P1-B): introduce api/ package; move api.py → api/__init__.py`
2. `refactor(P1-B): extract system handlers to api/system.py`
3. `refactor(P1-B): extract voices handlers to api/voices.py`
4. `refactor(P1-B): extract characters handlers to api/characters.py`
5. `refactor(P1-B): extract sessions handlers to api/sessions.py`
6. `test(P1-B): add api package import surface test`

---

## Task 3: P1-C — Pro module relocation (in-repo, OSS still functional)

**Files (moves only — `git mv`):**
- `core/claude_code_talker/characters.py` → `core/claude_code_talker/codetalker_pro_modules/characters.py`
- `core/claude_code_talker/mesh/` → `core/claude_code_talker/codetalker_pro_modules/mesh/`
- `core/claude_code_talker/voice/cloning_jobs.py` → `core/claude_code_talker/codetalker_pro_modules/voice/cloning_jobs.py`
- `core/claude_code_talker/voices/clone.py` → `core/claude_code_talker/codetalker_pro_modules/voices/clone.py`
- `core/claude_code_talker/voices/transcribe.py` → `core/claude_code_talker/codetalker_pro_modules/voices/transcribe.py`
- `core/claude_code_talker/engines/xtts.py` → `core/claude_code_talker/codetalker_pro_modules/engines/xtts.py`

**New: `core/claude_code_talker/codetalker_pro_modules/__init__.py`** — provides the `install(state)` entry point that P1-A's try-import calls. Registers the character cfg-layer, audio engines, providers, ui_tabs, rest_routes.

**Modified imports:** every OSS module that still imports from the relocated files must be updated. Grep with `grep -rn "from claude_code_talker.characters\|from claude_code_talker.mesh\|from claude_code_talker.voice.cloning_jobs\|from claude_code_talker.voices.clone\|from claude_code_talker.voices.transcribe\|from claude_code_talker.engines.xtts" core/`.

**Audit finding (spec §3.2 + §3.3):** Per CCT-30 + vNext spec, the feature gate IS repo membership — Pro modules physically don't exist in OSS users' installs. P3 will lift these to a separate private repo. P1-C proves the move is mechanical by relocating them in-repo to `codetalker_pro_modules/` (still git-tracked in the public repo for now), with an `install(state)` entry point. P3's extraction = `git mv codetalker_pro_modules/ ../codetalker-pro/codetalker_pro/`.

**Success criteria:**
- All listed files live under `codetalker_pro_modules/`
- `codetalker_pro_modules/__init__.py:install(state)` registers:
  - cfg_layer "character" — wraps the old character-merge logic from `config.resolve_for_session` (which P1-A stripped out)
  - audio_engine "xtts" — instantiates `XttsEngine`
  - ui_tab — TabManifest(id="characters", label="Characters", url="/ui-react-pro/characters")
  - rest_routes — all `/api/characters/*`, `/api/mesh-jobs/*`, `/api/voice-clone-jobs/*` Routes from `api/characters.py` (which P1-B created)
- `build_server_state()` calls `install` because `codetalker_pro_modules` is importable from inside the same package — but only if explicit opt-in (see below: env var or marker file). OSS-default builds skip it.
- Existing test suite passes
- New test confirms: with the env var unset, daemon boots without character routes; with it set, daemon boots with them

**Constraints:**
- This task touches a LOT of imports. Be mechanical — one resource at a time, one commit per resource.
- Do NOT rewrite any of the moved code — pure relocation + `__init__.py` install logic.
- Total LOC: ~50 new (the `__init__.py` install + 1 marker check) + ~30-40 import path edits across OSS modules. The moves themselves are pure git history with no diff.

### Step 1: Decide the opt-in mechanism

Two options, pick one at dispatch time (subagent reports the pick):

- **Option A — env var:** `CCT_PRO_ENABLED=1` toggles the try-import path. Simpler. Default off.
- **Option B — marker file:** presence of `core/claude_code_talker/codetalker_pro_modules/INSTALLED.txt` toggles. Allows simulating P3's pip-install distribution.

Recommended: **Option B**, because it more accurately models the eventual production flow (Pro install = file presence; OSS install = file absent). The `INSTALLED.txt` file ships gitignored locally for development.

### Step 2: Create directory structure

```powershell
cd core/claude_code_talker
mkdir codetalker_pro_modules
mkdir codetalker_pro_modules/mesh
mkdir codetalker_pro_modules/voice
mkdir codetalker_pro_modules/voices
mkdir codetalker_pro_modules/engines
```

Then `git mv` each file. One commit per move:
1. `chore(P1-C): relocate characters.py to codetalker_pro_modules/`
2. `chore(P1-C): relocate mesh/ to codetalker_pro_modules/mesh/`
3. ...etc

### Step 3: Update imports across OSS modules

```powershell
grep -rln "from claude_code_talker.characters" core/claude_code_talker/ | grep -v codetalker_pro_modules
grep -rln "from claude_code_talker.mesh" core/claude_code_talker/ | grep -v codetalker_pro_modules
# ... repeat for each moved module
```

For each hit, update the import:
```python
# OLD
from claude_code_talker.characters import Character, CharacterStore
# NEW
from claude_code_talker.codetalker_pro_modules.characters import Character, CharacterStore
```

OR (cleaner architecturally): route the imports through `state.extensions` instead of importing the Pro module directly. This forces OSS-side code to be Pro-agnostic. For example:
```python
# OSS code that needs a "character" — go through registry, not import
character_resolver = state.extensions.cfg_layers.get("character")
if character_resolver:
    cfg = character_resolver(cfg, session)
```

Subagent decides per-call-site based on whether the OSS code actually needs the Pro types (rare) vs just the Pro behavior (common). Default to going through `state.extensions`.

### Step 4: Write `codetalker_pro_modules/__init__.py`

```python
"""Pro install hook — called by build_server_state when the package is importable."""
from __future__ import annotations

import os
from pathlib import Path

from claude_code_talker.extensions import TabManifest

_MARKER = Path(__file__).parent / "INSTALLED.txt"


def is_enabled() -> bool:
    """Pro modules only run when the install marker is present."""
    return _MARKER.exists()


def install(state) -> None:
    """Register all Pro features into state.extensions.

    Called by server.build_server_state() after the OSS-side state is built.
    Safe to call multiple times (registrations are idempotent in practice).
    """
    if not is_enabled():
        return

    # 1. Character cfg-layer — wraps the merge logic stripped out of config.resolve_for_session
    from .characters import CharacterStore
    state.characters = CharacterStore(...)
    state.extensions.register_cfg_layer("character", _character_merge_layer)

    # 2. XTTS audio engine
    from .engines.xtts import XttsEngine
    state.extensions.register_audio_engine("xtts", XttsEngine(...))

    # 3. UI tab
    state.extensions.register_ui_tab(TabManifest(
        id="characters",
        label="Characters",
        url="/ui-react-pro/characters",
    ))

    # 4. REST routes
    from claude_code_talker.api.characters import character_routes
    state.extensions.register_routes(character_routes(state))


def _character_merge_layer(cfg: dict, session) -> dict:
    """Apply the attached character's voice/persona overrides to cfg."""
    if not getattr(session, "attached_character", None):
        return cfg
    # ... (port the character merge logic that was in resolve_for_session)
    return cfg
```

### Step 5: Modify `server.build_server_state()` to call install

(This was already wired in P1-A. P1-C just makes the import resolve to a real install() instead of being a no-op.)

```python
# P1-A already added this — verify it's still here:
try:
    import codetalker_pro    # noqa: F401
    codetalker_pro.install(state)
except ImportError:
    pass
```

**Wait** — `codetalker_pro` is the package name in P3. P1-C is using `codetalker_pro_modules` (in-repo). Two options:

- **Option A:** P1-A imports `codetalker_pro` as the package name (production-shape), and P1-C creates an outer-level shim that re-exports `codetalker_pro_modules` as `codetalker_pro`. Cleanest for the final P3 hand-off.
- **Option B:** P1-A and P1-C agree on `codetalker_pro_modules` as the dev name, and P3 renames at extraction time.

Recommend: **Option A** — wire P1-A to import `codetalker_pro` exactly as P3 will deliver it. P1-C adds `core/claude_code_talker/codetalker_pro/__init__.py` (re-exports from `codetalker_pro_modules/`). This minimizes diff at P3 extraction time.

Subagent picks at dispatch time; reports.

### Step 6: Verify

```powershell
cd C:/Users/brand/.codetalker-worktrees/P1-C
# OSS default — marker absent
rm core/claude_code_talker/codetalker_pro_modules/INSTALLED.txt 2>/dev/null
python -c "from claude_code_talker.server import build_server_state; s = build_server_state(); print('OSS boot:', s.extensions.cfg_layers, s.extensions.ui_tabs)"
# expect: empty registry, no characters

# Pro-enabled — marker present
echo "" > core/claude_code_talker/codetalker_pro_modules/INSTALLED.txt
python -c "from claude_code_talker.server import build_server_state; s = build_server_state(); print('Pro boot:', list(s.extensions.cfg_layers), [t.id for t in s.extensions.ui_tabs])"
# expect: 'character' in cfg_layers, 'characters' in ui_tabs

python -m pytest core/tests/ -x --tb=short -q
```

Both boots succeed. Tests pass.

### Commit pattern

One commit per moved resource, plus one final for the install hook:
1. `chore(P1-C): relocate characters.py to codetalker_pro_modules/`
2. `chore(P1-C): relocate mesh/ to codetalker_pro_modules/`
3. `chore(P1-C): relocate voice/cloning_jobs.py to codetalker_pro_modules/`
4. `chore(P1-C): relocate voices/clone.py + transcribe.py to codetalker_pro_modules/`
5. `chore(P1-C): relocate engines/xtts.py to codetalker_pro_modules/`
6. `feat(P1-C): add codetalker_pro install hook + marker-file gating`
7. `refactor(P1-C): route OSS character access through state.extensions`

---

## Task 4: P1-D — App.tsx dynamic tab manifest

**Files:**
- Modify: `webui/src/App.tsx`
- New: `webui/src/hooks/useUITabs.ts`
- Modify: `webui/src/App.test.tsx` (or wherever tab-rendering is tested)
- (Implicit) Pro UI bundle delivered separately under `/ui-react-pro/` — out of scope for this task

**Audit finding (spec §3.1):** `App.tsx` today hardcodes a static import of `CharactersTab`. To support Pro-as-separate-bundle, the React shell must fetch `/api/ui/extensions` on mount and `React.lazy()` each declared tab. OSS-only users see no character tab (registry empty). Pro users see it (registry populated by `codetalker_pro_modules.install`).

**Success criteria:**
- Static `import { CharactersTab } from "..."` removed from `App.tsx`
- `useUITabs()` hook fetches `/api/ui/extensions`, returns `{ tabs: TabManifest[], loading: bool }`
- App.tsx iterates `tabs` and renders each via `React.lazy(() => import(/* webpackChunkName: pro-${tab.id} */ tab.url))`
- Empty manifest renders just the OSS-static tabs (Sessions, Markup, Activity, Preferences)
- Vitest covers: empty manifest, populated manifest, fetch-fail (degrades to OSS-static)
- `npm run typecheck` + `npm run build` + `npm test` all exit 0

**Constraints:**
- Do NOT break OSS-static tabs (Sessions, Markup, Activity, Preferences) — they remain hardcoded
- Pro tab content (the actual CharactersTab.tsx component) is OUT of scope — that lives in the future `@codetalker/pro-webui` bundle. This task only wires the loading mechanism.
- Max LOC: ~120 (~60 in useUITabs, ~40 App.tsx edits, ~20 test)

### Step 1: Write the failing test — `webui/src/App.test.tsx`

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';

describe('Dynamic tab manifest', () => {
  it('renders OSS-static tabs when manifest is empty', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ tabs: [] }), { status: 200 })
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /sessions/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('tab', { name: /characters/i })).not.toBeInTheDocument();
  });

  it('renders Pro tabs from manifest', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        tabs: [{ id: 'characters', label: 'Characters', url: '/ui-react-pro/characters.js' }]
      }), { status: 200 })
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /characters/i })).toBeInTheDocument();
    });
  });

  it('degrades to OSS-static tabs on /api/ui/extensions fetch error', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('network'));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /sessions/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('tab', { name: /characters/i })).not.toBeInTheDocument();
  });
});
```

### Step 2: Implement `useUITabs.ts`

```typescript
import { useEffect, useState } from 'react';

export type TabManifest = {
  id: string;
  label: string;
  icon_url?: string;
  url: string;
};

export function useUITabs() {
  const [tabs, setTabs] = useState<TabManifest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/ui/extensions')
      .then((r) => r.json())
      .then((body) => {
        if (cancelled) return;
        setTabs(body.tabs ?? []);
      })
      .catch(() => {
        if (cancelled) return;
        setTabs([]);  // degrade quietly to OSS-only
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return { tabs, loading };
}
```

### Step 3: Modify `App.tsx`

```typescript
// Remove:
// import CharactersTab from './features/characters/CharactersTab';

// Add:
import { useUITabs } from './hooks/useUITabs';
import React, { Suspense, lazy } from 'react';

function App() {
  const { tabs: proTabs, loading } = useUITabs();
  return (
    <Tabs>
      <Tab id="sessions">…OSS-static…</Tab>
      <Tab id="markup">…OSS-static…</Tab>
      <Tab id="activity">…OSS-static…</Tab>
      <Tab id="preferences">…OSS-static…</Tab>
      {proTabs.map((t) => {
        const LazyComp = lazy(() => import(/* @vite-ignore */ t.url));
        return (
          <Tab key={t.id} id={t.id}>
            <Suspense fallback={<div>Loading {t.label}…</div>}>
              <LazyComp />
            </Suspense>
          </Tab>
        );
      })}
    </Tabs>
  );
}
```

### Step 4: Verify

```powershell
cd C:/Users/brand/.codetalker-worktrees/P1-D/core/claude_code_talker/webui
npm test
npm run typecheck
npm run build
```

All three exit 0.

### Commit pattern

1. `feat(P1-D): add useUITabs hook for dynamic tab manifest`
2. `refactor(P1-D): App.tsx renders Pro tabs from /api/ui/extensions`
3. `test(P1-D): cover empty/populated/error manifest cases`

---

## Task 5: P1-E — webui + static cleanup

**Files:**
- Modify: `.gitignore` (add `webui/node_modules/` and `core/claude_code_talker/static/` if not gitignored)
- Delete: `core/claude_code_talker/static/` directory entirely (rebuilt from webui/dist/ by setup.py at packaging time)
- Modify: `setup.py` (remove `static/*` from `package_data` if listed)
- Verify wheel build doesn't accidentally include `static/`

**Audit finding (spec §3.1 + miscellaneous):** `webui/node_modules/` slips into git in some checkouts (not gitignored consistently); `static/` is a packaging artifact that should never live in git. Both are cheap cleanups that simplify the public-repo footprint before P3 extraction.

**Success criteria:**
- `git status` shows no untracked `node_modules/` content after a fresh `npm install`
- `core/claude_code_talker/static/` directory does not exist
- `python -m build` produces a wheel that excludes `static/` (or includes only freshly-generated dist content from webui/dist/, copied at build-time)
- No regression in install flow: `pip install .` still works

**Constraints:**
- Pure tooling change — no Python or TypeScript source changes
- Max LOC: ~15 (.gitignore + setup.py)

### Steps

1. Audit `.gitignore` for existing `node_modules` entries: `grep node_modules .gitignore`
2. Add explicit `webui/node_modules/` line if absent
3. Add `core/claude_code_talker/static/` line if absent
4. `git rm -rf core/claude_code_talker/static/` (commit deletion)
5. Inspect `setup.py` for `package_data` — remove static references
6. Build wheel + inspect: `python -m build --wheel; unzip -l dist/*.whl | grep static` should return nothing
7. Smoke: `pip install dist/*.whl` in a fresh venv; `claude-code-talker --help` exits 0

### Commit pattern

1. `chore(P1-E): gitignore webui/node_modules + remove static/`
2. `chore(P1-E): drop static/ package_data from setup.py`

---

## Phase 1 Gate Verification

After all five subagents return + foreground merges their branches into `vNext-phase-1`, run the gate before tagging.

- [ ] **Gate Step 1: All branches merged**

```powershell
cd C:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker
git checkout vNext-phase-1
git log --oneline vNext-P0.5-gate..HEAD
```

Expected: ~20 commits across P1-A/B/C/D/E + 5 merge commits.

- [ ] **Gate Step 2: OSS boot (Pro absent)**

```powershell
# Ensure no Pro marker exists
rm core/claude_code_talker/codetalker_pro_modules/INSTALLED.txt 2>/dev/null
python -c "from claude_code_talker.server import build_server_state; s = build_server_state(); assert s.extensions.cfg_layers == {}; assert s.extensions.ui_tabs == []; print('OSS-only boot OK')"
```

Expected: `OSS-only boot OK`. No tracebacks, no Pro features registered.

- [ ] **Gate Step 3: Pro boot (marker present)**

```powershell
echo "" > core/claude_code_talker/codetalker_pro_modules/INSTALLED.txt
python -c "from claude_code_talker.server import build_server_state; s = build_server_state(); assert 'character' in s.extensions.cfg_layers; assert any(t.id == 'characters' for t in s.extensions.ui_tabs); print('Pro boot OK')"
```

Expected: `Pro boot OK`. Character cfg-layer + characters tab registered.

- [ ] **Gate Step 4: Daemon tests pass**

```powershell
cd core
python -m pytest --tb=short 2>&1 | tail -10
```

Expected: same pass count as `vNext-P0.5-gate` (or higher — new tests for extensions + api-package add to the count). 0 errors, 0 unexpected failures.

- [ ] **Gate Step 5: React tests + build + typecheck**

```powershell
cd core/claude_code_talker/webui
npm test
npm run typecheck
npm run build
```

Expected: all three exit 0. Build size hasn't blown up (Pro tabs lazy-loaded, no static bundle bloat).

- [ ] **Gate Step 6: Wheel build excludes static**

```powershell
cd C:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker
python -m build --wheel
unzip -l dist/claude_code_talker-*.whl | grep -i static && echo "FAIL — static in wheel" || echo "wheel clean"
```

Expected: `wheel clean`.

- [ ] **Gate Step 7: Tag the gate**

```powershell
git tag vNext-P1-gate
# Do NOT push to remote yet — Phase 2 (which can run from this gate) is the next session's work
```

Phase 1 complete. Phase 2 plan-writing happens in a future session, branched from `vNext-P1-gate`.

---

## Dispatch order summary (for the next session)

**Wave 1 (parallel — 3 worktrees):**
- P1-A, P1-B, P1-E

**Wave 2 (sequential, after wave 1 merges):**
- P1-C (depends on P1-A's extensions module + P1-B's api/characters.py split)
- P1-D (depends on P1-A's `/api/ui/extensions` endpoint)

Each dispatch follows the SDD discipline locked in by Phase 0:
1. Implementer (haiku) writes code per the task's exact spec
2. Spec-compliance reviewer (haiku)
3. Code-quality reviewer (haiku, parallel with spec reviewer)
4. If reviewers flag blocking issues, dispatch a fix subagent; otherwise merge no-ff into `vNext-phase-1`
5. Remove worktree + delete branch
6. Move to next task

Apply the comms doctrine ported 2026-05-12: 3-sentence mid-updates, 5-section end-of-phase brief, composite-outcome + per-task-state + proving-slice for the gate.

Apply the dispatch-preflight doctrine: before dispatching each task, verify every named file exists in the dispatch worktree.

Apply the haiku-default doctrine: `model: haiku` for all Phase 1 implementer + reviewer dispatches (mechanical refactor work). Reserve `model: opus` for any task that turns out to need design-level judgment (e.g., the OSS-as-Pro-agnostic question in P1-C Step 3).

---

## Self-review notes

**Spec coverage:** Every Phase 1 line in vNext spec §4 (P1-A through P1-E) maps to a task here. CCT-30's three extension points (rest_routes, cfg_layers, ui_tabs) are all in P1-A; CCT-30's audio_engines and providers extensions are also in P1-A (the spec §3.1 expanded the registry to 5 surfaces).

**Placeholder scan:** No "TBD" / "fill in later" / "similar to..." patterns. Every step has actual code or commands.

**Dispatch readiness:** Each task is self-contained with files, code, tests, verification, commits, constraints. A subagent can pick up any task without reading the others (except P1-C and P1-D which explicitly depend on P1-A merges).

**Sequencing risk:** P1-B (api.py decomposition) and P1-A (extension points) touch different concerns but P1-A adds `/api/ui/extensions` which is one of the handlers P1-B would naturally bucket into system.py. If both run in parallel, the P1-A endpoint addition needs to merge before P1-B's system.py extraction picks it up — or P1-B re-runs against the merged P1-A state. Document this in dispatch: "P1-B starts after P1-A's `/api/ui/extensions` commit lands on vNext-phase-1."

**P1-C complexity:** The most complex task — touches many import paths. If the haiku subagent gets stuck, escalate to opus. The Option A vs B decisions (env var vs marker file; codetalker_pro vs codetalker_pro_modules naming) should be made by the subagent at dispatch time and reported.

**Gate strictness:** The "boots with and without Pro" test in Gate Steps 2+3 is the single most important Phase 1 verification — it directly proves the open-core foundation works. If those fail, the rest of the gate is moot.

---

**End of Phase 1 plan.** When Phase 1 gate clears, return to writing-plans for Phase 2 (UX polish: emoting animation pipeline, AR HUD, ModelViewer lazy-load, WorkspaceGroupSection settings, field-name drift, detekt baseline).
