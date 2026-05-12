# 2026-05-10 — Pro Release Polish & Verification

## Context

We are preparing a polished release of codetalker v0.1.0 spanning two product tiers:

- **Basic** — the webui React dashboard, paired with the local daemon. Browser-only.
- **Pro** — the companion-android app, optionally with XREAL One Pro glasses. The Android app works standalone (Tier 2 = phone-only) or with glasses (Tier 3 = AR HUD). Both share the same APK.

**Pro-exclusive differentiators (marketing positioning):**
- Local voice cloning (recording user voice samples, binding to characters).
- Animated 3D character avatars (Meshy / Hyper3D Rodin / Tripo3D meshes rendered as animated avatars on AR HUD or in-app).

The polish pass does not move existing character/cloning UIs out of webui in v0.1.0; it treats this as positioning + roadmap context. If webui's CharactersTab feels overbuilt for the Basic tier, future passes can gate it behind a Pro badge.

CCT-32 marked 40/40 release-prep tasks as done, but a live hardware test session on Beam Pro + XREAL One Pro surfaced real bugs and rough edges. The user has directed a comprehensive polish pass: design, build, test, polish all aspects across both tiers.

This spec is the consolidated polish + verification scope. Out-of-scope items are listed at the bottom and queued for v0.1.x.

## Goals

1. Every bug surfaced during the live hardware test is fixed.
2. The Sessions list on **Pro** reaches feature parity with the Basic webui's session affordances, plus the inline controls + grouping the user requested.
3. The Basic webui CCT-28 refinements (originally deferred) ship now so the polish bar is consistent across surfaces.
4. The hardware test runs cleanly end-to-end (Phases 1–4) on Beam Pro + XREAL One Pro.
5. The E2E gate script passes; signed AAB + APK build without warnings.
6. Test artifacts and screenshots stay on disk (offload pattern); the conversation's context stays clean.

## Polish bundle

### A. Bug fixes (surfaced in live test)

**A.1 SessionDetail "unexpected end of stream" on dormant rows.**
- Root cause: `/api/companion/sessions` returns the full catalog (82 rows). `/api/sessions/{id}` only resolves sessions in `state.sessions` (in-memory active set). Tapping any dormant row produces a 404 with empty body, which OkHttp surfaces as the cryptic "unexpected end of stream on http://...".
- Fix: in `DaemonClient.getSession()`, branch on `resp.code` and throw an `AppError` ("session no longer active — refresh list") on 404 specifically; map other failures to the existing AppErrors. SessionDetailScreen translates that into a recoverable banner with a Refresh action.
- Files: `companion-android/app/src/main/kotlin/.../net/DaemonClient.kt`, `.../ui/SessionDetailScreen.kt`, `.../ui/errors/AppErrors.kt`.

**A.2 PairingScreen ManualEntryScreen URL field default `"http://"` causes typing to append.**
- Root cause: `var url by remember { mutableStateOf("http://") }` at `PairingScreen.kt:105` — value (not placeholder).
- Fix: empty default + use OutlinedTextField `placeholder` slot for `"http://"`. On Save, if the value doesn't start with `http://` or `https://`, prepend `http://` before calling `saveManual`.
- Files: `companion-android/app/src/main/kotlin/.../ui/PairingScreen.kt`.

### B. Sessions list redesign (Pro)

Bring the Pro companion's SessionListScreen to parity with the Basic webui's SessionCard affordances, plus inline list-level controls and grouping. Each row becomes a small card with:

- **Live/dormant marker**: green pulse for `is_live`; muted grey for dormant. Match the web's `border-l-emerald-500` vs `border-l-rose-500` visual language.
- **Speaking flash**: when a session is currently emitting TTS (`is_speaking`), the row's border pulses. Pulse runs even when `is_muted` is true (because muting suppresses audio, not activity — and finding active sessions while debugging is the use case).
- **Active-session indicator + setter**: the companion's currently-active session has an `ACTIVE` chip; tap the chip on any other row to make THAT row active (calls `POST /api/companion/active-session`).
- **Inline mute toggle**: small icon button on the row, calls `PUT /api/sessions/{id}/overlay {"enabled": <toggled>}`.
- **Inline brief/live quick-pick**: two-button segmented control (`brief` / `live`), calls `PUT /api/sessions/{id}/overlay {"active_mode": ...}`.
- **Filter pills at the top of the list**: `All` / `Live` / `Dormant` / `Active`. Default to `Live`. Filter state persists in DataStore.
- **Grouping by project_slug**: section headers like `codetalker (12)`, `Workspace (38)`, `Wish (3)`. Collapse/expand per group; persisted in DataStore.

Files touched:
- `companion-android/app/src/main/kotlin/.../ui/SessionListScreen.kt` (full rewrite of the row Composable; add filter chip strip + group headers + LazyColumn rebuild)
- `companion-android/app/src/main/kotlin/.../net/SessionLite.kt` (extend with `isSpeaking`, `isMuted` fields if missing — verify against current daemon JSON shape)
- `companion-android/app/src/main/kotlin/.../net/DaemonClient.kt` (add `setMuted(sessionId, muted)` and `setMode(sessionId, mode)` thin wrappers around the overlay PUT)
- `companion-android/app/src/main/kotlin/.../data/SessionListPrefs.kt` (NEW — DataStore-backed filter + group-expansion state)

### C. Webui refinements (Basic, from CCT-28 — deferred items now in scope)

**C.1 Headline precedence flicker.** SessionCard headline uses `session.display_name || session.session_id.slice(0,8)` already — good. CCT-28 noted the previous `title` fallback was the bug; verify it's gone in the current SessionCard.tsx and remove if any code path still reads `session.title`. **Quick verify, then remove if found.**

**C.2 Focus loss during edits.** Add `placeholderData: keepPreviousData` to `useSessions` and `useSessionConfig`. Memoize `SessionCard`, `ProjectBadge` if not already memo'd.

**C.3 Twitchy re-renders.** In `SessionGrid.tsx`, the sort already uses `useMemo` — confirm. Add `layout` prop on `motion.article` in SessionCard (CCT-28 recommended). Bucket relative-time display by minute via a util.

Files:
- `core/claude_code_talker/webui/src/hooks/useSessions.ts`
- `core/claude_code_talker/webui/src/hooks/useSessionConfig.ts`
- `core/claude_code_talker/webui/src/components/SessionCard.tsx`
- `core/claude_code_talker/webui/src/components/SessionGrid.tsx`
- `core/claude_code_talker/webui/src/components/ProjectBadge.tsx`
- `core/claude_code_talker/webui/src/util/relativeTime.ts` (NEW if missing)

### D. Daemon

Audit whether the existing endpoints are sufficient for the Pro inline controls:

- `POST /api/companion/active-session` — already exists.
- `PUT /api/sessions/{id}/overlay` — already exists; accepts `{"enabled": bool, "active_mode": str, "voice": {...}, "live": {"cadence": ...}}` etc.

No new daemon endpoints needed. **But**: ensure `/api/companion/sessions` response includes `is_speaking` and `is_muted` so the Pro UI can render the flash + muted chip without an extra round-trip. If absent, add them.

Files (if needed):
- `core/claude_code_talker/companion/api.py` (list_sessions response shape)
- `core/claude_code_talker/sessions.py` (source of is_speaking / is_muted)

### E. Verification (the test plan, polished)

Hardware test resumes after the polish lands. All test artifacts use the screenshot offload pattern from the original plan: PNGs on disk, visual-analyst subagent reads them in its own context, only text reports flow back here.

**E.1 webui smoke (Basic):**
- `npm run build` succeeds without errors
- `python -m claude_code_talker.daemon` serves the dashboard
- Browser opens dashboard at `http://localhost:17832/`
- Click around: Sessions tab loads, SessionCard renders correctly, dropdown selects stay open during edits (CCT-28 fix verification)

**E.2 Pro Phase 1 — phone-side functional walk:** Re-runs the original Phase 1 with the polished UI. Adds verification of the new filter chip strip, group headers, inline mute toggle, brief/live quick-pick, current-session setter.

**E.3 Pro Phase 2 — audio loop.** Direct daemon API drives TTS on a live session. Human confirms audio via Beam Pro speakers / earbuds. Mute toggle silences. Character voice (Dr. Crow cloned) sounds distinct.

**E.4 Pro Phase 3 — AR HUD on XREAL One Pro (Display 6).** Display 6 confirmed (1920×1080@90Hz, FLAG_PRESENTATION + FLAG_SECURE). Human wears glasses; daemon injects caption; human confirms render. `screencap -d 6` likely returns black (FLAG_SECURE) — this is expected and the plan falls back to human verdict.

**E.5 Pro Phase 4 — STT round-trip.** Try `adb shell input keyevent KEYCODE_HEADSETHOOK` first; fall back to human button-press. Verify daemon-side buddy receives text, replies via SSE, audio plays, caption renders.

**E.6 E2E gate script:** `bash companion-android/scripts/e2e/run_release_check.sh` passes the post-pairing tasks now that pairing is established.

**E.7 Signed release builds:**
- `./gradlew bundleRelease` produces `app-release.aab`
- `./gradlew assembleRelease` produces `app-release.apk`
- Both signed with the production keystore (already rotated per user's prior session)

## Architecture notes

- The Pro Sessions list refactor introduces a new `SessionListPrefs` DataStore for filter/group-expansion state. Keep the state local; do not push to daemon (each device's filter preferences are personal).
- Inline mute / mode / active-session controls do **not** open SessionDetail. The detail screen is preserved for the full picker set (voice, cadence, markup quick panel, character attach). Inline list controls are the quick path; detail is the deep path.
- Speaking flash uses Compose's `infiniteRepeatable` `animateFloat` for a 2-state pulse on the border. Runs only when `isSpeaking` is true. Cheap enough — single float interpolation per visible row.
- Filter pills are `FilterChip` Composables (Material3). Default selection persisted to DataStore.

## Out of scope (queued for v0.1.x)

- Audio cuts when screen turns off and the foreground notification is dismissed (lifecycle hardening cat. 2).
- Pairing token auto-renew UI before expiry.
- Multi-daemon support (one pairing = one daemon today).
- 3D character avatar render on AR HUD (Phase 8 deferred per CCT-32 master plan).
- Dead `events` field cleanup in webui types (Phase 27 leftover; cosmetic).

## Verification of THIS spec

The spec is complete when:

1. Every polish item in §A/B/C/D ships as a code change in the right file(s), reviewed against this doc.
2. §E test phases all produce either text PASS verdicts (E.2, E.6) or recorded human verdicts (E.3, E.4).
3. Signed AAB + APK exist under `companion-android/app/build/outputs/`.
4. A final `test-report.md` lands in the per-run `C:\tmp\codetalker-hw-<ts>\` directory summarizing every phase.
5. No PNG bytes entered the main conversation context during the run (offload pattern held).
