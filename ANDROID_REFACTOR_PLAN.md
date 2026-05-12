# codetalker Android refactor plan — parity with webui v1.0

After the rapid webui buildout this session, the Android app needs to catch
up on 3 new feature surfaces + 2 small refinements. Most of the heavy
lifting (data classes, DaemonClient endpoints, session detail surface) is
already current — Android was further along than expected.

## 1. Inventory: what's already in parity ✅

The companion-android app already implements:

- All session API endpoints (sessions list, detail, overlay PUT, attach-character)
- SessionLite model with every v0.1.0 field: `active_mode`, `cadence`, `is_speaking`, `last_user_interaction_at`, `audio_outputs`, `auto_mode_enabled`, `attached_character`
- SessionState model that correctly unwraps daemon's `{state, resolved_cfg}` response
- SessionListScreen with workspace grouping, filter pills (Live/All/Dormant/Active), speaking pulse, mute toggle, mode quick-pick, auto-switch ribbon
- SessionDetailScreen with the full control stack: name & workspace, ModePicker (4-mode), auto-switch toggle, **DestinationPicker (3-chip multi-select — not the stale 4-way exclusive picker the original plan flagged)**, VoicePicker, CadencePicker, MutedToggle (rose-bordered), CharacterAttachRow, MarkupQuickPanel
- CharacterPickerSheet, CharacterAttachRow, CharacterChip
- BuddyChatPanel (single-session chat surface)

The `outputDestination` compile blocker mentioned in earlier handoffs is **resolved** — `audio_outputs` is the active field everywhere.

## 2. Gaps: what needs to land

### A. Daemon client extensions (foundation for B and C)

Add to `DaemonClient.kt`:

```kotlin
// Piper voice manager (4 endpoints)
suspend fun getPiperCatalog(): List<PiperCatalogEntry>
suspend fun installPiperVoice(name: String)
suspend fun uninstallPiperVoice(name: String)
suspend fun previewPiperVoice(name: String): ByteArray   // returns WAV bytes

// Auto-generate character preview mode (1 endpoint)
suspend fun generateCharacterDraft(sessionId: String): CharacterDraft  // POSTs with ?preview=true
```

New data classes:
- `PiperCatalogEntry` — name, lang, speaker, gender, quality, size_mb, installed
- `CharacterDraft` — id, display_name, voice_ref, persona, mesh_prompt, emotive_states (Map<String,String>)

### B. VoiceLibraryScreen (~ 1-2 hr)

New top-level screen reached from main nav (drawer or tab).

Layout: title → two LazyColumn lists side-by-side on tablet / stacked on phone:
- **Installed (N)** — `▶ test` button (synthesizes + plays through Android AudioTrack), `remove` button (rose-tinted text)
- **Available (N)** — `⬇ install` button (downloads with progress indicator)

Per-row chip showing voice metadata: language, gender, quality, MB.

State management via `VoiceLibraryViewModel` with `StateFlow<UiState>` containing: catalog list, busy map (row → action), errs map (row → message).

### C. AutoGenerateCharacterDialog (~ 1 hr)

Modal `AlertDialog` triggered from a new "✨ Auto-generate from session name" button in SessionDetailScreen's Character section.

Flow:
1. Click → `POST /api/sessions/{id}/generate-character?preview=true` (returns draft, doesn't save)
2. Dialog opens with editable fields:
   - Identity row: display_name input, ID (auto-derived, editable), persona dropdown, voice picker
   - Mesh prompt textarea
   - 10 emotive_states textareas (idle, listening, …, alerted)
3. Three buttons: **Cancel**, **↻ Regenerate** (re-calls preview endpoint, replaces all fields with confirmation), **Save & Attach** (POSTs `/api/characters`, then attach)

Reuses existing `CharacterPickerSheet` patterns where possible.

### D. CTCGalleryScreen — CodeTalkerChat mode (~ 2-3 hr)

New screen reached from main nav.

Layout: LazyVerticalGrid of session cards on phone (auto-fit 2-3 cols on tablet/landscape).

Each card:
- Character avatar (or initials fallback)
- Speaking pulse animation when `is_speaking == true`
- Session display_name + headline
- Mute toggle (top-right, stopPropagation so doesn't also select)
- Click selects → spotlight pane (bottom or side) with NarrationFeed + ModePicker + mute for the selected session

Spotlight pane is conditional render below the grid on phone (sticky-ish), beside it on landscape tablet.

This is **the Android mode** mentioned in the spec — quick-glance multi-session monitoring + tap to focus.

### E. "Active" filter refinement (~ 15 min)

`SessionListScreen` "Active" pill currently uses `isCompanionActive || sessionId == activeSessionId`. Update to match webui semantics:

```kotlin
fun isActiveNow(s: SessionLite): Boolean {
    if (s.isSpeaking) return true
    val last = s.lastUserInteractionAt ?: 0L
    if (last == 0L) return false
    val ageSec = (System.currentTimeMillis() / 1000) - last
    return ageSec in -2..29  // within 30s, allow 2s clock skew
}
```

Update the filter chip definitions to drive count + filter from this predicate.

### F. NarrationFeedPanel integration (~ 30 min)

File exists but isn't wired. Two places to use it:
- Inside `SessionDetailScreen` between sections (or in a sub-tab)
- Inside `CTCGalleryScreen` spotlight pane (when selected)

Backed by an SSE subscription to `/api/narration-stream` filtered by session_id (mirror webui's `useNarrationStream`).

## 3. Phase order + dependencies

```
Phase A: DaemonClient + data classes        ─┬─→ Phase B: VoiceLibraryScreen
                                              │
                                              ├─→ Phase C: AutoGenerateCharacterDialog
                                              │
Phase E: "Active" filter refinement (parallel; no deps)
                                              │
                                              └─→ Phase F: NarrationFeedPanel
                                                  │
                                                  └─→ Phase D: CTCGalleryScreen
```

Phase D depends on F because the spotlight pane uses the panel.

## 4. Verification per phase

After each phase:
1. `./gradlew :app:assembleDebug` — must succeed
2. Install on device or emulator: `./gradlew :app:installDebug`
3. Manual smoke: launch app, navigate to new screen, exercise primary action

Final phase (after D): full app walk-through covering:
- Pair / unpair
- Sessions list filter cycles through all 4 pills with sensible counts
- Open session detail → all controls work (mute, mode, destination, voice, cadence, character)
- Auto-generate character → dialog opens, fields populate, save creates + attaches
- Voice Library → install a small voice (en_US-danny-low 23MB) → preview plays through Android speaker → remove cleans up
- CTC Gallery → see all live sessions; speaking session pulses; tap to spotlight

## 5. What's NOT in this refactor

- Pro/Free gating UI changes (separate concern)
- AR companion presentation modes — keep as-is
- Push-to-talk / STT inject — keep as-is
- Glasses-specific UI — keep as-is

## 6. Estimated effort

| Phase | Hours |
|---|---|
| A. DaemonClient + data classes | 1 |
| B. VoiceLibraryScreen | 1-2 |
| C. AutoGenerateCharacterDialog | 1 |
| D. CTCGalleryScreen | 2-3 |
| E. "Active" filter | 0.25 |
| F. NarrationFeedPanel wiring | 0.5 |
| **Total** | **6-8 hours** |

Add ~30% for verification + edge cases.
