# Phase 0 — Deferred Tasks (P0-C, P0-D)

**Filed:** 2026-05-12
**Status:** Deferred from the Phase 0 sweep; tracked here for pickup in a follow-up session.
**Plan reference:** `docs/superpowers/plans/2026-05-11-vNext-phase-0-implementation.md` Tasks 3 + 4.

## Why deferred

Both tasks target Android files in `companion-android/`, which lives in a **separate `codetalker-pro` private git repo** (per the CCT-30 / CCT-31 spec entries). The `companion-android/` directory is `.gitignore`d in the public `codetalker` repo and has its own `.git/` inside.

At the time of the Phase 0 sweep, that companion-android working tree had **substantial uncommitted work-in-progress**: ~1,875 line insertions across 18 files, including the very files P0-C and P0-D target (`DaemonClient.kt`, `SessionListScreen.kt`, `MainActivity.kt`, `CompanionViewModel.kt`).

Executing P0-C and P0-D on top of that uncommitted in-flight work would (a) conflict structurally, and (b) entangle the Phase 0 release-prep delta with a much larger unrelated feature stream. Both tasks were therefore deferred until the in-flight work lands as its own session checkpoint.

## P0-C status (STT caption display)

**Originally specified:** Wire `CompanionViewModel.captionText` into a visible Composable on `SessionDetailScreen` and replace HudLayer "listening"/"sending" literals with the live caption.

**In-flight state found 2026-05-11:**
- `CompanionViewModel.captionText` already exists as `MutableStateFlow("")` (line 40).
- SSE events are already wired into `captionText`: `STTEvent.Partial -> captionText.value = event.text` (line 61).
- A new untracked file `BuddyChatPanel.kt` already collects `viewModel.captionText` and renders it as visible UI (lines 55, 77, 97-98, 109).

**Conclusion:** P0-C is **effectively already implemented** by the in-flight `BuddyChatPanel.kt` work. The audit finding ("captionText is set but never collected on a visible Composable") was stale — written before the in-flight work began. Once the companion-android work is committed, **verify** that the user can actually see the live caption during dispatch and the HudLayer literals are replaced; if any gap remains, file a tight follow-up.

**Pickup procedure:**
1. Wait for user to commit the in-flight companion-android session work.
2. From the resulting commit, verify `BuddyChatPanel.kt` renders during STT dispatch.
3. If `HudLayer.kt` still shows literal "listening"/"sending" instead of caption, re-plan P0-C with the new file structure.
4. Otherwise, close P0-C as ✅ done-by-incident.

## P0-D status (Mute UX banner)

**Originally specified:** Add red "🔇 TTS muted — tap to unmute" banner to `SessionListScreen` when daemon `enabled=false`, polled every ~5s with one-tap `POST /api/unmute`.

**In-flight state found 2026-05-11:**
- `DaemonClient.kt` has 341 line changes (no `getStatusEnabled()` or `globalUnmute()` yet).
- `SessionListScreen.kt` has 661 line changes (no banner yet).

**Conclusion:** The mute-banner UX work is still legitimately missing. The bug it addresses (silent global mute with no UI indicator on the phone) remains a recurring footgun. But the planned edits would heavily conflict with the in-flight changes.

**Pickup procedure:**
1. Wait for user to commit the in-flight companion-android session work.
2. Re-read `DaemonClient.kt` + `SessionListScreen.kt` against the new committed state.
3. Re-plan the P0-D edits with adjusted line numbers and surrounding context.
4. Dispatch a fresh P0-D implementer subagent (haiku or sonnet, ~120 LOC task).

## Other Phase 0 follow-ups (closed in mop-up sweep 06cb85f, 2026-05-12)

All three items below emerged from the integrated review of P0-A/B/E/F. **All closed** in the Phase 0 mop-up dispatch (merge commit `06cb85f` on `vNext`):

1. ✅ **P0-A integration test gap** (Important) — landed in commit `6f0f249` as `test_clone_voice_then_attach_character` in `core/tests/test_voices_clone_e2e.py`. Test clones a voice, attaches it to a character, asserts `voice_ok=True` via the 200 status of `/api/sessions/{sid}/attach-character`.
2. ✅ **P0-A dead-code cleanup** (Minor) — landed in commit `69c9f51`. The `if char.voice_ref.startswith("char-")` block plus the Phase-25c stub-clone comment are gone from `api.py`. Engine `list_voices()` check is the only voice-validation path now.
3. ✅ **P0-E skip extension** (Minor) — landed in commit `77f316e`. `test_e2e_v2.py::test_e2e_live_mode_per_tool_call` is function-level skipped (Option B); the other two tests in that file (`test_e2e_stop_via_mcp_client`, `test_e2e_notification_via_mcp_client`) still run cleanly.

## New follow-up from the mop-up code-quality review (2026-05-12)

1. 🟡 **XTTS test-fixture extraction** (Important, deferred to a future cleanup pass). The mop-up code-quality reviewer flagged that `core/tests/test_voices_clone_e2e.py` now has two tests that duplicate the XTTS config setup pattern (defensive null-check + `state.cfg["engines"]["xtts"]["references_dir"] = ...`) and the `fake_clone` closure. Extract to a shared `@pytest.fixture` before a third consumer arrives — would be ~15 LOC of cleanup. Same file also has a magic `"xtts"` engine-dict key worth promoting to a module-level constant.

   Not a merge blocker — the reviewer explicitly said "should be refactored before the file grows further" (future-tense). File here so it doesn't get lost.

## 2026-05-13 session additions — hardware-verified follow-ups

After the post-reboot hardware testing session, these items emerged:

### Direct-STT (vol-up long-press) — landed and verified ✅

Daemon endpoint `/api/companion/direct-stt` + Windows SendKeys helper landed in commit `0ed8b2e`. Kotlin wiring in companion-android (HardwareKeys vol-up long-press, ButtonInput LongPressUp/HoldEndUp variants, MainActivity routing, CompanionButtonHandler new methods, SessionDetailScreen handlers, CompanionViewModel SttMode enum + branched dispatch, DaemonClient.postDirectStt) is **uncommitted in the private repo, intentional** — belongs to the user to commit.

Hardware verification proof: user test message *"This is a test resp"* arrived as a typed user message in the active Claude Code session via the SendKeys path.

### Session-view fixes — landed and verified ✅

Three bugs found while diagnosing why the phone showed only 1 of the user's 6 active CC sessions:

- **Visibility filter (24h)**: drops catalog entries whose transcript hasn't been touched in 24h. Result: 95 → 14 entries (and naturally less when sessions age out).
- **Live window (60s → 300s)**: `TRANSCRIPT_LIVE_WINDOW_SEC` raised so an active CC session pausing for the user to read a response doesn't flicker out of "live".
- **workspace_group auto-derive heuristic**: OCR-* → OCRacing, CodeTalker/CTDev/CTWeb/OCM → OCDev, BlueprintForge → BlueprintForge.
- **Companion is_live mirrors webui**: `(live_match is not None) or (sid in disk_active_sids)` — phone now reports Live count immediately post-daemon-restart instead of waiting for first hook.

Commits: `5b7853a` + `62cc400`. The `_derive_workspace_group` helper is duplicated in `api.py` and `companion/api.py` — consolidate during P1-B api.py decomposition.

### 🟡 STT truncation tuning (Important follow-up)

Direct-STT works end-to-end but the test transcript got cut mid-word ("resp" instead of "response"). Probable causes:

- Android `SpeechRecognizer.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS` aggressive default
- LongPressDetector's `onHoldEnd` fires before the recognizer's final-text event lands in `lastFinalText`
- Network/SendKeys flush race

Quick fix idea: add a 200-300ms grace window in CompanionViewModel.dispatch() that waits for any pending STT final-text event before reading `lastFinalText`.

### 🟡 Settings-save UI bug (Important follow-up)

User reported settings changes on SessionDetail not persisting. Daemon API verified to write correctly to disk (`/api/persistent-sessions/{sid}` reads back the overlay). The bug is one of:

- Phone PUT request not firing (network/auth/code path)
- Phone UI not reflecting post-save state (display bug)

Next diagnostic step: capture phone HTTP traffic while user changes a setting; see if PUT lands at the daemon. If not → phone-side bug. If yes → UI redraw issue.

### 🟢 Audio routing requires explicit `audio_outputs: ["phone"]`

Discovered today. Without this overlay, the daemon synthesizes narration but only publishes to desktop. Phone gets silence even though it's subscribed.

Fixed for the user's 4 active sessions via API. Consider:

- **Auto-set on subscribe**: when `companion_active_sessions.add(sid)` fires, default `audio_outputs` to include `"phone"` if it's null.
- **Make this discoverable in UI**: the phone's SessionDetail should show + let the user toggle the routing list. Currently invisible.

### IME-conflict gotcha for adb-driven UI testing

When tapping a button via `adb shell input tap X Y`, if the on-screen keyboard is showing and the tap Y coordinate overlaps the keyboard area, the tap goes to the keyboard (typing a character) instead of the intended button. ALWAYS hide IME with `KEYCODE_BACK` before tapping buttons near screen bottom. Spent ~5 min today debugging this when the Save button at (312, 1643) was typing an `e` into the token field below.

### Phone post-reboot pair flow

Phone reboots wipe its AppPreferences pairing state. Re-pair flow:

1. Discover wireless ADB port: `adb mdns services` (requires phone Wireless Debugging foreground)
2. `adb connect 192.168.1.132:<port>`
3. Generate fresh pair token: `curl -X POST -H "Content-Type: application/json" -d '{"label":"..."}' http://127.0.0.1:17832/api/companion/pair`
4. Drive phone manual-entry pair via adb taps + `input text` for URL + token + Save (remember to hide IME before Save tap)
5. Daemon-side pair tokens are persistent on disk; old tokens stay valid until expiry even after re-pair.

## Pre-P0 regression triage (Phase 0.5 cleanup punch list)

A full pytest run after Phase 0 landed: **1061 passed / 11 failed / 16 skipped (~7.4h — slow Piper fixture loading inflates wall time; total CPU not as bad)**. Of the 11 failures, only one is downstream of P0 work (item #3 above). The other 10 are **pre-existing regressions from the session-base commit `ce8e4ca`** (audio_hub backpressure refactor, /ui retirement, sessions-character-attach reshape):

| Test | Likely cause |
|------|--------------|
| `test_audio_companion_fanout.py::test_worker_fans_synthesized_audio_to_hub` | audio_hub backpressure (ce8e4ca) |
| `test_audio_companion_fanout.py::test_worker_no_fanout_when_hub_is_none` | audio_hub backpressure (ce8e4ca) |
| `test_audio_priority.py::test_alert_jumps_normal` | audio queue priority (ce8e4ca) |
| `test_audio_priority.py::test_stale_jobs_dropped_on_dispatch` | audio queue priority (ce8e4ca) |
| `test_audio_queue.py::test_worker_synthesizes_and_plays` | audio worker refactor (ce8e4ca) |
| `test_audio_queue.py::test_worker_continues_after_synth_error` | audio worker refactor (ce8e4ca) |
| `test_audio_queue.py::test_worker_continues_after_play_error` | audio worker refactor (ce8e4ca) |
| `test_openai_chat_provider.py::test_default_stream_yields_complete_for_non_streaming_provider` | OpenAI provider streaming |
| `test_server_transport.py::test_composed_app_serves_static_ui_route` | /ui retirement (now 302 redirect) |
| `test_sessions_character_attach.py::test_api_sessions_response_includes_attached_character` | sessions response shape |

These are **NOT P0's responsibility** but they cap a quality gate that should be cleared before Phase 1 ships (or earlier — pre-Phase-1 in a "Phase 0.5 stabilize" pass). Each failure is in a test for code that landed in `ce8e4ca` (the single big session-end commit on main) and was carried into `vNext` as the branch base. Updating the tests to the new contracts is the typical fix path.

**Slow test investigation**: The 7h24min wall-clock for 1088 tests is suspicious. Likely a few tests load Piper/XTTS models from disk per-call instead of session-fixture-cached. Worth profiling before CI signs off.

**Update 2026-05-12 (post-Phase-0.5):** A focused 10-file subset run (88 tests, 17m39s) with `--durations=15` revealed three concrete time-hog clusters:

| Cluster | Tests | Time each | Likely cause |
|---|---|---|---|
| `test_e2e_v2.py` setup | 2 setups | ~109-120s | uvicorn-thread fixture + model loading per-test (should be session-scoped) |
| Voice clone tests | 2 tests | ~108-118s | real XTTS cloning logic — possibly engine init per-test (session-scope candidate) |
| `test_sessions_character_attach.py` | 6 tests | 30-107s | full ASGI app build per-test (single session-scoped app fixture would batch them) |

These three clusters account for ~13 of the 17 minutes in the focused subset. The fix pattern is consistent: convert per-test fixtures to `@pytest.fixture(scope="session")` for the heavy objects (ASGI app, XTTS engine, uvicorn thread). One sweep dispatch could likely cut the broader run to <5min and the full 1088-test run from 7h to under an hour. File as a single Phase 0.5 follow-up or roll into Phase 1's stabilization budget.

## What's in `vNext` after Phase 0

- 4 task commits: P0-A (×2 commits — impl + review-fix), P0-B, P0-E, P0-F
- 4 merge commits (no-ff): one per task into `vNext`
- Tag: `vNext-P0-gate`

Phase 1 can branch from `vNext-P0-gate` safely; the deferred Android tasks are tracked here and don't block Phase 1 critical-path work (open-core foundation, extension points, schema).
