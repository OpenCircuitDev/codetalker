# Claude Code Talker v1 — Store-readiness design

**Status**: approved 2026-05-08, awaiting spec review.
**Authors**: Brand (user) + Claude (this session).
**Scope**: Phases 21–24 of the codetalker repo. Phase 18 (Claude Code plugin) and Phase 19 (marketplace catalog + LICENSE) already shipped. Phase 20 (rename to CodeTalker / Claude Code Talker / Cursor Code Talker family) is **deferred** — revisit after CCT v1 is feature-complete and shipping.

## Context — why this design exists

After Phase 19 shipped, the public install path for Claude Code Talker (CCT) is two lines:

```
/plugin marketplace add OpenCircuitDev/codetalker
/plugin install codetalker@codetalker
```

Plus the prerequisite `pip install --user claude-code-talker`. The plugin works; the daemon is multi-session-aware (v0.3.0); the trigger-mode parser handles `## Audible <Tag>` blocks. But four shipping-blockers remain before this is something an everyday user can adopt:

1. **The starter trigger pack is generic.** Tags fire on prose moments, not on Claude Code's actual output shapes (plan mode, subagents, TodoWrite, skills, permissions). Narration sounds vague because the triggers don't know what Claude Code does.
2. **No multi-session dashboard.** The daemon already tracks sessions and `/api/sessions` returns live data; the legacy UI exposes it but the React rewrite is a placeholder. The user's stated outcome — "see all my sessions and tune them in one place" — has the data layer ready and zero UI.
3. **No live narration view.** A user listening to audio has no visual companion that shows what's being spoken right now, per session, with the ability to mute or skip.
4. **First-run friction is unverified.** The `/codetalker:install` slash command is a stub. The public install path from a fresh machine has not been end-to-end tested. No demo recording exists.

This spec covers Phases 21–24, which together deliver a "store-ready" v1 of Claude Code Talker that an everyday user can install, hear, see, and control.

## Decisions locked in

- **Identity scope**: single-machine, OS-user-implicit. The daemon already only sees what runs as the user; no Anthropic-account identity layer in v1. Anthropic-account scoping is a future phase, gated on real cross-machine demand.
- **Trigger pack shape**: additive. Keep the 5 generic starter tags; add 5 Claude-Code-specific tags, all disabled-by-default. Existing users see no behavior change.
- **Rename**: deferred. Marketplace, package, and plugin names stay `codetalker` / `claude-code-talker` until after v1. The rename is a separate phase.
- **Web UI transition**: parallel-serve, both stay in v1. The React UI at `/ui-react/` becomes the daily-driver surface (multi-session dashboard, narration stream, per-session controls). The legacy UI at `/ui/` keeps serving the noun-heavy edit screens it already implements — voice cloning, secrets management, profile CRUD, trigger-tag editor — which Phases 22–23 do **not** replicate. Porting the noun-heavy screens to React is a future phase, not v1.

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │  Singleton HTTP daemon              │
                     │  127.0.0.1:17832                    │
                     │                                     │
                     │  /api/health                        │
                     │  /api/sessions                      │
                     │  /api/triggers/{config,tags,body}   │
                     │  /api/narration-stream  ← Phase 23  │
                     │  /sse  (FastMCP)                    │
                     │  /ui   (legacy UI, removed in 24)   │
                     │  /ui-react  (React, Phases 22–23)   │
                     └────────────▲────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
   VS Code extension     Claude Code plugin           React webui
   (12 cmds)             (10 /codetalker:* cmds)      (Phases 22–23)
                         (MCP shim, hooks)
```

No daemon redesign. All four phases extend existing surfaces or replace existing UI assets. The trigger-mode parser, audio queue, mode selectors, and provider/engine adapters are all unchanged.

## Phase 21 — Claude-Code-tuned trigger pack

**Goal**: ship 5 starter tags whose `when_to_trigger` text references actual Claude Code behaviors so narration is meaningful instead of vague.

**Files**:
- Modify: [core/claude_code_talker/triggers/tags.py:20](../../../core/claude_code_talker/triggers/tags.py) — extend `STARTER_TAGS` with the 5 new entries.
- Tests: [core/tests/test_triggers_tags.py](../../../core/tests/test_triggers_tags.py) — add assertions for each new starter, plus a snapshot test of `compose_skill_body()` when each is enabled in isolation.

**The 5 new tags** (all `enabled: false`, `editor_mode: "structured"`):

| Tag id | Display name | When to trigger |
|---|---|---|
| `audible_plan_entry` | Audible Plan Entry | "you've just entered plan mode (created a plan file or are about to call ExitPlanMode) and want to surface the high-level plan for the listener" |
| `audible_subagent_done` | Audible Subagent Result | "a Task subagent has returned a result you're about to summarize for the user — narrate the outcome, not the process" |
| `audible_todo_advance` | Audible Todos Update | "TodoWrite advanced a meaningful task to in_progress or completed — narrate the move, not the full list" |
| `audible_skill_invoked` | Audible Skill Invoked | "you've activated a skill via the Skill tool that the listener should know about — name it and what it'll change" |
| `audible_permission_request` | Audible Permission Request | "a tool permission prompt is about to fire and the listener may need to grant or deny — narrate what's being requested and why" |

Format templates and examples follow the existing `audible_summary` pattern: ≤60–80 words, plain audible English, no URLs or paths read aloud.

**Why this works without parser/daemon changes**: the trigger-mode parser auto-recognizes any `## Audible <Tag>` header (Phase 14.5 Task 1). The daemon-aware skill in [claude-code-plugin/skills/codetalker-narration/SKILL.md](../../../claude-code-plugin/skills/codetalker-narration/SKILL.md) fetches the live tag list from `/api/triggers/skill-body` at every activation. New tags appear automatically.

**Acceptance**: 5 new starters present in `STARTER_TAGS`, all disabled-by-default; tests assert the new ids are returned by `TagLibrary.list()` after `bootstrap_starters()`; snapshot test confirms each tag's `## When to write` section appears in `compose_skill_body()` when enabled. Manual smoke: enable `audible_subagent_done` in the legacy UI, run a Task in this Claude Code session, observe the narration when the subagent returns.

## Phase 22 — Multi-session dashboard, read-only

**Goal**: replace the React placeholder with a working dashboard that shows all live sessions and their current state. No write paths in this phase.

**Files**:
- Replace: [core/claude_code_talker/webui/src/App.tsx](../../../core/claude_code_talker/webui/src/App.tsx).
- Add: `core/claude_code_talker/webui/src/components/{GlobalStatusBar,SessionGrid,SessionCard,ProjectBadge,ProfileBadge,ModeIndicator,MuteIndicator}.tsx`.
- Add: `core/claude_code_talker/webui/src/hooks/useSessions.ts` — polls `/api/sessions` every 2s with React Query.
- Add: `core/claude_code_talker/webui/src/hooks/useDaemonHealth.ts` — polls `/api/health`.
- Add: `core/claude_code_talker/webui/vitest.config.ts` and `core/claude_code_talker/webui/src/__tests__/{SessionCard,SessionGrid}.test.tsx`.
- Add: `core/claude_code_talker/webui/src/index.css` — Tailwind v4 entry.
- Modify: [core/claude_code_talker/server.py](../../../core/claude_code_talker/server.py) `build_asgi_app()` — mount built React assets at `/ui-react/` alongside the existing `/ui/`.

**Component tree**:
```
App
├── GlobalStatusBar
│   • daemon health badge (green/red)
│   • total active sessions
│   • global mute toggle (read-only display in this phase)
└── SessionGrid
    └── SessionCard × N (one per is_live session)
        ├── ProjectBadge (project_slug, last_modified relative)
        ├── ProfileBadge (attached_profile or "no profile")
        ├── ModeIndicator (mode badge)
        └── MuteIndicator (muted/audible)
```

**Data flow**: React Query polls `/api/sessions` every 2s, dedupes by `session_id`, sorts by `last_modified` descending. Cards animate in when a new session appears, fade out when `is_live` flips to false. Per-session mode/mute aren't in `/api/sessions` today — Phase 22 fetches them from `/api/sessions/{id}` lazily on card mount and refreshes every 5s. (The endpoint exists and returns the per-session config overlay.)

**Build**: `npm --prefix core/claude_code_talker/webui run build` produces `webui/dist/`. The daemon's `build_asgi_app` mounts `webui/dist/` at `/ui-react/` via `StaticFiles`.

**Tests**: vitest renders `<SessionCard>` against fixture session data, asserts the project slug and profile badge show up; renders `<SessionGrid>` with three sessions, asserts three cards.

**Acceptance**: from this Claude Code session, navigating to `http://127.0.0.1:17832/ui-react/` shows live cards for every active session in `/api/sessions`. The codetalker session card shows `codetalker / no profile`; the BF_Workspace cards show `Workspace / alpha`. Cards update within 2s of `last_modified` changes.

## Phase 23 — Live narration stream + dashboard interactivity

**Goal**: dashboard becomes the user's actual control surface. They can see narrations stream in real time, they can drive each session's mode/mute/voice from the card.

Two parallel tracks within the phase.

### 23a — SSE narration stream (daemon side)

**Files**:
- Add: `core/claude_code_talker/narration_stream.py` — `NarrationStream` class with `subscribe()` async generator, `publish()` method, bounded queue per subscriber.
- Modify: [core/claude_code_talker/audio_queue.py](../../../core/claude_code_talker/audio_queue.py) — call `NarrationStream.publish()` at submit, start, end, skip transitions.
- Modify: [core/claude_code_talker/api.py](../../../core/claude_code_talker/api.py) — add route `GET /api/narration-stream` returning `text/event-stream`.
- Add: [core/tests/test_narration_stream.py](../../../core/tests/test_narration_stream.py) — async pytest, subscribes to the stream, queues a synthetic narration, asserts the four event types arrive in order.

**Event shape**:
```json
{
  "session_id": "<uuid>",
  "timestamp": 1778299617.328,
  "text": "<narration content>",
  "voice": "en_GB-jenny_dioco-medium",
  "mode": "brief",
  "status": "queued" | "speaking" | "done" | "skipped"
}
```

**Subscriber lifecycle**: subscribe creates a per-client `asyncio.Queue` with `maxsize=200`. On overflow, oldest events drop and a `{status: "overflow"}` sentinel is emitted. Disconnects are detected by failed write; the stream cleans the queue.

### 23b — Dashboard interactivity

**Files**:
- Add: `core/claude_code_talker/webui/src/components/{NarrationFeed,SessionControls,VoicePicker,ModePicker}.tsx`.
- Add: `core/claude_code_talker/webui/src/hooks/useNarrationStream.ts` — wraps `EventSource`, parses events, exposes per-session ring buffer (last 20 events).
- Modify: `core/claude_code_talker/webui/src/components/SessionCard.tsx` — embed `<SessionControls>` (mute toggle, mode picker, voice picker).
- Modify: `core/claude_code_talker/webui/src/App.tsx` — add `<NarrationFeed>` below the grid.
- Add: vitest tests for `<SessionControls>` and `<NarrationFeed>`.

**Write paths used**: existing REST — `POST /api/sessions/{id}/overlay` (set mode/voice), `PUT /api/sessions/{id}/overlay` (mute). Voice picker lazy-loads from existing `/api/voices`. No new daemon endpoints in 23b.

**Acceptance**: dashboard subscribes to `/api/narration-stream` on mount. As the daemon speaks (this session triggers it), the narration appears in the feed within 200ms with the correct session attribution. Clicking mute on a card silences only that session and the next narration shows `status: "skipped"`. Mode change persists across daemon restart (overlay survives).

## Phase 24 — First-run polish + demo

**Goal**: an outsider who finds the GitHub repo can go from `pip install` to "I'm hearing Claude" in under two minutes.

**Tasks**:

1. **`/codetalker:install` flow polish** ([claude-code-plugin/commands/install.md](../../../claude-code-plugin/commands/install.md)):
   - Detect missing pip package → emit copy-paste fix.
   - Detect missing Piper binary → emit copy-paste fix.
   - Detect missing voice models → emit copy-paste fix.
   - Detect daemon-not-running → emit `claude-code-talker serve` instruction.
   - Each branch gives one specific fix command, not a wall of options.

2. **`claude-code-talker setup` polish** ([core/claude_code_talker/setup.py](../../../core/claude_code_talker/setup.py)):
   - Improve terminal output: clear sectioning, progress indicators for the Piper download, post-setup verification step.

3. **`/codetalker:open-ui` rerouting** (legacy UI stays):
   - Update [claude-code-plugin/bin/open-ui.cmd](../../../claude-code-plugin/bin/open-ui.cmd) and [open-ui.sh](../../../claude-code-plugin/bin/open-ui.sh) to point at `/ui-react/` so the slash command opens the new dashboard by default.
   - Add a small "Advanced" link inside the React dashboard pointing at `/ui/` for users who need the legacy noun-heavy screens (voice cloning, secrets, profiles, trigger-tag editor).
   - Do **not** delete `core/claude_code_talker/static/` or unmount `/ui/`. The legacy UI's screens aren't replicated in Phases 22–23 and are needed in v1.
   - Porting the noun-heavy screens to React is tracked as a follow-up phase, not part of v1.

4. **Public install path verification**:
   - Commit + push Phases 18, 19, 21–23 to `OpenCircuitDev/codetalker` on GitHub.
   - From a fresh Claude Code session: `/plugin marketplace remove codetalker` (if previously added locally), then `/plugin marketplace add OpenCircuitDev/codetalker`, then `/plugin install codetalker@codetalker`. End-to-end verification.

5. **Demo recording**:
   - 60-second screen capture: install commands → first narration → dashboard view → mode change.
   - Embed in [README.md](../../../README.md) as an animated GIF or a YouTube link.

**Acceptance**: a clean Windows machine with Python 3.11+ and Claude Code installed reaches first narration in <2 minutes following only the README.

## Cross-phase testing strategy

- **Existing tests stay green at every phase boundary.** 84 tests today; each phase commit must keep them all passing.
- **Phase 21**: +5 unit tests in `test_triggers_tags.py`.
- **Phase 22**: +6 vitest tests in `webui/src/__tests__/`. New `vitest.config.ts`. CI command added to `webui/package.json` scripts: `"test": "vitest run"`.
- **Phase 23**: +3 daemon tests in `test_narration_stream.py`; +5 vitest tests for the new components.
- **Phase 24**: manual smoke; the demo recording itself is documentation, not an automated test. Public install path verification is a manual end-to-end gate before tagging the v1 release.

## Subagent-driven implementation contract

Each phase decomposes into 3–6 single-concern tasks. The main thread (this session) dispatches them one at a time, or in parallel within a phase where independent.

**Dispatch contract for each task**:
- A self-contained brief with file paths, function names, acceptance criteria.
- The relevant excerpt from this spec.
- An explicit instruction: "run the affected tests before reporting done; report the test output verbatim."

**Receipt contract for the main thread**:
- Re-run the full test suite (or affected subset) on receipt.
- Read the diff before commit.
- Commit with a Phase-numbered message; push at phase boundaries, not per-task.

**Sequence**:
- Phase 21 → 22 → 23 → 24, sequential.
- Within Phase 23: 23a and 23b in parallel.
- Within other phases: parallelize where independent (Phase 22's components can be built in parallel).

## Risks / open questions

- **Phase 22 `/api/sessions/{id}` polling overhead**: 2s × N sessions could be heavy if N is large. Mitigation: bound at 20 visible sessions, paginate the rest. If overhead is real, fold per-session config into the bulk `/api/sessions` response in a follow-up.
- **Phase 23 SSE on Windows + Dropbox**: Dropbox's filesystem layer occasionally interferes with long-lived sockets in our environment. Mitigation: keepalive pings every 15s, EventSource auto-reconnect on the client side.
- **Phase 24 demo recording**: requires screen-capture tooling. Out-of-scope for the codebase; user provides.
- **Identity scope decision** could change mid-phase if cross-machine usage materializes. Mitigation: design the dashboard's session list to be source-agnostic (it consumes `/api/sessions`; the source of those sessions can change later without UI changes).
- **Rename later**: when Phase 20 (rename) lands, the marketplace name changes, breaking existing users' `/plugin marketplace add` commands. Mitigation: ship the rename with a clear migration command and a 30-day deprecation banner.

## Out of scope for v1

- **Anthropic-account identity layer** — defer until cross-machine demand is real.
- **Full Python package split** (`code-talker` + `claude-code-talker` + `cursor-code-talker`) — defer to Phase 20+.
- **Cursor support** — paper-only until there's actual Cursor demand.
- **Cloud relay / hosted dashboard** — out of scope, may never be needed.
- **MCPB bundle for Claude Desktop** — secondary artifact, ship after CCT v1 is stable.
- **Single-binary installer** (PyInstaller) — defer until pip prerequisite proves to be the actual conversion blocker.

## Success criteria for v1

A user who has never seen this repo before can, in under 2 minutes:
1. Read the README's two-line install snippet.
2. Run `pip install --user claude-code-talker`.
3. Run `/plugin marketplace add OpenCircuitDev/codetalker` + `/plugin install codetalker@codetalker` in Claude Code.
4. Issue any prompt and hear narration.
5. Open the dashboard via `/codetalker:open-ui` and see their session(s).
6. Adjust mute/mode from the dashboard and feel the change immediately.

When that's true on a clean machine, v1 is shipping-ready.
