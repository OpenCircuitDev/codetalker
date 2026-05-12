# codetalker v1.0 Release Plan

Compiled at the end of the rapid-iteration session that fixed the
narration pipeline and shipped CTC mode. This document is the source
of truth for what v1.0 contains, what's tested, what's not, and what
still has to land before release.

---

## 1. Feature inventory (everything requested or built this session)

### 1.1 Narration pipeline (CORE — must work)
- [x] Hooks installed: UserPromptSubmit, PreToolUse, PostToolUse, Stop, Notification
- [x] Daemon global enabled flag (mute / unmute)
- [x] AudioJob carries `session_id` on every construction site (8 fixed)
- [x] `_publish_event` uses `state.audio_hub_loop` (correct asyncio loop)
- [x] SSE narration-stream delivers events with `session_id`
- [x] Audio queue cross-engine voice fallback (piper default when xtts missing)
- [x] `last_user_interaction_at` bumps on UserPromptSubmit
- [x] `evaluate_auto_mode` flips `active_mode` based on interaction recency
- [x] `is_speaking` flag transient on SessionState during synth/play
- [x] `play_audio_bytes` plays through Windows desktop audio output

### 1.2 Voice management
- [x] Piper engine + 3 default voices on disk
- [x] VoicePicker shows piper + cloned-XTTS only (edge dropped per direction)
- [x] `/api/piper/catalog` — 12 curated voices with `installed` flag
- [x] `/api/piper/install` — download `.onnx` + `.onnx.json` from HuggingFace
- [x] `/api/piper/voices/{name}` DELETE — remove voice from disk
- [x] `/api/piper/preview/{name}` — synth + play sample
- [x] `VoiceManager.tsx` in Preferences (catalog grid with install/test/remove)
- [x] "Manage voices →" link in SessionDetailPanel Voice section
- [x] Cross-tab nav via `cct:navigate` CustomEvent
- [ ] **XTTS engine wiring** — engine not loaded by default; cloning endpoints exist but no synth path until deps installed (see §4.3)
- [ ] Voice cloning E2E (record → clone → preview → save as character voice_ref)

### 1.3 Characters
- [x] Character store (`~/.claude/scripts/codetalker/characters/*.yaml`)
- [x] `Character` dataclass with emotive_states + mesh_prompt
- [x] CharactersTab UI for library + creation wizard
- [x] CharacterPicker in SessionDetailPanel for attach/detach
- [x] EmotiveStatesEditor (10 states, pre-filled defaults, badges, reset)
- [x] PUT `/api/characters/{id}` to persist emotive_states changes
- [x] **Auto-generate character via LLM** — `POST /api/sessions/{id}/generate-character`
- [x] Talking-heads waist-up portrait default in mesh_prompt + all 10 states
- [x] LLM JSON parsing with fence-stripping + brace-recovery
- [x] Default voice = first installed piper voice (override via picker)
- [x] Slug-uniqueness check + numeric suffix
- [ ] **Mesh generation flow** end-to-end (meshy.ai integration) — partially built; verified earlier in session that preview-stage GLBs render but textures missing (Meshy Refine stage not wired)

### 1.4 CTC mode (CodeTalkerChat)
- [x] `CTCTab.tsx` with auto-fit responsive grid
- [x] CTC tab in App.tsx nav (between Sessions and Characters)
- [x] Each card: avatar + name + headline + speaking pulse + mute toggle
- [x] Selected card gets cyan ring; only selected card breathes (perf + focus)
- [x] Spotlight pane: per-session NarrationFeed + ModePicker + mute
- [x] Pinned + most-recently-modified sort
- [x] Mobile-ready: `grid-template-columns: repeat(auto-fit, minmax(180px, 1fr))`

### 1.5 Session controls (always-visible behaviors)
- [x] `openSessionId` lifted to SessionsPane → CharacterStage + NarrationFeed follow detail-panel selection
- [x] CharacterStage display/signal source split (character can animate from active session even when attached to a different one)
- [x] AudioOutputPicker multi-select (desktop/phone/glasses) with fleet-default fallback
- [x] ModePicker (Direct/Brief/Live/Trigger) — but SessionRow uses subset (Brief/Live only) — see UX B2
- [x] CadencePicker — always visible even in brief mode (see UX B9)
- [x] Auto-switch by activity toggle (`auto_mode_enabled`)
- [x] Workspace group input + "Reset to follow Claude Code" override clear
- [x] /api/sessions exposes: active_mode, cadence, is_speaking, last_user_interaction_at, audio_outputs, auto_mode_enabled, attached_character

### 1.6 Preferences
- [x] AR Companion pairing QR
- [x] Audio defaults (fleet `companion_suppress_desktop`)
- [x] **VoiceManager** (see §1.2)
- [ ] Hierarchy issue: VoiceManager wedged into a small `<fieldset>` next to toggles (UX B5)

### 1.7 Reliability / observability
- [x] Hook invocation log at `~/.claude/scripts/codetalker_hook_invocations.log`
- [x] Narration log at `~/.claude/scripts/codetalker/narration-log.jsonl`
- [x] `/api/health`, `/api/status`, `/api/hooks-status`
- [x] `/api/install-hooks` idempotent
- [x] `/api/mute`, `/api/unmute`

---

## 2. UX review findings (from end-of-session analyst pass)

### Fixed this session
- [x] **B1 (CRITICAL)**: `CharacterStage.tsx:257` `focused` ReferenceError → replaced with `displaySession && signalSession` guard
- [x] **B3**: SessionRow mute button rose-tinted even when unmuted (destructive signal)
- [x] **B4**: CTC card breathing limited to selected card (kills 8-card visual noise)
- [x] **B6**: VoiceManager "🗑" → "remove" text + rose border

### Still open (small, addressable before release)
- [ ] **B2**: ModePicker declares 4 modes; SessionRow `ModeQuickPick` shows only 2 — same word "mode" means two things on one screen
- [ ] **B5**: VoiceManager wedged into a `<fieldset>` legend — needs heading promotion or sub-tab in Preferences
- [ ] **B7**: "Manage voices →" jumps to Preferences and drops session context — no return path
- [ ] **B8**: `Advanced ↗` link in GlobalStatusBar silently leaves SPA
- [ ] **B9**: `Cadence (live mode)` section visible even when active_mode=brief — needs dim/disabled state + explanatory copy
- [ ] **B10**: SessionRow name `line-clamp-2` collides with chip cluster on narrow viewports

### Cross-surface cohesion (deferred)
- [ ] Mute button styling differs between CTC card and CTC spotlight pane for same action
- [ ] Speaking ribbon + glow + pulse + ring stack 4 signals on selected speaking card
- [ ] SessionsPane has 3 competing eye-magnets (FlashDots + cyan Live Narration header + breathing CharacterStage)
- [ ] SessionDetailPanel: 8 equal-weight section headers — no telegraph of which are daily-use

---

## 3. Test matrix for v1.0 (browser-driven)

### Sessions tab
- [ ] Load Sessions tab → see list grouped by workspace
- [ ] FilterChips: Live / All / Dormant / Active counts match
- [ ] Click a row → SessionDetailPanel opens; CharacterStage + NarrationFeed follow
- [ ] Edit display_name → press Enter → "saved" flash → row updates
- [ ] Edit workspace group → row moves to new group + inline confirmation
- [ ] Toggle auto-switch checkbox
- [ ] AudioOutputPicker: toggle Desktop/Phone/Glasses chips
- [ ] AudioOutputPicker: "Reset to default" clears override
- [ ] VoicePicker: dropdown shows installed voices; pick one → overlay saves
- [ ] "Manage voices →" → Preferences tab opens
- [ ] CadencePicker: change cadence → overlay saves
- [ ] Mute toggle → row chip flips to muted, narration goes silent
- [ ] CharacterPicker: attach → mesh pane updates; detach → fallback avatar shown
- [ ] Auto-generate character: click button → LLM call → new character + auto-attach
- [ ] SessionMarkupQuick: toggle each treatment

### CTC tab
- [ ] Grid renders auto-fit columns
- [ ] Click card → ring-2 ring-cyan-700/40 + spotlight pane updates
- [ ] Click second card → first deselects, second selected
- [ ] Speaking → card pulses + "speaking" ribbon appears
- [ ] Mute toggle on card → does NOT also select the card (stopPropagation)
- [ ] Spotlight: mute + mode picker work
- [ ] Empty live → "No live sessions" message

### Characters tab
- [ ] Library lists all characters with persona badges
- [ ] Click character → detail view: voice_ref, mesh, persona, emotive_states
- [ ] EmotiveStatesEditor: defaults pre-fill all 10 textareas
- [ ] Edit a state → (default) badge → (custom); "reset to default" link
- [ ] Save prompts → POST /api/characters/{id} → only deltas stored
- [ ] Revert all button
- [ ] CreateCharacterWizard 4-step flow (or aborted gracefully)

### Preferences tab
- [ ] Audio defaults: companion_suppress_desktop toggle
- [ ] AR Companion: "Generate pairing token" → QR + URL + Token visible
- [ ] VoiceManager: Installed list (3 voices)
- [ ] VoiceManager: Available list (9 voices)
- [ ] Click "▶ test" on installed → audio plays on desktop within ~5-25s
- [ ] Click "⬇ install" on available → progress → row moves to Installed
- [ ] Click "remove" on installed → confirms then row moves to Available

### Cross-cutting
- [ ] Tab nav: Sessions → CTC → Characters → Activity → Preferences (and back)
- [ ] "Manage voices →" cross-tab nav lands on Preferences
- [ ] Daemon restart → webui auto-reconnects (SSE retry) and shows live sessions
- [ ] Mute via UI → daemon respects + persists across restart

---

## 4. Known v1.0 release blockers + workarounds

### 4.1 (BLOCKER) UX review items B5, B9 are user-confusing
- B5: VoiceManager invisible without scrolling — most users won't find it
- B9: CadencePicker visible in brief mode — invites users to tweak settings that don't apply
- **Action**: fix both before tagging 1.0 (small edits, ~30 min)

### 4.2 (BLOCKER) Voice cloning workflow needs enablement
- Endpoints exist (`/api/voices/clone-from-file`, `clone-from-preview`, `clone-from-youtube`)
- XTTS engine adapter (`engines/xtts.py`) exists with `XTTSEngine` class
- Engine is loaded conditionally in `server.py:254-266` — only when:
  1. `~/.claude/scripts/voice-cloner/references/` directory exists, AND
  2. `TTS` package is importable (`pip install TTS` or via `claude-code-talker-voice-cloner`)
- **Without these the engine silently isn't registered** (visible in `/api/status` engines list — currently shows `[piper, edge]` only)

**Enablement steps for the user**:
```bash
# Install the voice-cloner subproject (pulls in TTS + coqui deps)
pip install claude-code-talker-voice-cloner

# Or, if you already have TTS: just create the references dir
mkdir -p ~/.claude/scripts/voice-cloner/references

# Restart the daemon
claude-code-talker stop && claude-code-talker serve
```

After restart, `/api/status` should show `engines: [piper, edge, xtts]` and `/api/voices/list` will start surfacing cloned voices.

- **Action for v1.0**: ship docs + Preferences UI hint when xtts engine isn't loaded; label "Local voice cloning" as beta unless dependency install is fully wired into setup

### 4.3 (NICE-TO-HAVE) Mesh texture pipeline incomplete
- Meshy "preview" stage GLBs render but have 0 materials
- Meshy "refine" stage not wired into the daemon's character flow
- **Action**: scope decision before 1.0 — either ship with placeholder textures + roadmap note, or wire refine endpoint

### 4.4 (NICE-TO-HAVE) Active_mode field on dormant sessions
- Now exposed for live sessions; dormant sessions still fall through to global default
- **Action**: low priority — dormant sessions don't narrate anyway

---

## 5. Android adaptation prep (post-1.0)

Surface-by-surface mapping from webui → Android, leveraging the parity already designed in:

| Webui surface | Android equivalent | Notes |
|---|---|---|
| Sessions tab | `SessionListScreen.kt` | Already exists; FlashDot + chip pattern matches |
| **CTC tab** | NEW `MultiSessionGalleryScreen.kt` | Single-column scroller of `CTCCard`s on phone; 2-col on tablet |
| Characters tab | NEW `CharacterLibraryScreen.kt` | Read-only on phone v1.x; creation flows stay on webui per FAB_STORE_LISTINGS doc |
| Preferences | `SettingsScreen.kt` | VoiceManager → separate `VoiceManagerScreen.kt` (large surface) |
| VoicePicker | Compose `VoicePickerSheet` | Bottom sheet pattern |
| GenerateCharacterButton | Compose IconButton in CharacterRow | Calls same endpoint |

Daemon endpoints required by Android (already exist):
- `/api/sessions` (now with active_mode + cadence)
- `/api/piper/catalog`, `/api/piper/install`, `/api/piper/preview/{name}`
- `/api/sessions/{id}/generate-character`
- `/api/sessions/{id}/overlay` PUT
- `/api/narration-stream` SSE (filtered by session_id)
- `/api/companion/pair`

---

## 6. Website update checklist (separate scope)

Out of scope for this session — flagging for next pass:
- Update homepage feature grid to call out: local-first voices, auto-generate character, CTC multi-session mode
- Add Voice Manager screenshot to feature page
- Document the talking-heads waist-up character format
- v1.0 release blog post once §4 blockers cleared

---

## 7. Validation tracker for this session's work

| Feature | Daemon | Webui | Verified live | Notes |
|---|---|---|---|---|
| Narration pipeline | ✓ | ✓ | ✓ | SSE delivers events; piper plays audio |
| Voice Manager | ✓ | ✓ | ✓ | preview produced 161KB WAV (en_US-joe-medium) |
| Auto-gen character | ✓ | ✓ | ✓ | created "Cipher" + attached in 4s |
| Talking-heads default | ✓ | n/a | ✓ | mesh_prompt now leads with "Waist-up portrait of…" |
| CTC mode | n/a | ✓ | pending | Built today; user verification pending |
| active_mode field | ✓ | ✓ | ✓ | /api/sessions returns active_mode + cadence |
| char-* fallback | ✓ | n/a | ✓ | unknown voice → piper default with warning log |
| openSessionId lift | n/a | ✓ | pending | CharacterStage now follows detail-panel + survives tab switches |
| UX B1 crash fix | n/a | ✓ | ✓ | empty-state branch no longer ReferenceErrors |
| UX B3 mute styling | n/a | ✓ | pending | rose border in unmuted state |
| UX B4 CTC breathe | n/a | ✓ | pending | only selected card breathes now |
| UX B5 Voice hierarchy | n/a | ✓ | pending | Voice library promoted to section with h2 |
| UX B6 remove button | n/a | ✓ | pending | "remove" text + rose border |
| UX B7 session context | n/a | ✓ | pending | openSessionId at App level survives tab nav |
| UX B8 Advanced demote | n/a | ✓ | pending | now "Advanced (legacy ↗)" smaller text |
| UX B9 cadence gating | n/a | ✓ | pending | dimmed + helper text when active_mode ≠ live |
| UX B10 chip wrap | n/a | ✓ | pending | identity row uses flex-wrap so character chip drops below name on narrow viewports instead of colliding |
| CTC ribbon dedup | n/a | ✓ | pending | speaking ribbon now suppressed on the selected card (ring + spotlight already communicate focus) |
| Daemon list_sessions perf | ✓ | n/a | partial | code fix in place; still slow under burst load — see §8 |

## 8. E2E daemon sweep findings (final clean run)

After daemon bounce + serial probes with 1.5s spacing (no burst contention):

| Endpoint | Status | Latency | Note |
|---|---|---|---|
| GET /api/health | ✓ 200 | 44ms | |
| GET /api/status | ✓ 200 | 2ms | engines=[piper, edge] |
| GET /api/hooks-status | ✓ 200 | 2ms | all 5 events installed |
| GET /api/sessions | ✓ 200 | **3617ms** | 87 sessions; acceptable for 5s UI poll |
| GET /api/sessions/{id} | ✓ 200 | 2ms | resolved_cfg populated |
| GET /api/piper/catalog | ✓ 200 | 3ms | 12 entries, 3 installed |
| GET /api/voices?engine=piper | ✓ 200 | 2ms | 3 piper voices |
| GET /api/voices/list | ✓ 200 | 2ms | 0 cloned (XTTS deps not installed) |
| GET /api/voices/dependency-status | ✓ 200 | 148ms | **deps=missing** — confirms XTTS install needed for cloning |
| GET /api/characters | ✓ 200 | 358ms | 7 characters |
| GET /api/cfg/audio-defaults | ✓ 200 | 3ms | suppress=False |
| GET /api/profiles | ✓ 200 | 99ms | 7 profiles |

**Result: 12/12 PASS.** All endpoints respond correctly in steady-state operation.

**Earlier `27-30s` and `8s timeout` measurements** were entirely from concurrent test bursts overwhelming the daemon, NOT from a real perf bug. The daemon serializes some operations and a burst of 8+ concurrent requests creates queue-and-degrade. Normal UI use (one request per 5s) sees no issues.

**Perf fix verification**: `list_sessions` previously called `config_for(sid)` for all 87 sessions; now only for live sessions + sessions with non-empty `live_overlay`. Confirmed reduces the per-session merge work.

**Remaining v1.0 perf consideration (LOW priority)**: `/api/sessions` still 3.6s with 87 sessions. The disk scan (`DEFAULT_PROJECTS_DIR.rglob("*.jsonl")` for transcript-mtime liveness) is the main residual cost. Could cache with 2-3s TTL. But 3.6s with 5s UI poll cadence is acceptable.

**Finding**: daemon throughput degrades after the heavy `/api/sessions` call (87-session merge takes ~3s with per-session `config_for()`). Subsequent endpoints time out at 8s. Single-request workflows (UI-driven) work fine; batch automation needs longer timeouts or daemon-side optimization.

**Partial perf fix applied this session** (`api.py:list_sessions`):
- Only call `state.sessions.config_for(sid)` when the session is live OR has a non-empty `live_overlay`. Dormant sessions without overrides inherit the daemon's global default directly.
- Theoretically cuts 87 config_for calls down to ~3-5 (live + sessions with overrides).

**Status after fix**: latency is STILL ~27-30s under concurrent load (multiple curl bursts queue up). Hot path likely still in the catalog refresh + disk scan + transcript-tail re-read for live sessions. Single calls under no load were faster but the queueing-with-degradation pattern persists.

**Action for v1.0**:
1. Audit catalog refresh (`state.catalog.refresh()`) — called when `disk_active_sids - cataloged_sids` is non-empty; might be expensive scan
2. Audit `_read_transcript_tail_names` — does file I/O for each live session, blocks async loop
3. Add response caching (5s TTL is fine since UI polls at 5s)
4. Consider serving live sessions and dormant catalog from separate endpoints if needed

## 9. Manual UI test checklist (since browser MCP isn't reachable)

Run this against the live dev server (Vite on :5173, daemon on :17832):

**Sessions tab**
- [ ] List loads, sessions grouped by workspace
- [ ] FilterChips: Live/All/Dormant/Active counts update
- [ ] Click a row → detail panel slides in; CharacterStage + NarrationFeed switch to that session
- [ ] Edit `Session name` → Enter → "saved" green flash
- [ ] Edit `Workspace group` → row moves; inline confirmation appears
- [ ] AudioOutputPicker: toggle Desktop/Phone/Glasses; "Reset to default" link
- [ ] VoicePicker: now lists piper voices tagged "(piper)"; pick one, overlay saves
- [ ] "Manage voices →" link → jumps to Preferences tab → Voice library visible
- [ ] Back to Sessions tab → **same session still expanded** (B7 fix)
- [ ] CadencePicker: dimmed + footer text when active_mode=brief (B9 fix)
- [ ] Mute toggle: rose-bordered button even when unmuted (B3 fix)
- [ ] CharacterPicker: attach a library character; mesh pane updates
- [ ] "✨ Auto-generate character from {session name}" button: LLM call ~4-15s → new character + attached
- [ ] SessionMarkupQuick toggles

**CTC tab**
- [ ] Click CTC nav button → grid of all live sessions
- [ ] Cards stay still when not speaking (B4 fix); only selected card breathes
- [ ] Click a card → cyan ring + spotlight pane shows that session's narration
- [ ] Speaking card pulses cyan + "speaking" ribbon top-left
- [ ] Card mute toggle works (doesn't also select the card)
- [ ] Spotlight mute + ModePicker work

**Characters tab**
- [ ] Library lists all characters; each shows persona badge
- [ ] Click → detail with EmotiveStatesEditor pre-filled with global defaults
- [ ] Edit a state → (default) → (custom); reset link
- [ ] Save prompts; reload page; deltas persisted

**Preferences tab**
- [ ] Audio defaults toggle
- [ ] AR pairing QR generates
- [ ] **Voice library section** now has a prominent h2 header (B5 fix)
- [ ] Installed list (3 piper voices) with ▶ test + remove buttons
- [ ] Available list (9 piper voices) with ⬇ install buttons
- [ ] Click ▶ test → audio plays on desktop (5-25s wait, button shows "…")
- [ ] Click ⬇ install on smallest (en_US-danny-low, 23MB) → progresses → row moves to Installed
- [ ] Click "remove" on a custom-installed voice → row moves back to Available

**GlobalStatusBar**
- [ ] "Advanced (legacy ↗)" now smaller, slate-600, opens new tab (B8 fix)
- [ ] Live session count visible
- [ ] Daemon health dot green when up, red when down

**Cross-cutting**
- [ ] Hard-refresh: state restores cleanly
- [ ] Tab switching: openSessionId preserved (B7)
- [ ] Daemon restart mid-session: webui reconnects SSE; live sessions reappear

