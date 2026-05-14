# Session Handoff — Direct-STT + Session-View Fixes

**Sessions:** 2026-05-12 evening + 2026-05-13 (post-reboot continuation)
**Branch:** `vNext` (public codetalker) at commit `0ed8b2e` (latest at handoff time)
**Phase 0 gate tag:** `vNext-P0-gate` at `2b1056f` (held since prior session)
**Phase 0.5 gate tag:** `vNext-P0.5-gate` at `4590be4` (held since prior session)
**Phase 1 work branch:** `vNext-phase-1` (created prior session, untouched here)
**Doctrine in effect:** `memory/feedback/session_communication_style.md` + siblings (ported 2026-05-11). Mid-session updates: 3-sentence shape. End-of-session: 5-section brief.

---

## Composite outcome

Two end-to-end product features verified on real hardware (XREAL Beam Pro at `192.168.1.132`) + three latent daemon bugs fixed:

1. **Vol-DOWN long-press Buddy STT** — full record→clone→speak loop working on phone
2. **Vol-UP long-press Direct-STT** — phone voice types into the active CC window via SendKeys + Enter (you're reading a message that landed via this path today)
3. **P0-B React 19 + custom-element prop bug** — `<model-viewer>` was getting `src`/`alt`/`exposure` as DOM properties instead of attributes, so PBR textures never loaded. Now fixed via `useEffect` + `setAttribute`.
4. **Session-view UX** — list returned 95+ entries unfiltered, "Live · 0" right after daemon restart, no auto-derived workspace_group. Now 14-row filtered list, broader live window, auto-derive heuristic.
5. **Audio routing discovered** — sessions need explicit `audio_outputs: ["phone"]` to narrate through phone; default is desktop-only.

---

## Per-task state

| ID | Item | State | Commit / Evidence |
|---|---|---|---|
| P0-A | Voice clone fix | ✅ Landed prior session | `10cd9b4` + `7f0caf1` |
| P0-B | Character textures — runbook + **real fix** | ✅ Both | runbook `fa108dd`; real fix `bf3537a` |
| P0-C | STT caption display | ✅ Done-by-incident | `BuddyChatPanel.kt` in in-flight Android renders captionText |
| P0-D | Phone mute banner | ❌ Still missing | In-flight Android adds many features but NOT this banner |
| P0-E | Test-suite repair | ✅ Landed prior session | `a5cc006` |
| P0-F | /ui markup links | ✅ Landed prior session | `26dce4c` |
| P0-mopup | Integration test + dead-code + skip extension | ✅ Landed prior session | merge `06cb85f` |
| P0.5 | 6-cluster test stabilization | ✅ Landed prior session | merge `4590be4`, tag `vNext-P0.5-gate` |
| Phase 1 plan | Open-core foundation plan | ✅ Written + branched | `3ce97d3` + branch `vNext-phase-1` |
| **Direct-STT daemon** | `/api/companion/direct-stt` + SendKeys helper | ✅ Landed this session | `0ed8b2e` |
| **Direct-STT Kotlin** | HardwareKeys vol-up long-press + plumbing | ✅ Implemented + APK installed on phone | **Uncommitted** in companion-android (intentional — belongs to user) |
| **Session-view bugs** | Visibility 24h + live window 300s + workspace_group auto-derive | ✅ Landed this session | `5b7853a` + `62cc400` |
| **Hardware verification** | Buddy STT + Direct-STT + audio routing | ✅ Verified live on Beam Pro | This handoff message itself was typed via Direct-STT pipeline once during testing |

---

## Proving slice

The single artifact that proves the work end-to-end: **commit `0ed8b2e`** plus the live observation that the user's test message *"This is a test resp"* arrived in this Claude Code session **as a typed user message** — meaning daemon `/api/companion/direct-stt` → Windows SendKeys typed the transcript into the focused CC window → Enter submitted → I received it as user input. The full chain works. View with:

```
git -C codetalker show 0ed8b2e
```

---

## What was done — full commit + edit inventory

### codetalker (public repo, vNext branch)

Two-day span of commits (most recent first):

```
0ed8b2e feat: /api/companion/direct-stt endpoint + Windows SendKeys helper
62cc400 fix: companion/api.py is_live includes catalog-recency match (mirrors webui)
5b7853a fix: session-view UX bugs — visibility filter (24h) + live window 300s + workspace_group auto-derive
bf3537a fix(P0-B): React 19 + custom-element prop forwarding for <model-viewer>
a868dd5 docs(phase-0.5): slow-fixture top-3 cluster data
3ce97d3 docs(phase-1): dispatch-ready Phase 1 plan — open-core foundation
66e23ea docs(phase-0): mop-up items closed + XTTS fixture refactor follow-up filed
06cb85f merge: Phase 0 mop-up (1a integration test + 1b dead-code + 1c skip extension) into vNext
77f316e chore(P0-E): skip MCP-SSE-dependent test in test_e2e_v2.py
69c9f51 chore(P0-A): remove unreachable stub-clone compat at api.py:1247-1249
6f0f249 test(P0-A): add integration test for clone-then-attach flow
10e8840 docs(phase-0): 7h-pytest results — 11 failures triaged
9efed63 docs(phase-0): file deferral notes for P0-C + P0-D
2b1056f merge: P0-F dead-end /ui/#markup link removal into vNext     <-- vNext-P0-gate
... (earlier P0-A through P0-F + their merges)
```

### companion-android (private codetalker-pro repo) — **UNCOMMITTED, intentional**

The whole point: this is the user's in-flight Android work + my direct-STT edits layered on top. Belongs to the user to commit at their discretion.

My contributions sit on top of the user's in-flight 1875L:

- **HardwareKeys.kt** — extracted `LongPressDetector` helper class; vol-DOWN keeps existing Buddy STT binding (LongPress/HoldEnd); vol-UP gained new LongPressUp/HoldEndUp emission for direct-STT; side button simplified to Click-only
- **ButtonRouter.kt** — added `ButtonInput.LongPressUp` + `HoldEndUp` sealed variants + their no-op handling in the `when` expression
- **CompanionButtonHandler.kt** — updated binding table doc + added `onRockerUpLongPress()` + `onRockerUpHoldEnd()` interface methods
- **MainActivity.kt** — routed new ButtonInput variants to handler; passed `directStt` lambda to CompanionViewModel constructor (calls `client.postDirectStt`)
- **SessionDetailScreen.kt** — implemented `onRockerUpLongPress` and `onRockerUpHoldEnd` to set `SttMode.DIRECT_CC` then trigger same recording flow as Buddy STT
- **CompanionViewModel.kt** — added `SttMode { BUDDY, DIRECT_CC }` enum + `directStt` constructor param (defaulted no-op for tests) + branched `dispatch()` on mode
- **DaemonClient.kt** — added `postDirectStt(sessionId, text)` POST helper

The APK with these edits is installed on the phone (build done 2026-05-12 18:40:27 + verified post-reboot).

---

## What it's about

The user is shipping a "Pro" tier of codetalker that includes a phone companion (in-flight Android code) for AR/wearable use with XREAL Beam Pro glasses. Two distinct STT routes exist now:

- **Vol-DOWN long-press = Buddy STT** — quick Q&A through an intermediate LLM (OpenRouter / Anthropic). Phone records → /api/companion/inject → Buddy LLM → response narrates back. Useful for asking questions of an AR-side AI while working.
- **Vol-UP long-press = Direct-STT** — wireless dictation mic for the user's active Claude Code session. Phone records → /api/companion/direct-stt → daemon types transcript into OS-foreground CC window via PowerShell SendKeys + Enter. Response narrates back through the regular hook → audio pipeline. This is the feature that got verified today.

The session-view fixes were uncovered while diagnosing audio gaps: phone showed only 1 of the user's 6 active CC sessions, daemon catalog had 95 historical entries, "Live" filter was a 60-second recency window. Now 14-row clean filtered view with auto-derived workspace groups.

The audio routing discovery (`audio_outputs: ["phone"]` required) was the LAST gap in the audio chain. Without it, the daemon synthesizes narration but only publishes to desktop — phone gets silence.

---

## What's left — open items for next agent

### High-value follow-ups

1. **P0-D mute banner on phone** (~120 LOC Kotlin in companion-android). The in-flight code adds workspace groups, character avatars, mode chips, per-session mute, BuddyChatPanel — but **no global mute banner**. Confirmed missing by direct UI dump: when daemon `enabled: false`, phone UI is byte-identical to enabled state. Per the original Phase 0 plan Task 4 (P0-D).

2. **STT trigger picker (3 options)** (~200 LOC, deferred). User asked for vol-down long-press + vol-up long-press + on-screen button + double-tap as user-selectable options, with vol-down long-press as default. Default is implemented; the picker UI in PreferencesScreen + the `SttTrigger` enum + branched logic in HardwareKeys is what's needed.

3. **Settings-save investigation** — user reported settings changes on SessionDetail not saving. Daemon API verified to persist correctly (`/api/persistent-sessions/{sid}` reads back the overlay). Either phone PUT isn't firing OR UI doesn't reflect post-save state. Next step: capture phone HTTP requests while user changes a setting.

4. **STT truncation tuning** — verified Direct-STT works ("This is a test resp" arrived) but transcript got cut mid-word. Probable cause: Android `SpeechRecognizer.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS` aggressive default, OR LongPressDetector's `onHoldEnd` fires before the recognizer's final-text event. Could add a 300ms grace window before dispatching transcript.

5. **P0-C UX gap** — caption text renders only on BuddyChatPanel (Chat tab), not on SessionDetail. User on SessionDetail hears audio cue + sees no visible confirmation of what was captured. Should mirror captionText to a row on SessionDetail.

6. **Companion-android commit** — 1875L+ of in-flight work + my direct-STT edits are sitting uncommitted. Per cross-repo doctrine, **this belongs to the user**, not the next agent. Flag this to the user before doing other Android-side work.

### Lower-priority follow-ups (filed in deferred-tasks)

7. **XTTS test-fixture extraction** (🟡 Important) — `core/tests/test_voices_clone_e2e.py` has duplicated XTTS config setup across two tests; refactor before a third consumer arrives.

8. **Phase 0.5 pre-existing failures triage** — full pytest run during prior session had 11 failures from session-base commit `ce8e4ca`. Phase 0.5 mop-up already addressed these via the 6-cluster sweep; a full re-run hasn't happened post-fix.

9. **Phase 1 dispatch** — `vNext-phase-1` branch exists at `4590be4` (= vNext-P0.5-gate). Phase 1 plan at `docs/superpowers/plans/2026-05-12-vNext-phase-1-implementation.md` is dispatch-ready. Next agent could execute Phase 1 (open-core foundation: extension points, schema, repo-split prep) using `superpowers:executing-plans` against that plan.

---

## What you need from the user

If you're picking up as the next agent, before doing anything Android-side:

1. **Has the user committed the in-flight companion-android work?** Check `git -C companion-android status`. If 28+ lines still uncommitted, that's still your blocker for Android-side commits — don't add to that wall.

2. **Which workstream first?**
   - Phase 1 (Python refactor, no Android dependency) — clean, well-planned, dispatch-ready
   - P0-D mute banner — high user value, Android-side, conflicts with in-flight code until they commit
   - STT picker — user-asked, large scope, needs settings UI design
   - Settings-save bug — small, debug-driven, requires phone interaction

3. **Hardware setup state on phone:**
   - Wireless ADB port is dynamic per session — find via `adb mdns services`. Re-toggle phone's Wireless Debugging if mDNS shows empty.
   - Phone APK is installed (last built 2026-05-12 18:40:27).
   - Pair token (current valid): `RkErszDyDszeh7tcq8K5W4btp3xxCeOghR4EFhNsCK0`
   - 4 sessions in companion_active_sessions: NACA-Roadmap, OCR-Web, OCR-Game, CTDev.
   - All 4 have `audio_outputs: ["phone"]` set.
   - Daemon was unmuted today (`enabled: true`) but the config file defaults to `enabled: false` on cold start — daemon restart re-mutes.

---

## What you need to know — gotchas, doctrine, learnings

### Doctrine ports that already exist (memory)

Read these BEFORE diving in:

- `~/.claude/projects/C--Users-brand-Dropbox-OCR-Open-Circuit-codetalker/memory/session_communication_style.md` — mid-update + end-brief shape
- `.../memory/subagent_dispatch_preflight.md` — verify target files exist before SDD dispatch; gitignored siblings (`companion-android`) cost dispatch cycles
- `.../memory/sonnet_1m_context_unavailable.md` — `model: sonnet` returns error on this account; default subagents to `haiku`
- `.../memory/audio_routing_phone_destination.md` — **NEW this session** — sessions need explicit `audio_outputs: ["phone"]` overlay to narrate through phone; default routes to desktop only
- `.../memory/MEMORY.md` — index

### Discovered today

1. **adb wireless discovery flow**: `adb mdns services` returns `_adb-tls-connect._tcp 192.168.1.132:PORT`. Port is DYNAMIC per Wireless-Debugging-toggle. Empty list means phone's Wireless Debugging screen isn't foreground (Android pauses the listener for security).

2. **IME conflict with adb tap**: tapping coordinates that overlap the on-screen keyboard area routes to keyboard keys, not the underlying button. ALWAYS hide IME with `input keyevent KEYCODE_BACK` before tapping buttons near the bottom of the screen.

3. **Daemon mode resolution surprise**: Sending a Notification hook event put OCR-Game into "brief" mode active even though configured "live" mode. Possibly the Notification handler hard-codes brief? Worth investigating if mode handling matters for next agent's work.

4. **Hooks fire-and-forget**: `claude-code-talker-hook` is registered as `async: true`. Hook subprocess failures are silent. If you suspect hooks aren't firing during normal CC use, manually invoke `claude-code-talker-hook` from PowerShell with a known payload to see if it can even reach the daemon.

5. **The two STT routes share the same recording mechanics** but differ ONLY in `dispatch()`'s branch: `SttMode.BUDDY` hits `/api/companion/inject`, `SttMode.DIRECT_CC` hits `/api/companion/direct-stt`. SttMode is set by which gesture handler fires.

### Watch out for

- **Daemon restart resets `companion_active_sessions`** — the in-memory subscription set is rebuilt from persistent storage but the phone's TTSPlayer needs to re-subscribe its active set. After daemon restart, user may need to re-toggle "Active" on phone for each session.
- **`enabled: false` in `tts_config.yaml`** — user's default config has the daemon muted at cold start. Always `curl -X POST /api/unmute` after daemon restart if you want to test audio.
- **Visibility filter (24h)** — list_sessions drops entries older than 24h. Useful for noise reduction; surprising if you're looking for a session you used yesterday and it's missing. Direct `/api/sessions/{sid}` lookup still works regardless.
- **Phone's local `activeSessionIds` state vs daemon's `companion_active_sessions`** — they sync via `setActiveSessions(set)` in MainActivity. If they drift (phone restart, daemon restart, re-pair), use phone UI to re-toggle.

---

## Cadence note — how to resume in the next session

Start the next session with these commands to confirm state hasn't drifted:

```powershell
# Confirm daemon healthy
curl -s http://127.0.0.1:17832/api/status

# Confirm vNext head is at handoff commit
cd C:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker
git log --oneline -5

# Confirm companion-android in-flight work status (should still be uncommitted unless user committed)
git -C companion-android status --short | wc -l   # likely 28+

# Confirm phone ADB
$adb = "$HOME\AppData\Local\Android\Sdk\platform-tools\adb.exe"
& $adb mdns services   # if empty, ask user to re-enable Wireless Debugging

# Read THIS handoff doc:
cat docs/superpowers/sessions/2026-05-13-handoff-direct-stt-and-session-view-fixes.md
```

Then ask the user which of the "What's left" items they want first.

---

**End of handoff.** Good luck to the next agent. The two big features that make codetalker meaningful for AR use (Buddy STT + Direct-STT) are working end-to-end on real hardware now. The path from here is mostly polish (P0-D banner, STT picker, settings-save) + the bigger Phase 1 architectural refactor for open-core split.
