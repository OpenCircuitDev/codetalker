# v0.1.0 — Basic + Pro Unification

Cross-surface unification pass making the webui dashboard and Pro Android app
feel like one product. Same session organization, same flash signals, same
toggles, same mental model.

## Headline changes

### Webui Sessions tab — full layout overhaul

The previous flat 3-column live-only `SessionCard` grid is replaced with a
sidebar-style layout that mirrors the Pro Android `SessionListScreen`:

- **Filter pills** — Live / All / Dormant / Active with live counts
- **Workspace groups** — sticky uppercase headers with expand/collapse triangles
  and live/total counts (`2/5` format)
- **Compact `SessionRow`** — single-line, dot prefix, hover-revealed controls
  (pin, destination pips, brief/live picker, mute)
- **`SessionDetailPanel`** — 8-section side panel (Name & workspace, Speaking
  mode, Audio destination, Voice, Cadence, Muted, Character, Markup) opens when
  a row is clicked
- **Per-group settings icon** (sliders) hover-revealed on each group header
- **"Ungrouped" section** always sorts last with muted styling

### Per-session pin-to-top

Click the pin glyph on any session row to pin it to the top of its workspace
group. Pinned sessions render with an amber pin icon prefix; sort priority is
`pinned > is_live > last_modified desc`. Persisted in the daemon overlay so
the pin syncs across webui + Pro Android.

### Multi-select audio destination (per-session)

The old `output_destination: "desktop"|"companion"|"both"|"none"` enum is
replaced with `audio_outputs: List["desktop"|"phone"|"glasses"]`. Reflects the
real hardware: phone speakers and XREAL Beam Pro USB-Audio glasses are
independent sinks. Three-chip multi-select picker in the detail panel + Pro
Android equivalent. `null` = inherit fleet default; `[]` = silenced everywhere;
any subset = explicit override.

### Fleet-default audio routing toggle

New `/api/cfg/audio-defaults` endpoint backs a "Companion takes over desktop"
toggle in webui Preferences. When on, the fleet default for unassigned sessions
becomes `{phone, glasses}`. Persisted to `cfg-overlay.yaml`.

### Auto-mode (live ↔ brief switching)

Per-session `auto_mode_enabled` toggle in the detail panel. When on, the
session's `active_mode` flips to `live` while the user is interacting (via
prompts or STT-driven inject) and back to `brief` after 30s of background-only
activity. Manual mode picks pause auto-mode for 60s so the user's explicit
choice isn't immediately overwritten.

### Character picker (per-session)

The Character section in the detail panel is now interactive — lists all
characters from `/api/characters` with attach/detach buttons. Each library row
shows `mesh_provider` (e.g. `meshy`) so the source is visible at a glance.
Replaces the previous read-only display.

### Group + name parity with Pro Android

- **`groupLabelFor`** webui helper mirrors Pro Android's `workspaceLabel()`:
  `workspace_group > humanized project_dir > cwd leaf > project_slug > "Ungrouped"`.
- **`humanizeProjectDir`** ports Android's heuristic for
  `C--Users-brand-Dropbox-...-Workspace` → `BF / Workspace` style cleanup.
- **Daemon now exposes `project_dir` on `/api/sessions`** (was companion-endpoint-only).

### `/title` rename freshness

`list_sessions` re-reads the latest `customTitle` from each live transcript's
JSONL tail on every request. Renames in Claude Code via `/title <name>` now
surface in the webui within 5 seconds (next react-query poll) instead of
waiting up to 30 seconds for the catalog watcher.

### Transcript-mtime liveness

A session is `is_live=True` if EITHER it has an in-memory `SessionState`
(fired a hook recently) OR its transcript file was modified within the last
60 seconds. Catches CC sessions that are open but haven't fired tool-event
hooks yet. Also triggers an on-demand catalog refresh when disk-active SIDs
aren't yet cataloged, so brand-new sessions appear within 5 seconds.

### Sweeper threshold bump

`SessionRegistry.expire_idle()` default bumped from 30 minutes to 8 hours.
Sessions you opened in the morning stay "live" through lunch. LRU cap
(`max_active=50`) prevents unbounded memory growth.

### Account-switch resilience

`SessionGrid` now prunes stale state when the catalog changes:

- Stale `collapsedGroups` localStorage entries (groups no longer in the catalog)
  are dropped on the next render.
- Stale react-query `["session-config", sid]` caches are evicted when a
  session-id leaves the catalog.
- The detail panel's `openSessionId` is implicitly cleared because
  `sortedSessions.find()` returns undefined for a missing SID.

Both prune effects gated on `data !== undefined` so they don't fire during
the first-paint empty state.

### Save-feedback UX

Editing the Session Name or Workspace group input shows a green
`✓ saved · row moved to new group` flash next to the field label after blur
(1.5s). Helper text under the input: "Press Enter or click outside to save."
Critical because workspace_group changes also re-shuffle the row into a new
group, which previously looked like the input "lost" the value rather than
committed it.

### "Reset to follow Claude Code"

Small text-button below the Session Name input. Clears the persistent
`display_name` override so future `/title` renames in CC win again. Without
this affordance, once you renamed in the codetalker UI, `/title` was
permanently ignored for that session.

### Derived workspace_group autocomplete

The workspace_group input's datalist now derives from the unique set of
`workspace_group` values across the session catalog, deduped + sorted. Falls
back to `OCR / OCDev / CodeTalker` when no assignments exist yet.

### Character display bug fix

`/api/sessions` now resolves `attached_character` IDs to full records (was
returning bare strings like `"dr-crow"` that broke the `CharacterAvatar`
render). Webui has defensive `resolveAttachedCharacter()` for backwards
compatibility with older daemons.

### Self-healing migration

`PersistentSessionStore.get()` lifts orphan keys from `live_overlay` to
top-level on read (`pinned`, `workspace_group`, `audio_outputs`,
`auto_mode_enabled`, `auto_mode_idle_threshold_secs`, `display_name`). Cleans
up overlays written by pre-fix daemon code where the merge handler didn't
recognize the keys yet.

### Unified flash logic

`SessionRow.FlashDot` mirrors the Pro Android pattern:

- Strong pulse (0.9s, 1→1.4 scale) when `is_speaking=true`
- Ambient pulse (2.2s, gentle) when last hook fired within 10s
- Steady green ring outline when this is the companion's currently-active
  session
- Muted: rose dot, no animation

### Pro Android parity

- `SessionLite.audioOutputs: List<String>?` + `setAudioOutputs(sid, list?)` helper
- `SessionLite.autoModeEnabled: Boolean` + `setAutoMode(sid, enabled)` helper
- `SessionLite.pinned: Boolean` + `setPinned(sid, pinned)` helper
- `SessionLite.isSpeaking: Boolean` for unified flash
- `DestinationPicker` rewritten to 3-chip multi-select on
  `SessionDetailScreen.kt` with "Reset to default" affordance
- `SessionListScreen` `↻ auto` ribbon when auto-mode is on
- Built + installed on connected XREAL devices (X4200 over USB-ADB + wifi-ADB)

### `[Pro]` badge on webui Characters tab

Local voice cloning and animated 3D characters are Pro features. The webui's
CharactersTab keeps its existing functionality for v0.1.0 but gains a `[PRO]`
badge near the title and a one-line subtitle:
*"Local voice cloning and animated characters are Pro features. Web creation
flows are moving to the Pro Android app in v0.1.x."*

## New endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/cfg/audio-defaults` | Read fleet `companion_suppress_desktop` flag + resolved `default_outputs` |
| PUT | `/api/cfg/audio-defaults` | Write the fleet flag (persists to cfg-overlay.yaml) |

## New persistent overlay keys

All recognized as top-level by `_merge_into_persistent`:

- `workspace_group: str | null` — user-defined group label
- `audio_outputs: List[str] | null` — multi-select destinations
- `auto_mode_enabled: bool`
- `auto_mode_idle_threshold_secs: float | null` — fleet default applies if null
- `pinned: bool`

## New tooling

### `scripts/bulk_assign_workspace_group.py`

Bulk-assigns `workspace_group` to sessions matching pattern rules (cwd,
display_name, project_dir, project_slug). Dry-run by default, `--apply` to
commit, `--clear` to wipe all assignments. Distribution summary shows
"X already, Y to migrate" so the user always sees the full picture, not
just the diff.

Default rules (edit RULES at top of file to fit your projects):

1. CodeTalker — sessions in codetalker repo or named CodeTalker/CT*
2. OCDev — `ocr-memory-palace` / `ocr-forge` cwds, `OCDev` in name
3. OCR — broad catch-all for OCR-flavored work in BF_Workspace / Open_Circuit

## Test coverage added

- 16 webui grouping tests (humanizeProjectDir, groupLabelFor, groupSessions, pin sort)
- 4 webui pin-sort tests
- 6 daemon audio-defaults tests
- 14 bulk-assign rule tests
- 6 self-healing migration tests
- 3 transcript-mtime liveness tests

Total: **62 webui tests + ~30 new daemon tests**, all green.

## Verification gated on user actions

- **Daemon restart** activates 9 server-side fixes in one go (audio-defaults
  endpoint, project_dir field, custom_title freshness, pinned merge,
  attached_character resolve, transcript-mtime liveness, on-demand catalog
  refresh, self-healing migration, sweeper bump).
- **`python scripts/bulk_assign_workspace_group.py --apply`** to migrate the
  21 sessions matching the default rules into OCR/CodeTalker/OCDev.
- **Pro Android cross-surface smoke** — mute on Pro → see in webui within 5s,
  audio routing matrix (6 sub-cases), workspace_group parity.

## Out-of-scope (deferred to v0.1.x)

- AR HUD `Presentation` activity on glasses Display 6
- Pro Android Characters tab (CreateCharacterWizard / BrowserRecorder migration)
- Webui Characters tab retreats to read-only display
- VSCode label change watcher (currently propagates within 30s via catalog scan)
- Multi-select bulk row actions in webui
- Drag-to-reorder within a group
