# 2026-05-10 — Basic + Pro Unification Design

## Context

After the v0.1.0 hardware-test polish landed (Sessions list redesign, OpenRouter buddy, glasses audio path, multi-screen button design, workspace_group, persistent cross-sync), the Pro Android surface has meaningfully more session-management UX than the Basic webui dashboard. The user has been navigating both surfaces in parallel and wants them to feel like **one product**: the same session organization, the same flash signals when sessions are active, the same toggles for routing audio, and the same mental model for grouping.

The webui's CharactersTab (with CreateCharacterWizard + BrowserRecorder) is a Pro-positioning concern: local voice cloning and 3D characters are the stated **Pro-exclusive differentiators**, so they should migrate to the Pro Android app over time, with the webui retreating to a read-only "what's attached" view.

This spec is the design for the unification pass. It is scoped to v0.1.0 polish-completion; the character-flow migration is phased into v0.1.x.

## Goals

1. **Single mental model across surfaces** — same grouping (`workspace_group` user-defined > `project_dir` humanized > "Ungrouped"), same filter pills (Live / All / Dormant / Active), same sticky group headers, same display-name rename, same Make-active flow.
2. **Pro Android UI pattern in the webui** — Sessions becomes a card list with filter pills + group headers, SessionDetail becomes a panel-by-panel detail (Name & workspace, Speaking mode, Voice, Cadence, Muted, Markup, Character display).
3. **Per-session output destination** — each session has an `output_destination` field: `desktop`, `companion`, `both` (default), or `none`. The audio worker honors it: it suppresses local playback when destination = `companion`, suppresses the audio_hub publish when destination = `desktop`, suppresses everything when destination = `none`. The existing `companion_suppress_desktop` cfg flag becomes the global DEFAULT for sessions without an explicit destination.
4. **Active-state flash, unified** — both surfaces render the same animation: a strong pulse when the daemon says `is_speaking=true`, a softer ambient pulse when `last_hook_at` is within 10s, a steady green outline when the row is the companion's currently-active session. The daemon adds `is_speaking` to `/api/companion/sessions` (already populated in `/api/sessions` for the webui's `SpeakingDot`).
5. **Bidirectional sync stays automatic** — every overlay edit goes through `PUT /api/sessions/{id}/overlay` → daemon updates `state.sessions.update_overlay` + writes through to `state.persistent_sessions` (already wired in v0.1.0 polish). Both surfaces poll the daemon every 3–5s and converge.
6. **Pro features preserved on Pro** — Character library + voice cloning REMAIN in webui for v0.1.0 to avoid regression for existing dashboard users; webui's CharactersTab gets a `Pro` badge + a note that creation/cloning is moving to the Pro Android app in v0.1.x. The Pro Android app gains a Characters tab in a separate spec (out of scope here).

## Non-goals (deferred / out of scope)

- AR HUD `Presentation` activity on glasses Display 6 — its own v0.1.x spec.
- Pro Android Characters/CreateCharacterWizard/BrowserRecorder — its own v0.1.x spec; the webui's flows stay functional in the meantime.
- Catalog ingestion of Claude Code project dirs that have no codetalker hook history — its own v0.1.x spec.
- Pro Android SessionDetail Feed/Chat tabs — partly built; finishing them is folded into the webui's narration display unification later.

## Architecture overview

```
┌──────────────────────┐         shared state          ┌──────────────────────┐
│ Webui (Basic)        │◀──────── HTTP REST ─────────▶│ Pro Android          │
│ React + react-query  │         + SSE narration       │ Compose + OkHttp     │
└──────────┬───────────┘                               └──────────┬───────────┘
           │                                                       │
           └─────────────────► daemon ◀───────────────────────────┘
                            (Python / Starlette)
                            • state.sessions (in-memory live)
                            • state.persistent_sessions (disk)
                            • state.audio_hub (companion subscribers)
                            • state.cfg (companion_suppress_desktop default)
                            • SSE: /api/narration-stream
                            • REST: /api/sessions, /api/companion/sessions
```

Both surfaces are clients of the same daemon. They read the same response shape from `/api/sessions` (webui) and `/api/companion/sessions` (Pro). They write through the same `PUT /api/sessions/{id}/overlay`. All cross-sync is implicit via the shared daemon.

## Data model changes

### `output_destination` (new)

Per-session field stored in `state.persistent_sessions[sid]["output_destination"]`. Values: `"desktop"`, `"companion"`, `"both"` (default), `"none"`. Set via `PUT /overlay {"output_destination": "..."}`. Exposed on both list endpoints.

Audio worker behavior in `audio.py`:

```python
dest = _resolve_output_destination(job)  # reads persistent overlay, falls back to cfg default
companion_owns = self._companion_owns_audio(job)

if dest == "none" or not job.enabled:
    skip
elif dest == "desktop":
    play_audio_bytes(...)
    # no hub publish
elif dest == "companion":
    if companion_owns: hub.publish(...)
    # no local play
elif dest == "both":
    if companion_owns: hub.publish(...)
    play_audio_bytes(...)
```

The existing `companion_suppress_desktop` cfg flag becomes the default applied when destination is unset — it's the "global tide" while per-session is the "river override".

### `is_speaking` (new on companion endpoint; already exists on `/api/sessions`)

The daemon's audio worker already publishes a `speaking`/`done` event per AudioJob. Set `state.sessions.get(sid).is_speaking = True` while a TTS job for that session is in flight, clear on completion. The webui's `SpeakingDot` already polls this. The Pro Android needs the same field on `/api/companion/sessions`.

### `workspace_group` and `display_name`

Already shipped daemon-side in the v0.1.0 polish — keep as the canonical fields for user-defined grouping and renames. Both surfaces read and write them via the overlay endpoint.

## UI design

### Webui changes (the big refactor)

**SessionsPane** (current: split grid + narration rail) →

```
┌───────────────────────────────────────────────┬─────────────────────────┐
│  Sessions header [Pair AR Companion] [Unpair] │                          │
│  Filter chips: [Live · N] [All · N] [Dormant] │     Live Narration       │
│                [Active · N]                    │     (existing component) │
├───────────────────────────────────────────────┤                          │
│  ▾ OCRacing (3 live · 5 total)                 │                          │
│  ┌────────────────────────────────────────┐   │                          │
│  │ ●  OCR     [ACTIVE] [Mute] [brief|live]│   │                          │
│  │            project: BF-Workspace        │   │                          │
│  │            destination: ●●○ Both        │   │                          │
│  └────────────────────────────────────────┘   │                          │
│  ┌────────────────────────────────────────┐   │                          │
│  │ ○  OCR-Web        [Make active] [Mute] │   │                          │
│  │            destination: ○●○ Companion  │   │                          │
│  └────────────────────────────────────────┘   │                          │
│  ▸ OCDev (collapsed)                           │                          │
│  ▾ Ungrouped (72)                              │                          │
│  ...                                          │                          │
└───────────────────────────────────────────────┴─────────────────────────┘
```

Components:
- `SessionsHeader` — title + Pair AR Companion + Unpair
- `FilterChips` — same semantic as Pro app (Live / All / Dormant / Active) persisted to webui preferences
- `WorkspaceGroupSection` — sticky header with expand/collapse; reads `workspace_group` with `project_dir` humanized fallback
- `SessionRow` (replaces `SessionCard`'s 4-zone layout in this view) — compact card matching the Pro app's row design: live/dormant dot + display name + truncated session id + ACTIVE chip OR Make active button + Mute toggle + brief/live segmented pick + destination indicator + character chip
- `SessionDetailPanel` (new) — opens when a row is clicked (replaces the inline `SessionControls`); shows all the same panel sections the Pro Android does: Name & workspace / Speaking mode / Voice / Cadence / Muted / Markup / Character (read-only) / Destination picker

The narration rail on the right stays as-is — it's the webui's strong point and the Pro Android will gain a Feed tab to mirror it later.

**Activity tab** stays as-is.

**Preferences tab** gains:
- Global default `output_destination` (Desktop / Companion / Both / None)
- Global `companion_suppress_desktop` toggle (= alias for "set default destination to companion")
- Existing app preferences

**Characters tab** keeps current functionality but gains a small "Pro" badge near the title + a one-line note: *"Local voice cloning and animated characters are Pro features. Web creation flows are moving to the Pro Android app in a future release."*

### Pro Android changes

Smaller — most of the polish already shipped. Adds:

- **Per-session destination picker** in SessionDetail's Settings panel (under "Name & workspace"): segmented control with `Desktop / Companion / Both / None`. Writes via `daemonClient.setOutputDestination(sid, value)` thin wrapper.
- **Speaking pulse uses `is_speaking`** from the daemon endpoint (now exposed) instead of just `last_hook_at`. Both signals combined as in the unified flash design.
- **Workspace group inline assignment** stays as just-shipped.

## Daemon changes

- `state.sessions` gains an `is_speaking` field (already exists internally, just needs to be exposed in `/api/companion/sessions`).
- `state.persistent_sessions` schema gains `output_destination`. The `_merge_into_persistent` helper already supports arbitrary keys via the `else` clause; we add an explicit recognized key so it lives at the top level (not nested under `live_overlay`).
- `audio.py` worker queries `output_destination` (with `companion_suppress_desktop` fallback) and routes accordingly.
- Webui's `/api/sessions` list endpoint gains `workspace_group` + `display_name` resolved (it already has `enabled` / `attached_profile` / `attached_character`; the Pro Android polish added `workspace_group` only on the companion endpoint — we mirror it on the broader one for webui parity).

## Implementation phasing

**Phase 1 (this session, in-scope):**
- Daemon: add `is_speaking` to companion endpoint, add `workspace_group` to broader endpoint, add `output_destination` field handling in `_merge_into_persistent` + audio worker
- Daemon: add `auto_mode_enabled` + `auto_mode_idle_threshold_secs` persistent fields + `evaluate_auto_mode` evaluator + hook wiring + `last_user_interaction_at` / `last_manual_mode_change_at` transient fields
- Pro Android: SessionDetail destination picker + auto-mode switch + DaemonClient.setOutputDestination / setAutoMode
- Webui: filter chips + group sections + SessionRow refactor + SessionDetailPanel + Preferences destination default + Characters "Pro" badge + auto-mode switch in Speaking mode section
- Both surfaces: unified flash logic (Compose for Pro, framer-motion for webui), `↻` ribbon on mode chip when auto-mode is on

**Phase 2 (v0.1.x, separate spec):**
- AR HUD Presentation activity on glasses Display 6
- Pro Android Characters/CreateCharacterWizard/BrowserRecorder migration
- Webui Characters tab retreats to read-only display
- Catalog auto-discovery of project dirs without hook history

## Auto-mode switching based on session activity

Per-session toggle that flips `active_mode` between `live` and `brief` automatically based on whether the session is in **interactive** mode (user is currently chatting with Claude Code) or **background** mode (Claude is grinding through tasks without recent user input).

### Signals

The daemon already receives Claude Code's hook events: `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `Notification`. We add a per-session `last_user_interaction_at: float` timestamp on the in-memory session state, bumped whenever:

- `UserPromptSubmit` fires (user typed a new prompt) — primary signal.
- An STT-driven `/api/companion/inject` reaches the session's buddy (user spoke through the AR companion) — secondary signal.

`PreToolUse` / `PostToolUse` / `Stop` do NOT bump it — those are Claude's autonomous work and should NOT count as user interaction.

### Rule

When per-session `auto_mode_enabled = true` (default off; user opts in):

- On every hook event for the session, evaluate:
  - `idle_secs = now - last_user_interaction_at`
  - If `idle_secs < 30`: target `active_mode = "live"`
  - Else: target `active_mode = "brief"`
- If the target differs from the current `active_mode`, apply via the same overlay-update path that the manual brief/live picker uses. The overlay write also persists, so both surfaces see the new mode on their next poll.

The 30-second threshold is the spec default — store it as `auto_mode_idle_threshold_secs` on the session's overlay so power users can tune per-session, with a fleet default in `state.cfg["auto_mode_idle_threshold_secs"] = 30`.

### Edge cases

- **User manually picks a mode while auto-mode is on:** the manual pick wins for 60 seconds (auto-mode pauses), then auto resumes. This prevents the rocker / picker fighting the auto-switcher mid-task. We track `last_manual_mode_change_at` per session for this grace window.
- **No hook fires for a long time:** auto-mode evaluator runs at hook-fire time (cheap); if no hooks fire, no mode change. Sessions that go idle just stay in whatever mode they were last in until activity resumes.
- **AR companion-only audio mode:** auto-mode still applies; brief vs live is about narration density, orthogonal to where audio routes.

### UI

- **Pro Android SessionDetail "Speaking mode" section:** below the manual brief/live picker, a switch labeled "Auto-switch based on activity" + helper text "Briefs background work, goes live when you interact." When enabled, the mode chip shows a small `↻` ribbon to indicate auto-control.
- **Webui SessionDetailPanel:** identical toggle in the Speaking mode section.
- **Sessions list rows:** when auto-mode is on, the inline brief/live quick-pick still shows the CURRENT mode (so you can see what auto chose), but tapping it triggers the manual override + 60s pause (visual hint: tap shows a brief tooltip "manual override · resumes auto in 60s").

### Data model addition

`state.persistent_sessions[sid]` gets two top-level fields:
- `auto_mode_enabled: bool` (default false)
- `auto_mode_idle_threshold_secs: float | None` (default null → fleet default applies)

In-memory `state.sessions[sid]` gains transient fields:
- `last_user_interaction_at: float`
- `last_manual_mode_change_at: float`

Both list endpoints (`/api/sessions`, `/api/companion/sessions`) expose `auto_mode_enabled` and the resolved `active_mode` (already there). The webui's existing config-poll picks up auto-driven mode changes automatically; same for the Pro Android.

### Implementation hook

The auto-mode evaluator is a small function `evaluate_auto_mode(state, sid)` invoked at the END of every hook handler that updates `last_user_interaction_at` AND at the end of every tool-call hook. It reads the session's persistent + in-memory state, applies the rule, calls `state.sessions.update_overlay(sid, {"active_mode": target})` only when target differs from current (so we don't flood writes).

## Cross-device toggles (the "obvious toggles" ask)

Three places the user can flip output:

1. **Per-session destination picker** on the SessionDetail panel — primary control. Affects only that session.
2. **Preferences → "Default destination for new sessions"** in webui — global default applied to sessions that haven't been explicitly set. Affects new + unassigned sessions.
3. **Companion app Preferences → "Companion takes over desktop"** — convenience toggle on Pro Android that sets the global default to `companion`. Same backing flag as #2.

All three write to the same daemon state; both surfaces poll and converge within 5s.

## Verification

The spec succeeds when:

1. A session muted from the Pro app shows muted in the webui within 5s; mode change, destination change, workspace_group assignment, display_name rename all sync the same way.
2. Tapping "Make active" on either surface flips both their `ACTIVE` badges within 5s.
3. With `output_destination = companion` set, an inject test plays audio only through the glasses; with `destination = desktop`, only through the desktop; with `both`, both; with `none`, neither.
4. With `is_speaking = true` on a session, both surfaces render the strong pulse; when it clears, only the recency dim remains for 10s, then the row goes idle.
5. Workspace group sections in the webui match the same groups (and same labels) the Pro Android shows for the same session set.

## Out-of-spec touches deliberately left in place

- The webui's narration rail stays alongside the Sessions tab — same SSE source, same component. Pro Android's Feed tab (when shipped) will consume the same `/api/narration-stream`.
- React-query `staleTime` of 4–5s stays the canonical poll cadence on both surfaces.
- DataStore for Pro Android filter/group state + react-query for webui — different storage layers, same semantics.
- The Pro app's three-tier hardware button design (rocker nav / click select / click mute / hold-to-talk + STT ding) is Pro-only and stays as-is; the webui equivalents are mouse + keyboard.

## Open questions queued for v0.1.x

- Whether the global `companion_suppress_desktop` should auto-toggle based on companion connection state (e.g., when AR companion is actively subscribed, default to companion-only).
- Whether destination = `companion` should fall back to `both` when the companion has disconnected for > 30s (so audio doesn't vanish unexpectedly).
- Whether the Characters tab should ever appear in the Pro Android app or whether character management is a webui-only flow (Pro picks/attaches but doesn't create).
