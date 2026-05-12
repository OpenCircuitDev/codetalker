# Codetalker vNext Release-Prep Roadmap

**Status:** design — pending user review · 2026-05-11
**Predecessors:** cct-30 open-core, cct-32 xreal-release, 2026-05-10 basic-pro-unification, 2026-05-10 pro-release-polish
**Successors:** implementation plans per phase via subagent-driven development

---

## §1 Context + Architecture

### 1.1 Where codetalker is today (audit-grounded)

Four parallel research subagents audited the daemon, character pipeline, React UI, and Android companion on 2026-05-11. Findings consolidated:

**Daemon (`core/claude_code_talker/`):**
- 30 Python modules; `api.py` is 2902 lines (largest single file), `server.py` 868, `audio.py` 546.
- 1077 tests collected but **collection BROKEN** — `test_e2e.py` + `test_hook_cli.py` import the removed `dispatch_hook` symbol after the 2026-05-11 plain-HTTP hook_cli rewrite. Must-fix before any "tests pass" release claim.
- This-session fixes ALL LANDED: `audio_misaligned` field, hub backpressure, TTSCache wiring, hook_cli circuit breaker, /ui retirement, Anthropic prompt-cache scaffold, TeacherMode strategy.
- **Extension points NOT implemented** — CCT-30 spec requires three (REST registry, cfg-layer registry, UI tab manifest); zero hits on any of them in the source.
- License-verification infrastructure absent (matches CCT-30 open question).
- Legacy `static/` dir still ships (15+18+65 KB inside any pip wheel) even though `/ui/*` route was retired this session. Dead bytes.
- `webui/node_modules/` is in the source tree — would bloat a public repo if pushed verbatim.

**Character pipeline:**
- **Voice cloning is a 20-line stub.** `api.py:1058-1098` swallows the audio bytes and immediately marks the job succeeded; never calls the real `clone_from_local_file` at `api.py:2031`. Every "cloned" character falls back to the default Piper voice. Allowlist mask hides the bug. Fix is ~20 LOC.
- **Textures may already be fixed.** `<model-viewer>` renderer at `CharacterStage.tsx:324-331` has `environment-image="legacy"` + `exposure=1.3-1.7` to compensate for PBR lighting — the exact symptom the user described. Most likely root cause was a stale `dist/` deployed. Today's `npm run build` may have already resolved it. Verifiable with a fresh `/ui-react/characters` load.
- **Emoting animations were never built.** The state machine exists (`useCharacterPose.ts`, 10 emotive states) but the renderer drives only CSS keyframes + camera drift. Meshy/Hyper3D `preview` mode ships unrigged static meshes. Real emoting requires (a) rigged + clipped GLBs and (b) renderer driver — either a `model-viewer` `animation-name` prop OR migration to `@react-three/fiber`. Pipeline-scale work, not a bug fix.

**React UI (Basic-tier):**
- Most CCT-27/28 polish SHIPPED: filter chips, workspace groups, SessionRow, SessionDetailPanel (all 8 panels including AutoModeSwitch), `keepPreviousData`, memo'd cards, layout prop, AnimatePresence popLayout, headline precedence, ActivityTab dedup.
- 62 vitest tests pass; `npm run typecheck` clean.
- **ModelViewer chunk is 1 MB eager-loaded** — should be `React.lazy()`. Cheap perf win.
- Two dead-end `/ui/#markup` links (`App.tsx:143`, `SessionMarkupQuick.tsx:133`) now 302 back to /ui-react/ — circular no-ops, must remove or wire to a real markup view.
- `WorkspaceGroupSection` settings affordance is a `window.alert()` placeholder.
- **Field-name drift**: spec calls it `output_destination` (desktop/companion/both/none); code ships `audio_outputs: AudioOutput[]` (desktop/phone/glasses). Docs lie.

**Android Pro:**
- Most Sessions/Detail UX SHIPPED + polished this session: filter pills, workspace groups, SessionRow card with live-dot + speaking-flash + ACTIVE chip + inline Mute + brief/live picker + 📵 audio_misaligned badge + ↻ auto toggle + auto-subscribe. 9 SessionDetail panels render.
- **AR HUD on Display 6 = STUB.** `AROverlayActivity.kt` exists as skeleton with `// TODO(nebula)` placeholders; not registered in `AndroidManifest.xml`; no `Presentation` API usage anywhere; no FLAG_PRESENTATION/FLAG_SECURE; no Nebula SDK AAR in `app/libs/`. Pro-release-polish §E.4 (Phase 3 hardware test) cannot pass — caption render path to glasses does not exist.
- **STT caption never rendered to user.** `captionText` flows into `CompanionViewModel` but no Composable collects it. HUD shows literal `"listening"`/`"sending"` text, not the transcript.
- Release AAB + APK on disk from 2026-05-10 11:21 — **stale**, predate today's polish + audio_misaligned + detekt wiring.
- detekt + compose-rules wired but never executed; `maxIssues: 0` config will fail CI immediately on first run. Needs baseline.

### 1.2 Locked architectural decisions (carried forward)

From CCT-30 (open-core strategy) and 2026-05-10 specs, ratified:

- **Two repos** — public `OpenCircuitDev/codetalker` (MIT, OSS) + private `OpenCircuitDev/codetalker-pro` (proprietary).
- **Pro = characters + voice cloning + 3D mesh** — daemon-side `characters.py` + `mesh/` + `voice/`; React UI `features/characters/`; future Android character render.
- **Basic = everything else** — daemon, modes, providers, engines (Piper free, ElevenLabs/OpenAI/XTTS infrastructure stays OSS but requires user-provided keys), webui shell, plugin, VS Code extension.
- **Single Android APK** — runs as Tier 2 (phone-only) or Tier 3 (with AR glasses). Hardware presence determines features, not licensing.

### 1.3 In-scope for this plan / deferred to v0.1.x+

**In-scope:**
- All audit findings above.
- The four roadmap phases laid out in §4.
- Extension-point refactor + Pro/OSS split mechanics (§3, §4.2).
- Voice clone wiring fix, texture validation, basic emoting animation pass.
- AR HUD Display 6 implementation (or explicit deferral with marketing positioning intact).
- Test suite repair + first detekt baseline.
- Distribution: signed builds, Lemonsqueezy checkout, repo-membership-as-license.

**Deferred (queued for v0.1.x):**
- Full character library expansion beyond the 3-5 ship-with-product defaults.
- Onboarding wizard / first-run polish (basic flow only).
- Per-customer Pro watermarks (anti-piracy v2).
- VS Code extension polish (functionality assumed unchanged).
- Metered pricing / usage analytics (subscription model deferred).
- Multi-daemon support.
- Catalog auto-ingestion of Claude Code project dirs without prior hook history.

---

## §2 Gap Inventory (severity-ranked)

Every gap has a severity, owner-phase, and a one-line verification.

### 2.1 Critical-blocker gaps (P0)

| # | Gap | Owner-phase | Verification |
|---|---|---|---|
| C-1 | Voice cloning endpoint is a stub; swallows audio bytes | P0 | Record → clone → speak via cloned voice; daemon log shows real reference saved to disk |
| C-2 | Test suite collection broken (2 import errors) | P0 | `pytest --co` returns 0 errors |
| C-3 | Character textures not visibly rendering (or appears so to user) | P0 | Three characters render with textures on fresh `/ui-react/characters` load |
| C-4 | STT caption never displayed in Android | P0 | Long-press → speak → see transcribed text on phone screen during dispatch |
| C-5 | /ui/#markup dead-end links (App.tsx, SessionMarkupQuick.tsx) | P0 | grep `/ui/#` in webui/src returns 0 hits |
| C-6 | Mute UX has no visibility on Android | P0 | When daemon `enabled=false`, phone shows top-level "🔇 TTS muted" banner with unmute button |

### 2.2 Foundation gaps (P1)

| # | Gap | Owner-phase | Verification |
|---|---|---|---|
| F-1 | No `register_routes` / `register_cfg_layer` / `register_ui_tab` extension points | P1 | OSS daemon boots without Pro; Pro install adds routes + tab without forking |
| F-2 | server.py + api.py have hard imports of `characters.py` + `mesh.registry` | P1 | After refactor, OSS-only build has zero `import` of Pro modules |
| F-3 | api.py is 2902 lines — refactor friction for split | P1 | api.py split into ≤4 focused modules; each ≤800 lines |
| F-4 | webui App.tsx static-imports `CharactersTab` | P1 | App.tsx renders without Pro tab installed; tab manifest API drives it |
| F-5 | `webui/node_modules/` in source tree | P1 | Public repo .gitignore covers node_modules; CI checks |
| F-6 | Legacy `static/` dir still in package | P1 | `static/` removed from disk + package_data; pip wheel doesn't carry it |

### 2.3 Polish gaps (P2)

| # | Gap | Owner-phase | Verification |
|---|---|---|---|
| P-1 | Emoting animations never implemented; only CSS approximation | P2 | At least 3 emotive states drive distinct visible animation on a rigged character |
| P-2 | AR HUD Display 6 caption render path absent | P2 | Caption text from daemon SSE appears on glasses Display 6 in `Presentation` activity |
| P-3 | ModelViewer 1 MB eager-load | P2 | Bundle splits ModelViewer to a `React.lazy()` chunk |
| P-4 | WorkspaceGroupSection settings = `alert()` placeholder | P2 | Settings opens a real panel (rename group / delete empty group) |
| P-5 | Field-name drift `audio_outputs` vs `output_destination` | P2 | Pick one (recommendation: keep `audio_outputs`); update spec text + types + API contract; one canonical name |
| P-6 | Filter chips diverged from spec | P2 | Spec docs updated to match shipped `active`/`live`/`muted`; OR shipped widened to spec |
| P-7 | DiagnosticsScreen hardcoded `"TTSPlayer ready (live wiring in B.5)"` | P2 | Real audio-focus state surfaced |
| P-8 | TTSPlayer `playSession()` `@Deprecated` warning | P2 | Removed call sites or method |

### 2.4 Cross-cutting gaps (P3 distribution + P4 launch)

| # | Gap | Owner-phase | Verification |
|---|---|---|---|
| X-1 | No license-verification mechanism (open spec question) | P3 | Decision: repo-membership-only (rec'd). Pro package delivered via Lemonsqueezy. |
| X-2 | Stale signed Android AAB + APK | P3 | Fresh AAB + APK with today's polish; uploaded to Play Console internal test |
| X-3 | detekt configured but never run, `maxIssues: 0` | P3 | First `./gradlew detekt` run produces baseline; CI enforces baseline+0 going forward |
| X-4 | Pre-existing test failures (test_e2e, test_teacher_mode, test_triggers_tags) | P3 | All `lastfailed` tests pass or are explicitly skipped with reason |
| X-5 | OSS README has no Pro upsell | P4 | README has 2-paragraph Pro upsell + 14-day trial CTA |
| X-6 | Pro landing page doesn't exist | P4 | Static landing page at codetalker.io (or similar) with demo video + Lemonsqueezy CTA |
| X-7 | Marketplace listings (Claude Code plugin) need refresh | P4 | Plugin listing updated with new screenshots + Pro upsell link |

---

## §3 Refactor Target State

### 3.1 Extension points (NEW)

Per CCT-30, OSS core needs three plug-in seams so `codetalker-pro` can register without forking.

**New module: `core/claude_code_talker/extensions.py`**

```python
@dataclass
class TabManifest:
    id: str
    label: str
    icon_url: str | None = None
    url: str = ""  # relative URL to mount the tab's React bundle

class ExtensionRegistry:
    def __init__(self):
        self.rest_routes: list[Route] = []
        self.cfg_layers: dict[str, CfgResolver] = {}
        self.ui_tabs: list[TabManifest] = []
        self.audio_engines: dict[str, "TTSEngine"] = {}
        self.providers: dict[str, "LLMProvider"] = {}

    def register_routes(self, routes: list[Route]) -> None: ...
    def register_cfg_layer(self, name: str, resolver: CfgResolver) -> None: ...
    def register_ui_tab(self, manifest: TabManifest) -> None: ...
    def register_audio_engine(self, name: str, engine: "TTSEngine") -> None: ...
    def register_provider(self, name: str, provider: "LLMProvider") -> None: ...
```

**Modified: `core/claude_code_talker/server.py`**

```python
def build_server_state() -> ServerState:
    ...
    state.extensions = ExtensionRegistry()
    # Pro discovery (optional, OSS still works without):
    try:
        import codetalker_pro
        codetalker_pro.install(state)
    except ImportError:
        pass
    return state

def build_asgi_app(state):
    routes = build_routes(state)
    routes.extend(state.extensions.rest_routes)
    ...
```

**Modified: `core/claude_code_talker/config.py`**

```python
def resolve_for_session(base_cfg, session, profile_store, *, extensions=None):
    # Built-in layer order: base_cfg → profile → live_overlay
    layered = ...
    # Pluggable layers (e.g. Pro registers "character" between profile and overlay):
    if extensions:
        for name, resolver in extensions.cfg_layers.items():
            layered = resolver(layered, session)
    return layered
```

**New REST endpoint: `GET /api/ui/extensions`**

```json
{
  "tabs": [
    {"id": "characters", "label": "Characters", "icon_url": "/ui-react-pro/icons/chars.svg",
     "url": "/ui-react-pro/characters"}
  ]
}
```

React UI's `App.tsx` reads this manifest on mount and renders each tab dynamically.

### 3.2 Feature gate = repo membership

No runtime license check. Pro modules physically don't exist in the OSS user's installation.

**OSS daemon:** `import codetalker_pro` raises `ImportError` → registry stays empty → no Pro routes/tabs/layers/cfg.
**Pro daemon:** `pip install codetalker-pro-1.0.0.tar.gz` (delivered via Lemonsqueezy) makes `codetalker_pro` importable → on next daemon start, registry populates.

Tradeoffs (already covered in §3.2 of the preview — see commit history for the full table). Net: trivial enforcement, OSS stays clean, single distribution channel.

### 3.3 Module boundaries

| Module | Target home | Notes |
|---|---|---|
| All of `core/claude_code_talker/` EXCEPT below | **OSS** | server, api, modes, providers, engines except XTTS-clone-specific paths |
| `characters.py` | **Pro** | Character data model + CharacterStore |
| `mesh/*` (7 files) | **Pro** | Meshy / Hyper3D / Tripo3D adapters + tracker |
| `voice/cloning_jobs.py` | **Pro** | Clone job tracker (the empty-shell side) |
| `voices/clone.py` + `voices/transcribe.py` | **Pro** | XTTS local cloning + Whisper transcription |
| `voices/dependency_check.py` + `auto_install.py` + `metadata.py` | **OSS** | Generic voice library plumbing — useful for Piper too |
| `engines/xtts.py` | **Pro** | XTTS engine (cloning-dependent) |
| `engines/piper.py` + `edge.py` + `elevenlabs.py` + `openai.py` | **OSS** | Free + BYO-key cloud TTS |
| `providers/*` (4 LLM adapters) | **OSS** | BYO-key cloud LLMs |
| `webui/src/features/characters/` | **Pro UI bundle** | Delivered as a separate npm/static drop-in |
| `companion-android/` | **OSS** | Whole Android app stays OSS — it's a daemon client; Pro features come from daemon |

---

## §4 Phase-Ordered Roadmap

Per Approach A (locked): phase-ordered with parallel subagents inside, sequential gate between phases.

### Phase 0 — Critical user-visible blockers (1-2 weeks)

**Goal:** Codetalker is *usable* and *demonstrable* as a Pro product. Fix the things a user would immediately notice.

| Subagent | Scope | Files |
|---|---|---|
| **P0-A: Voice clone fix** | Replace `api.py:1058-1098` stub with real `clone_from_local_file` wiring. Save audio to tmp file, call cloner, save voice reference, return job ID. Validate end-to-end: record → clone → attach to character → speak with cloned voice. | api.py, voice/cloning_jobs.py, voices/clone.py |
| **P0-B: Character texture validation** | Verify the `environment-image="legacy"` + `exposure=1.3-1.7` fix is live in the latest deployed `dist/`. If still broken, diagnose specific GLB (open in donmccurdy viewer) + fix at source. Document validation procedure for future GLB regeneration. | webui/src/components/CharacterStage.tsx, dist/, mesh/{meshy,hyper3d}.py |
| **P0-C: STT caption display** | Wire `CompanionViewModel.captionText` → SessionDetail visible Composable. Show transcribed STT text live during dispatch. Caption clears on `final_text`. Same in `HudLayer.kt` (replace literal "listening"/"sending"). | MainActivity.kt, CompanionViewModel.kt, HudLayer.kt, SessionDetailScreen.kt |
| **P0-D: Mute UX visibility (Android)** | Top-of-list banner when daemon `enabled=false`. Polls `/api/status`. One-tap unmute via `POST /api/unmute`. | SessionListScreen.kt, MainActivity.kt, DaemonClient.kt |
| **P0-E: Test suite repair** | Fix the 2 import errors blocking `pytest --co`. Either restore `dispatch_hook` shim in hook_cli.py or update tests to import current symbols. Fix the 4 `lastfailed` tests or mark them `@pytest.mark.skip` with reason. | tests/test_e2e.py, tests/test_hook_cli.py, hook_cli.py |
| **P0-F: /ui/#markup link removal** | Remove the two dead-end `/ui/#markup` links from App.tsx + SessionMarkupQuick.tsx. Update SessionMarkupQuick.test.tsx accordingly. Re-run `npm run build` + commit `dist/`. | webui/src/App.tsx, components/SessionMarkupQuick.tsx, __tests__/SessionMarkupQuick.test.tsx |

**Phase 0 gate:** A live hardware-test demo (record voice → clone → render character with textures → speak with cloned voice → see STT caption → mute via banner) passes end-to-end. Test suite collects + runs without import errors.

### Phase 1 — Open-core foundation (3-5 days)

**Goal:** OSS core is clean and Pro is extractable. No user-facing changes.

| Subagent | Scope | Files |
|---|---|---|
| **P1-A: Extension points** | Add `extensions.py` with `ExtensionRegistry`. Refactor `server.py` to use it (`state.extensions`). Refactor `config.py:resolve_for_session` to accept registered cfg-layers. Add `GET /api/ui/extensions` endpoint reading the registry. Backwards-compatible — OSS daemon works with empty registry. | server.py, api.py, config.py, extensions.py (NEW) |
| **P1-B: api.py decomposition** | Split api.py (2902 lines) into ≤4 files. Suggested split: `api/sessions.py` (list, overlay, hooks), `api/voices.py` (list, install, clone), `api/characters.py` (CRUD — will move to Pro), `api/system.py` (status, mute, cfg). Each ≤800 lines. `build_routes` becomes assembly of imports. | api.py → api/{sessions,voices,characters,system}.py |
| **P1-C: Pro module extraction prep** | Move `characters.py`, `mesh/`, `voice/`, `voices/clone.py`, `voices/transcribe.py`, `engines/xtts.py` into a new `codetalker_pro_modules/` directory IN THE SAME REPO (still OSS-side for now). Update imports. Validate daemon still boots + functions. This proves extraction is mechanical. | Multiple — see §3.3 table |
| **P1-D: App.tsx dynamic tab manifest** | React: replace static `CharactersTab` import with manifest-driven tab loading. Fetch `/api/ui/extensions` on mount; for each entry, render the tab using `React.lazy()`. Pro UI bundle delivered separately under `/ui-react-pro/`. | webui/src/App.tsx, hooks/useUITabs.ts (NEW) |
| **P1-E: webui/node_modules + static cleanup** | Add `webui/node_modules/` to `.gitignore`. Remove `core/claude_code_talker/static/` directory and `package_data` references. Update setup.py if needed. Rebuild wheel — confirm no `static/*` inside. | .gitignore, setup.py, static/ deletion |

**Phase 1 gate:** OSS daemon boots without `codetalker_pro` package installed. With it installed, all current functionality works identically. Tests pass.

### Phase 2 — Feature parity + UX polish (1 week)

**Goal:** Both surfaces feel polished + the Pro positioning (animations, AR) is real.

| Subagent | Scope | Files |
|---|---|---|
| **P2-A: Emoting animation pipeline** | THE big one. Decision: stick with `<model-viewer>` and add `animation-name=...` prop driven by `useCharacterPose.state`, OR migrate to `@react-three/fiber` for finer control. Either way: add Meshy/Hyper3D `rig` flag to mesh-jobs so future characters ship rigged. Backfill the 3-5 default characters with rigged versions (regenerate via the provider's rig endpoint). 3-5 emotive clips minimum: idle, listening, speaking, thinking. | CharacterStage.tsx, ModelViewer.tsx, useCharacterPose.ts, mesh/meshy.py + hyper3d.py |
| **P2-B: AR HUD Display 6** | Integrate Nebula SDK AAR into `app/libs/`. Wire `AROverlayActivity` as a `Presentation` activity with FLAG_PRESENTATION + FLAG_SECURE on Display 6. Caption text from MainActivity's SSE listener routes to AR HUD Composable. Test via Beam Pro + XREAL One Pro hardware. | app/libs/, AROverlayActivity.kt, AndroidManifest.xml, HudLayer.kt, MainActivity.kt |
| **P2-C: ModelViewer lazy-load** | Convert `ModelViewer.tsx` import to `React.lazy()`. Suspense fallback shows avatar placeholder. Bundle drops 1 MB from initial load. | ModelViewer.tsx, CharacterStage.tsx |
| **P2-D: WorkspaceGroupSection settings panel** | Replace `window.alert()` placeholder with real settings modal: rename group, delete-if-empty, reorder. | WorkspaceGroupSection.tsx, SessionGrid.tsx |
| **P2-E: Field-name drift resolution** | Decision recommendation: keep `audio_outputs` (already shipped both surfaces). Update specs + docs + comments + tests to match. ~15 docs/comments + 2 test files. | Multiple |
| **P2-F: detekt baseline + first run** | `./gradlew detekt` → produces baseline. Set `maxIssues: 0` AGAINST baseline (CI fails on NEW violations only). Triage top 10 violations, fix if cheap. | detekt.yml, detekt-baseline.xml (NEW) |

**Phase 2 gate:** Hardware test on Beam Pro + XREAL passes Phases 1-4 of pro-release-polish. Three characters emote distinctly. detekt CI green.

### Phase 3 — Pro distribution (4-7 days)

**Goal:** Anyone can buy + install Pro in 5 minutes.

| Subagent | Scope | Files |
|---|---|---|
| **P3-A: Pro repo extraction** | Create `OpenCircuitDev/codetalker-pro` private repo. Move Pro modules (per §3.3 table) out of public repo, into Pro repo. Pro repo gets `pyproject.toml` with `codetalker-pro` package name. Validates `pip install -e .` from Pro repo loads cleanly into the OSS daemon. | New repo + git moves |
| **P3-B: Lemonsqueezy checkout setup** | Create LS store, configure product (codetalker-pro $49 one-time), automated delivery via signed S3 URL (24hr expiry per purchase). Webhook → email with download link. Test cycle: buy → email → download → install → use. | LS dashboard + S3 bucket + webhook handler |
| **P3-C: Fresh signed Android AAB + APK** | `./gradlew bundleRelease` + `assembleRelease` with the updated code. Upload AAB to Play Console internal track. Verify install + functional smoke on phone. | gradle, Play Console |
| **P3-D: OSS PyPI publish** | `python -m build` for OSS. `twine upload` to PyPI as `codetalker`. Test `pip install codetalker` on a clean Python env. | PyPI account + setup.py final |
| **P3-E: 14-day trial package** | Build `codetalker-pro-trial-1.0.0` package that's functionally identical to Pro but with a watermark in narration ("Trial: N days left") and a hard-stop at 14 days from first run. Delivered via a separate LS product ($0). | codetalker-pro-trial/ |

**Phase 3 gate:** Test purchase from a separate machine succeeds. OSS available on PyPI. AAB in Play Console internal track. Trial package self-expires after 14 days.

### Phase 4 — Launch + docs (2-3 days)

**Goal:** Public-facing surfaces are ready for traffic.

| Subagent | Scope | Files |
|---|---|---|
| **P4-A: OSS README rewrite** | New top: what is codetalker, 60s install, 2-paragraph Pro upsell with trial CTA, examples, screenshots. Existing prior README content moved to `docs/`. | README.md, docs/* |
| **P4-B: Pro landing page** | Static page at e.g. `codetalker.io`: hero, character demo video, voice clone demo, Lemonsqueezy CTA, refund policy. Hosted on Cloudflare Pages or similar. | New repo or codetalker/website/ |
| **P4-C: Claude Code plugin marketplace listing** | Refresh listing: new screenshots, Pro upsell link, demo gif. | Marketplace dashboard |
| **P4-D: Final hardware E2E + release notes** | Run the full pro-release-polish §E test plan (Phases 1-4) on Beam Pro + XREAL. Document any final-mile issues. Write release notes covering everything from this plan + linked specs. | docs/release-notes-v1.0.md (NEW) |

**Phase 4 gate:** Public announcement ready (Twitter/X, HN, dev.to). Repos public. Pro purchase live.

---

## §5 Subagent Execution Structure

### 5.1 Dispatch pattern

Per phase, **parallel subagents within phase**, **sequential gate between phases**. Foreground (the orchestrating agent or human) dispatches all subagents for the current phase at the same time, waits for all returns, runs verification, then advances.

The audit pattern just used in this plan is the template: 4 parallel research subagents, ~5-15 min each, return reports under 500 words, foreground synthesizes.

### 5.2 Worktree strategy

Each parallel subagent gets its own git worktree branched off `vNext`:

```bash
git worktree add ~/.codetalker-worktrees/P0-A vNext/P0-A
```

- Branch naming: `vNext/P{N}-{slug}` (e.g., `vNext/P0-A`).
- Worktree path: `~/.codetalker-worktrees/P{N}-{slug}`.
- On success, foreground rebases each branch into `vNext` (no fast-forward; explicit merge commits for audit).
- Subagents in different worktrees do not conflict on shared files.
- See `superpowers:using-git-worktrees` for the canonical pattern.

### 5.3 Per-subagent input shape

Standard YAML envelope (full template in Appendix B):

```yaml
agent_id: P0-A
scope: "Replace voice-clone stub with real wiring"
inputs:
  audit_finding: <quote from character audit>
  related_spec: docs/superpowers/specs/2026-05-09-cct-25c-voice-cloning-ux-design.md
  files_in_scope: [api.py, voice/cloning_jobs.py, voices/clone.py]
  files_NOT_in_scope: [characters.py, audio.py]
success_criteria:
  - record-then-clone-then-speak cycle uses real cloned voice (not Piper fallback)
  - voice reference written to disk per CloneJobTracker model
  - no regression in test_e2e or test_voices_clone
verification:
  - cd core && python -m pytest tests/test_voices_clone.py
  - manual: open /ui-react/, create char, record + clone, attach, narrate, hear cloned voice
constraints:
  max_files_changed: 5
  max_lines_added: 200
deliverable_format: |
  ## Report (under 300 words)
  - Root cause: ...
  - Fix summary: ...
  - Files changed (diff stats): ...
  - Verification result: ...
  - Risks / follow-ups: ...
```

### 5.4 Integration discipline

- Foreground reviews each subagent's diff before merge. No automated merges.
- Subagents do NOT push to `vNext` directly — they push to their branch and report.
- Phase gate verification runs against `vNext` after all merges land.
- If a phase gate fails, foreground identifies which subagent's work caused regression and reopens that subagent OR creates a new "fix-P{N}-{slug}" subagent.

---

## §6 UI Experience Refinement

### 6.1 React UI (Basic-tier)

Most CCT-27/28 polish shipped. Remaining work:

- **P0-F**: Remove dead-end `/ui/#markup` links. The session-quick markup panel inline is sufficient; the "full markup view" can wait for v0.1.x if it's needed at all.
- **P2-C**: Lazy-load ModelViewer (1 MB chunk). Suspense fallback shows the avatar circle.
- **P2-D**: WorkspaceGroupSection settings panel (replace `alert()`).
- **P2-E**: Resolve field-name drift `audio_outputs` vs `output_destination`. Recommendation: keep `audio_outputs` (already shipped). Update specs/docs/comments.
- **P1-D**: Tab manifest API — App.tsx renders Pro tab from `/api/ui/extensions` instead of static import. Characters tab stays available for users with Pro installed.

**No** major redesign. The current UX is the right shape; we're cleaning sharp edges.

### 6.2 Android UI (Pro-tier)

Most Sessions/Detail UX shipped. Remaining:

- **P0-C**: STT caption display (live transcript visible during dispatch).
- **P0-D**: Mute UX banner (visibility for global `enabled=false`).
- **P2-B**: AR HUD Display 6 caption render. The big one — Nebula SDK + `Presentation` activity.
- **P2-F**: detekt baseline + first run. After this, every PR runs detekt as a CI gate.

### 6.3 Character display surface

Today: webui only (`<model-viewer>` in CharacterStage). After P2-A emoting work:
- Webui shows the character with animated emotive states.
- Android phone displays a character avatar in SessionDetail (existing `CharacterChip`) — no full mesh render on phone (out of scope; mesh files are large).
- AR HUD displays the character in 3D space on Display 6 (P2-B). Same mesh files, same emotive state machine.

### 6.4 Onboarding + discovery

Minimal first-pass:

- **First-run on daemon**: `setup.py` already prints the dashboard URL. Add a 3-line "What is codetalker?" section + Pro upsell link.
- **First-run on Android**: PairingScreen + OnboardingScreen exist. Add a one-screen "Try a sample narration" before first session (deferred to v0.1.x if compressed).
- **Pro upsell from OSS UI**: a small "Upgrade to Pro" link in the React Preferences panel, opening the Pro landing page in a new tab.

---

## §7 Character System Deep-Dive

### 7.1 Texture pipeline diagnosis + fix (P0-B)

The renderer fix is **already in source** (`environment-image="legacy"` + `exposure=1.3-1.7` per `CharacterStage.tsx:324-331`). The user's observation of "no textures" most likely traces to a stale `dist/` deployed before that fix or a specific GLB with missing texture channels.

Validation procedure:
1. Open `/ui-react/characters` on a fresh load (Ctrl-Shift-R).
2. Pick each of the 3-5 default characters.
3. If a character appears textured: that character's GLB is fine.
4. If a character appears flat-gray: open its `.glb` file in https://gltf-viewer.donmccurdy.com — if textures show there, renderer config issue (rare); if textures missing there, regenerate the mesh job from Meshy/Hyper3D.

### 7.2 Emoting state machine + animation pipeline (P2-A)

**Current**: state machine in `useCharacterPose.ts` produces a `state` string (10 emotive states). Renderer applies CSS keyframes + camera drift to a static mesh.

**Target**: state drives a real animation clip on a rigged mesh.

Two implementation paths:

**Path A — Keep `<model-viewer>`, add `animation-name`** (Recommended, lower risk):

```tsx
<model-viewer
  src={meshUrl}
  animation-name={mapStateToClip(state)}  // e.g. "idle", "listening", "speaking"
  autoplay
  ...
/>
```

Requires: rigged GLBs with named animation clips. Meshy + Hyper3D both support `mode: "refine"` followed by `rig` endpoint to produce rigged + clipped GLBs. Cost: $0.10-0.50 per character at the provider. Re-render the 3-5 default characters with rigged versions; users can re-rig their own characters via a new "Add Animations" button in the wizard.

**Path B — Migrate to `@react-three/fiber`** (Higher control, higher cost):

Fine-grained control over clips, blends, lighting. Requires rewriting `CharacterStage` + `ModelViewer` to use react-three-fiber's `useAnimations` + `<Gltf>`. Estimated 1 week of work; rejected for vNext but kept as v0.2 option if emoting fidelity matters more later.

**Pipeline** for Path A (P2-A scope):

1. Update Meshy + Hyper3D adapters to accept `rig: bool` flag in mesh-job inputs.
2. Default `rig=true` for new character jobs. (Cost increase per char; acceptable for Pro.)
3. For existing 3-5 default characters: backfill rigged GLBs via the providers' rig pipelines.
4. Map `useCharacterPose.state` → clip name. Spec'd mapping: `idle`/`listening`/`speaking`/`thinking` minimum (4 clips per character); others map to nearest neighbor.
5. CharacterStage passes `animation-name` to `<model-viewer>`. Add fallback "if clip not found, stay in idle" path.

### 7.3 Voice clone E2E (P0-A)

Today the endpoint at `api.py:1058-1098` is a stub. **The real cloner exists** at `voices/clone.py:127-182` (`clone_from_local_file`) and is wired to `/api/voices/clone-from-file`. The wizard at `CreateCharacterWizard.tsx:150` posts to the wrong endpoint.

**Fix:**

1. `api.py:1058-1098`: replace stub body. Write `audio_bytes` to a tmp wav file. Call `await clone_from_local_file(tmp_path, name=cid, references_dir=state.cfg.xtts_refs_dir)`. Update `CloneJobTracker` with real reference path + status.
2. Validate: record from `/ui-react/`, watch daemon log for "wrote XTTS reference at `<path>.wav`", attach to character, narrate, hear cloned voice in TTS.
3. Add a test: `tests/test_voices_clone_e2e.py` mocks XTTS and asserts the wiring.

Total: ~20 LOC + 1 test file.

### 7.4 Character library defaults

Ship 3-5 default characters with Pro:

- **Spark** — friendly assistant (already in some configs)
- **Dr. Crow** — methodical researcher (already attached to CTDev session)
- **Cipher** — technical developer (already attached to OCDev)
- **TBD-4** — playful/casual voice option
- **TBD-5** — minimalist/neutral voice option

Each ships with:
- Rigged + clipped GLB (idle/listening/speaking/thinking minimum)
- Default Piper voice assigned (users can clone over)
- Persona text snippet

Storage: `core/claude_code_talker/pro_assets/characters/*/` (in Pro repo; not OSS).

---

## §8 Test + Verify Infrastructure

### 8.1 Daemon test suite gaps + new tests

**Must-fix (P0-E):**
- Restore or stub `dispatch_hook` symbol so `test_e2e.py` + `test_hook_cli.py` collect.
- Investigate the 4 `lastfailed` tests; fix or `@pytest.mark.skip(reason=...)`.

**New tests:**
- `test_voices_clone_e2e.py` — verifies P0-A fix
- `test_extension_registry.py` — verifies P1-A extension points
- `test_pro_module_extraction.py` — verifies daemon boots cleanly without Pro

### 8.2 React test gaps

62 vitest tests pass. Add:
- `test_audio_misaligned_field.tsx` — verifies field flows through SessionRow + badge renders
- `test_ui_extensions_manifest.tsx` — verifies dynamic tab loading
- `test_modelviewer_lazy.tsx` — verifies Suspense fallback

### 8.3 Android instrumentation + Compose tests

Existing tests (PickerCatalogTest etc.) pass. Add:
- `MuteBannerTest.kt` — verifies mute UX visibility (P0-D)
- `STTCaptionRenderTest.kt` — verifies caption display (P0-C)
- `ARHUDCaptionTest.kt` — verifies caption pipes to AR HUD (P2-B) — uses fake Display

### 8.4 Hardware E2E runner

Per pro-release-polish §E, four phases:
1. webui smoke (Basic)
2. Pro Phase 1 phone-side functional walk
3. Pro Phase 2 audio loop
4. Pro Phase 3 AR HUD Display 6
5. Pro Phase 4 STT round-trip

Existing script: `companion-android/scripts/e2e/run_release_check.sh`. Expand to include the four daemon-side checks. Phase 3 currently can't run (AR HUD stub) — green after P2-B.

### 8.5 Pre-release gate script

New shell script: `scripts/release/pre_release_gate.sh`:

1. `cd core && python -m pytest --co` → 0 errors
2. `cd core && python -m pytest -x` → all pass
3. `cd core/webui && npm run typecheck && npm test && npm run build`
4. `cd companion-android && ./gradlew test detekt`
5. `cd companion-android && ./gradlew bundleRelease assembleRelease` → AAB + APK with today's mtime
6. Daemon boots without Pro installed
7. Daemon boots with Pro installed
8. Verify `/api/sessions` includes `audio_misaligned` field
9. Verify `/ui/` returns 302 to `/ui-react/`

CI runs this on every PR to `vNext` and `main`.

---

## §9 Distribution + Release Engineering

### 9.1 Signed builds checklist

| Artifact | Tool | Output | Distribution |
|---|---|---|---|
| OSS Python | `python -m build` | `codetalker-1.0.0.tar.gz` + wheel | PyPI |
| Pro Python | `python -m build` (in Pro repo) | `codetalker-pro-1.0.0.tar.gz` | Lemonsqueezy → signed S3 URL |
| Pro Trial | same | `codetalker-pro-trial-1.0.0.tar.gz` | Lemonsqueezy ($0 SKU) |
| React UI (OSS) | `npm run build` in webui/ | `webui/dist/` | Inside OSS package |
| Pro React | `npm run build` in pro-webui/ | `pro-webui-1.0.0.tgz` | Delivered with Pro Python pkg |
| Android AAB | `./gradlew bundleRelease` | `app-release.aab` | Google Play (internal → closed → open testing → production) |
| Android APK | `./gradlew assembleRelease` | `app-release.apk` | Direct sideload via Pro landing page |
| Plugin | (no build) | `claude-code-plugin/` dir | Claude Code marketplace |

### 9.2 License-verification approach: repo membership

Ratified per §3.2. No runtime check. Pro is a separately-delivered package.

### 9.3 Pricing + trial + checkout

Recommendations (user decision required):

- **Price**: $49 USD one-time per major version. Upgrade to v2: $19.
- **Trial**: 14 days, watermarked narration ("Trial: N days left"), hard-stop on day 15.
- **Channel**: Lemonsqueezy (MoR handles VAT/tax globally).
- **Delivery**: webhook → email with 24hr-expiry signed S3 URL.
- **Refund**: 30 days, no questions, 1-click via LS.

### 9.4 Marketplace + README + landing

Per §4 Phase 4 subagents.

---

## §10 Risks + Open Questions

### 10.1 Per-phase risks

- **P0** — risk: voice clone fix exposes deeper XTTS issues (env, dependencies). Mitigation: P0-A subagent allocates 1 day buffer for diagnosis.
- **P0** — risk: characters appear textured locally but stale `dist/` deployed to user's environment continues showing untextured. Mitigation: explicit "refresh cache + verify" step in P0-B.
- **P1** — risk: api.py decomposition (2902 → ≤4 files of ≤800 LOC) breaks import paths. Mitigation: backwards-compat shim in api.py that re-exports the new symbols.
- **P2-A** — risk: animation pipeline rigging fails for one of the existing characters. Mitigation: ship animations for the 3-5 defaults; user-cloned characters get "rig coming soon" placeholder.
- **P2-B** — risk: Nebula SDK integration is harder than expected (vendor docs, custom AAR). Mitigation: explicit go/no-go decision at P2 start — if it slips, ship Pro v1.0 without AR (Tier 2 phone-only) and AR in v1.1.
- **P3** — risk: Lemonsqueezy webhook timing edge cases (purchase completes but email delivery fails). Mitigation: webhook retries + manual "resend download link" admin endpoint.
- **P4** — risk: marketing/landing-page work blocks launch. Mitigation: parallel content drafting during P3.

### 10.2 Questions surfaced for user pre-kickoff

| # | Question | Default if no answer |
|---|---|---|
| Q-1 | Animation approach: Path A (model-viewer animation-name) or Path B (react-three-fiber rewrite)? | Path A |
| Q-2 | AR HUD: P2 critical-path, or defer to v1.1 and ship Pro without it? | P2 critical-path |
| Q-3 | Trial: 14-day, watermarked, separate package — confirm? | Yes |
| Q-4 | Pricing $49 one-time — confirm? | Yes |
| Q-5 | Lemonsqueezy vs Stripe (we recommend LS for MoR) — confirm LS? | LS |
| Q-6 | OSS repo name `OpenCircuitDev/codetalker` vs `claude-code-talker` — keep current or rename? | Keep `codetalker` |
| Q-7 | Field-name drift: keep `audio_outputs` (shipped) or rename to `output_destination` (spec)? | Keep `audio_outputs` |
| Q-8 | Filter chips: keep diverged set (active/live/muted) or align to spec (all/live/dormant/active)? | Keep diverged + update docs |
| Q-9 | Animation backfill: regenerate 3-5 default characters with rigging (~$1-5 in provider costs) — proceed? | Proceed |
| Q-10 | Worktree path: `~/.codetalker-worktrees/` — OK? | Yes |

---

## Appendix A — Issue Inventory (every gap)

Severity legend: 🔴 P0 critical · 🟡 P1 foundation · 🟢 P2 polish · ⚪ P3/P4 distribution/launch

| Severity | Gap | Owner | Files |
|---|---|---|---|
| 🔴 | C-1 voice clone stub | P0-A | api.py, voice/cloning_jobs.py |
| 🔴 | C-2 test collection broken | P0-E | tests/test_e2e.py, tests/test_hook_cli.py |
| 🔴 | C-3 texture validation | P0-B | CharacterStage.tsx, dist/ |
| 🔴 | C-4 STT caption display | P0-C | CompanionViewModel, HudLayer, SessionDetailScreen |
| 🔴 | C-5 /ui/#markup links | P0-F | App.tsx, SessionMarkupQuick.tsx |
| 🔴 | C-6 mute UX visibility | P0-D | SessionListScreen.kt, MainActivity.kt |
| 🟡 | F-1 extension points missing | P1-A | extensions.py (NEW), server.py, config.py |
| 🟡 | F-2 hard imports of Pro modules | P1-C | server.py, api.py, sessions.py |
| 🟡 | F-3 api.py 2902 lines | P1-B | api.py → api/{sessions,voices,characters,system}.py |
| 🟡 | F-4 App.tsx static char import | P1-D | webui/src/App.tsx |
| 🟡 | F-5 node_modules in tree | P1-E | .gitignore |
| 🟡 | F-6 legacy static/ ships | P1-E | static/ removal |
| 🟢 | P-1 emoting animations | P2-A | CharacterStage, useCharacterPose, mesh providers |
| 🟢 | P-2 AR HUD Display 6 | P2-B | AROverlayActivity.kt, AndroidManifest, Nebula SDK |
| 🟢 | P-3 ModelViewer eager load | P2-C | ModelViewer.tsx |
| 🟢 | P-4 alert() placeholder | P2-D | WorkspaceGroupSection.tsx |
| 🟢 | P-5 field name drift | P2-E | Multiple docs + tests |
| 🟢 | P-6 filter chips diverged | P2-E | Specs + docs |
| 🟢 | P-7 hardcoded "TTSPlayer ready" | P2-F | DiagnosticsScreen.kt |
| 🟢 | P-8 playSession deprecated | P2-F | TTSPlayer.kt |
| ⚪ | X-1 license model decision | P3-A | (decision) |
| ⚪ | X-2 stale signed builds | P3-C | gradle |
| ⚪ | X-3 detekt no baseline | P2-F (folded) | detekt-baseline.xml (NEW) |
| ⚪ | X-4 pre-existing test failures | P0-E (folded) | tests/* |
| ⚪ | X-5 OSS README no upsell | P4-A | README.md |
| ⚪ | X-6 Pro landing page absent | P4-B | New repo or static site |
| ⚪ | X-7 marketplace listings | P4-C | Plugin dashboard |

---

## Appendix B — Subagent Prompt Templates

Generic envelope (use for any phase subagent):

```yaml
agent_id: <P{N}-{slug}>
worktree: ~/.codetalker-worktrees/<agent_id>
branch: vNext/<agent_id>
base_branch: vNext

scope: |
  <one paragraph: problem + desired end state>

inputs:
  audit_finding: |
    <quoted finding from this spec's §1.1 audit reports>
  related_spec: docs/superpowers/specs/<spec>.md
  files_in_scope:
    - <path1>
    - <path2>
  files_NOT_in_scope:
    - <path>

success_criteria:
  - <user-visible, testable>
  - <regression check>
  - <perf/quality if applicable>

verification:
  - <command(s)>
  - <visual check>
  - <subagent must produce: log line, screenshot, test pass>

constraints:
  max_files_changed: <N>
  max_lines_added: <N>
  no_schema_changes: true
  no_new_endpoints_outside_listed_paths: true

deliverable_format: |
  ## Report (under 300 words)
  - Root cause:
  - Fix summary:
  - Files changed (diff stats):
  - Verification result:
  - Risks / follow-ups:
```

Specific seed prompts for the 6 P0 subagents are drafted as code-blocks in §4 — copy + paste + adapt.

---

## Appendix C — Existing-Spec Cross-Reference

| Existing Spec | Status | This Plan |
|---|---|---|
| `2026-05-08-cct-v1` | foundational | §1.2 context |
| `2026-05-09-cct-25a-characters` | partially shipped | §7.1, §7.2 (deferred animation impl now in P2-A) |
| `2026-05-09-cct-25b-3d-mesh-apis` | partially shipped | §7.2 (rig pipeline addition) |
| `2026-05-09-cct-25c-voice-cloning-ux` | partially shipped + stubbed | §7.3 P0-A fix |
| `2026-05-09-cct-26-markup-awareness` | shipped | §6.1 (drop dead links) |
| `2026-05-09-cct-27-ui-ux-refinement` | shipped | §6.1 (audit-verified) |
| `2026-05-09-cct-28-ux-refinement-investigation` | shipped | §6.1 (audit-verified) |
| `2026-05-09-cct-30-open-core-strategy` | design only | §3 (ratified) + P1-A/B/C |
| `2026-05-09-cct-31-xreal-android-companion` | shipped | §6.2 |
| `2026-05-09-cct-32-xreal-release` | partial (AR HUD stub) | §6.2 + P2-B |
| `2026-05-10-basic-pro-unification` | partially shipped | §6.1 + §6.2 |
| `2026-05-10-pro-release-polish` | partially shipped | distributed across §6, §8.4 |

---

**End of spec.** Awaiting user review per the brainstorming skill's user-review gate. If approved, the next step is invoking `superpowers:writing-plans` to produce per-phase implementation plans.
