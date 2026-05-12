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

## Other Phase 0 follow-ups (surfaced by the final reviewer)

These are not P0-C/P0-D blockers but emerged from the integrated review of P0-A/B/E/F. File separately when picked up:

1. **P0-A integration test gap** (Important). Add `test_clone_voice_then_attach_character()` covering: clone a voice → save voice_ref to a character → attach character → assert `voice_ok=True`. This validates the voice_ref naming convention end-to-end and surfaces XTTS engine registration assumptions.

2. **P0-A dead-code cleanup** (Minor). `api.py:1247-1249` has stub-format compat logic (`if voice_ref.startswith("char-")`) that's now unreachable since the stub was removed in P0-A. Remove or rewrite the comment to clarify it's legacy-only.

3. **P0-E skip extension** (Minor). The full pytest run after Phase 0 surfaced `test_e2e_v2.py::test_e2e_live_mode_per_tool_call` failing with `NotImplementedError` from P0-E's `_call_mcp_tool` shim. P0-E skipped `test_e2e.py` + `test_hook_cli.py` at module level, but missed this third file in the same neighborhood. Either skip it with the same reason, or rewrite to mock `_post_hook` instead of `_call_mcp_tool`.

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

## What's in `vNext` after Phase 0

- 4 task commits: P0-A (×2 commits — impl + review-fix), P0-B, P0-E, P0-F
- 4 merge commits (no-ff): one per task into `vNext`
- Tag: `vNext-P0-gate`

Phase 1 can branch from `vNext-P0-gate` safely; the deferred Android tasks are tracked here and don't block Phase 1 critical-path work (open-core foundation, extension points, schema).
