# CCT-32 — XREAL Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute this plan task-by-task in the same session.

**Goal:** Ship the Beam Pro / XREAL Air 2 Pro Companion app to **XREAL Store + Google Play + GitHub Releases** as a release-grade v1.0. Full feature surface, lifecycle hardening, branding, signing, privacy policy, telemetry, store listings.

**Reference spec:** [docs/superpowers/specs/2026-05-09-cct-32-xreal-release-design.md](../specs/2026-05-09-cct-32-xreal-release-design.md) — read first.

**Working directory:** `companion-android/` (local-only git repo until CCT-30 splits to codetalker-pro). Daemon is at `192.168.1.86:17832`. Beam Pro paired via wireless adb (`adb devices` shows X4200).

**Test baseline:** 32 unit tests passing. Build clean. Theme fix landed. QR scan and LAN-aware QR fixed. Foreground service registered.

**Phase order:** A (features) → B (hardening) → C (branding) → D (release pipeline) → E (stores) → F (legal) → G (telemetry) → H (docs). Each phase commits and verifies on real hardware before next phase begins.

**File structure** (target after all phases):
```
companion-android/
├── app/src/main/
│   ├── AndroidManifest.xml                 # MODIFY: every release item
│   ├── kotlin/dev/opencircuit/codetalker/
│   │   ├── MainActivity.kt                  # MODIFY: route to Onboarding/SessionList/SessionDetail
│   │   ├── ui/
│   │   │   ├── PairingScreen.kt
│   │   │   ├── SessionListScreen.kt         # MODIFY: rows tappable
│   │   │   ├── SessionDetailScreen.kt       # NEW
│   │   │   ├── OnboardingScreen.kt          # NEW
│   │   │   ├── DiagnosticsScreen.kt         # NEW
│   │   │   ├── PreferencesScreen.kt         # NEW
│   │   │   ├── AboutScreen.kt               # NEW
│   │   │   ├── pickers/
│   │   │   │   ├── ModePicker.kt            # NEW
│   │   │   │   ├── VoicePicker.kt           # NEW
│   │   │   │   ├── CadencePicker.kt         # NEW
│   │   │   │   └── MutedToggle.kt           # NEW
│   │   │   ├── markup/
│   │   │   │   └── MarkupQuickPanel.kt      # NEW
│   │   │   └── character/
│   │   │       ├── CharacterChip.kt         # existing
│   │   │       ├── CharacterPickerSheet.kt  # NEW
│   │   │       └── CharacterAttachRow.kt    # NEW
│   │   ├── audio/
│   │   │   ├── TTSPlayer.kt
│   │   │   ├── STTRecorder.kt
│   │   │   └── AudioFocusManager.kt         # NEW
│   │   ├── service/
│   │   │   ├── CompanionForegroundService.kt
│   │   │   └── BootReceiver.kt              # NEW
│   │   ├── telemetry/                       # NEW
│   │   │   ├── CrashReporter.kt
│   │   │   └── ConsentFlow.kt
│   │   ├── legal/                           # NEW
│   │   │   ├── PrivacyPolicyScreen.kt
│   │   │   └── TermsScreen.kt
│   │   ├── net/DaemonClient.kt              # MODIFY: full session-cfg + voice + character
│   │   └── ar/{HudLayer,MenuLayer}.kt       # MODIFY: consume real session/character state
│   └── res/
│       ├── mipmap-anydpi-v26/{ic_launcher.xml, ic_launcher_round.xml}    # NEW: adaptive icon
│       ├── mipmap-{hdpi,mdpi,xhdpi,xxhdpi,xxxhdpi}/{ic_launcher.png}     # NEW: legacy fallbacks
│       ├── drawable/{ic_launcher_foreground.xml, ic_launcher_monochrome.xml}  # NEW
│       ├── values/{colors.xml, themes.xml, strings.xml}                  # MODIFY: add splash + branding
│       └── xml/{splashscreen.xml}                                         # NEW
├── docs/
│   ├── PRIVACY-POLICY.md                    # NEW
│   ├── TERMS.md                             # NEW
│   ├── USER-GUIDE.md                        # NEW
│   └── DEVELOPER-GUIDE.md                   # NEW
├── store-assets/                            # NEW: feature graphic, screenshots, description
│   ├── google-play/
│   ├── xreal-store/
│   └── github-releases/
├── scripts/
│   └── release.sh                           # NEW: tag → build → upload
├── CHANGELOG.md                             # NEW
├── RELEASE-NOTES.md                         # NEW
└── proguard-rules.pro                       # NEW
```

---

# Phase A — Feature completeness

## Task A.1: Extend DaemonClient with full session/voice/character endpoints (TDD)

**Files:**
- Modify: `app/src/main/kotlin/dev/opencircuit/codetalker/net/DaemonClient.kt`
- Modify: `app/src/test/kotlin/dev/opencircuit/codetalker/net/DaemonClientTest.kt`

- [ ] **Step 1: Write failing tests for new endpoints**

Add to `DaemonClientTest`:

```kotlin
@Test
fun `getSession returns full state with resolved cfg`() {
    val body = """
        {
          "state": {
            "session_id":"sid-1","cwd":"/tmp","attached_profile":null,
            "attached_character":"aria","live_overlay":{}
          },
          "resolved_cfg": {
            "active_mode":"direct",
            "voice":{"engine":"piper","model":"char-aria"},
            "live":{"cadence":"normal"},
            "enabled":true,
            "markup":{"code_fence":{"kind":"describe"}}
          }
        }
    """.trimIndent()
    server.enqueue(MockResponse().setBody(body))
    val s = client.getSession("sid-1")
    assertEquals("direct", s.activeMode)
    assertEquals("char-aria", s.voiceModel)
    assertEquals("normal", s.cadence)
    assertEquals(true, s.enabled)
    assertEquals("describe", s.markup["code_fence"]?.kind)
}

@Test
fun `putOverlay sends nested keypath PATCH`() {
    server.enqueue(MockResponse().setBody("""{"resolved_cfg":{}}"""))
    client.putOverlay("sid-1", mapOf("active_mode" to "brief"))
    val recorded = server.takeRequest()
    assertEquals("PUT", recorded.method)
    assertTrue(recorded.body.readUtf8().contains("\"active_mode\":\"brief\""))
}

@Test
fun `listVoices parses voice library`() {
    server.enqueue(MockResponse().setBody("""[{"engine":"piper","model":"en_US-amy-medium","display_name":"Amy"}]"""))
    val voices = client.listVoices()
    assertEquals("en_US-amy-medium", voices[0].model)
    assertEquals("Amy", voices[0].displayName)
}

@Test
fun `listCharacters returns full records`() {
    server.enqueue(MockResponse().setBody("""[{"id":"aria","display_name":"Aria","persona":"warm","voice_ref":"char-aria","mesh_path":null}]"""))
    val chars = client.listCharacters()
    assertEquals("aria", chars[0].id)
    assertEquals("warm", chars[0].persona)
}

@Test
fun `attachCharacter posts to attach endpoint`() {
    server.enqueue(MockResponse().setBody("""{"ok":true}"""))
    client.attachCharacter("sid-1", "aria")
    val r = server.takeRequest()
    assertTrue(r.path!!.endsWith("/attach-character"))
    assertTrue(r.body.readUtf8().contains("\"character_id\":\"aria\""))
}

@Test
fun `detachCharacter sends DELETE`() {
    server.enqueue(MockResponse().setBody(""))
    client.detachCharacter("sid-1")
    assertEquals("DELETE", server.takeRequest().method)
}
```

- [ ] **Step 2: Implement endpoints + data classes**

Add to `DaemonClient.kt`:

```kotlin
data class SessionState(
    val sessionId: String,
    val cwd: String,
    val attachedProfile: String?,
    val attachedCharacterId: String?,
    val activeMode: String,
    val voiceModel: String?,
    val cadence: String?,
    val enabled: Boolean,
    val markup: Map<String, MarkupTreatment>,
)

data class MarkupTreatment(val kind: String)
data class VoiceLite(val engine: String, val model: String, val displayName: String)
data class CharacterLite(
    val id: String,
    val displayName: String,
    val persona: String?,
    val voiceRef: String,
    val meshPath: String?,
)

// add methods:
fun getSession(sessionId: String): SessionState { ... }
fun putOverlay(sessionId: String, overlay: Map<String, Any>) { ... }
fun listVoices(): List<VoiceLite> { ... }
fun listCharacters(): List<CharacterLite> { ... }
fun attachCharacter(sessionId: String, characterId: String) { ... }
fun detachCharacter(sessionId: String) { ... }
```

The `putOverlay` body shape mirrors what the daemon's `PUT /api/sessions/{sid}/overlay` accepts: a nested JSON object that gets deep-merged onto the live overlay.

- [ ] **Step 3: Tests pass**

```bash
cd companion-android
./gradlew testDebugUnitTest --tests DaemonClientTest
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(net): full session/voice/character endpoints (CCT-32 Task A.1)"
```

---

## Task A.2: SessionDetailScreen — header + active toggle + back nav

**Files:**
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/ui/SessionDetailScreen.kt`
- Modify: `app/src/main/kotlin/dev/opencircuit/codetalker/MainActivity.kt`

- [ ] **Step 1: Implement scaffold (no tests — UI Compose)**

```kotlin
@Composable
fun SessionDetailScreen(
    sessionId: String,
    daemonClient: DaemonClient,
    onBack: () -> Unit,
) {
    var state by remember { mutableStateOf<SessionState?>(null) }
    var isActive by remember { mutableStateOf(false) }

    LaunchedEffect(sessionId) {
        state = withContext(Dispatchers.IO) { daemonClient.getSession(sessionId) }
    }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(...)  // back button + display name + persona chip
        // Make Active toggle
        // Body: pickers + markup + character (filled in subsequent tasks)
    }
}
```

- [ ] **Step 2: Wire MainActivity routing — list ↔ detail**

`MainActivity.CompanionRoot` adds a `selectedSessionId` state. When non-null, render `SessionDetailScreen`; back tap clears it.

- [ ] **Step 3: Make session list rows fully tappable**

`SessionListScreen.SessionRow` becomes a `Card { Modifier.clickable { onSelect(session.sessionId) } }` — entire card area is tappable, not just the button.

- [ ] **Step 4: Smoke verify**

```bash
./gradlew installDebug
adb shell am start -n dev.opencircuit.codetalker/.MainActivity
```

Tap a session → detail screen renders with header.

- [ ] **Step 5: Commit**

`feat(ui): SessionDetailScreen header + back nav (CCT-32 Task A.2)`

---

## Task A.3: ModePicker / VoicePicker / CadencePicker / MutedToggle

**Files:**
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/ui/pickers/{ModePicker,VoicePicker,CadencePicker,MutedToggle}.kt`
- Modify: `SessionDetailScreen.kt` to embed them

- [ ] **Step 1: Implement ModePicker (segmented row)**

```kotlin
@Composable
fun ModePicker(
    current: String?,
    onChange: (String) -> Unit,
) {
    val modes = listOf("brief", "direct", "live", "trigger")
    Row {
        modes.forEach { m ->
            FilterChip(
                selected = current == m,
                onClick = { onChange(m) },
                label = { Text(m) },
            )
        }
    }
}
```

- [ ] **Step 2: Implement VoicePicker (dropdown)**

Fetches `daemonClient.listVoices()` on first composition, renders ExposedDropdownMenu. Special-case `char-{id}` voice_refs: show as "Character voice (char-{id})" with persona color.

- [ ] **Step 3: Implement CadencePicker (segmented)**

slow / normal / fast.

- [ ] **Step 4: Implement MutedToggle (Switch)**

Inverts the polarity — daemon stores `enabled: bool`, UI shows "Muted: ON/OFF".

- [ ] **Step 5: Embed in SessionDetailScreen + wire to putOverlay**

```kotlin
ModePicker(current = state.activeMode) { newMode ->
    scope.launch(Dispatchers.IO) {
        daemonClient.putOverlay(sessionId, mapOf("active_mode" to newMode))
        state = daemonClient.getSession(sessionId)  // refresh
    }
}
```

- [ ] **Step 6: Verify on Beam Pro**

Tap mode chip → daemon's resolved_cfg updates → next narration uses new mode.

- [ ] **Step 7: Commit**

`feat(ui): mode/voice/cadence/muted pickers wired to overlay (CCT-32 Task A.3)`

---

## Task A.4: MarkupQuickPanel — 6 toggles in 3 categories (TDD)

**Files:**
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/ui/markup/MarkupQuickPanel.kt`
- Create: `app/src/test/kotlin/dev/opencircuit/codetalker/ui/markup/MarkupKindResolutionTest.kt`

- [ ] **Step 1: Markup kinds catalog (pure Kotlin)**

```kotlin
object MarkupQuickCatalog {
    data class Group(val title: String, val hint: String, val forms: List<String>)
    data class FormSpec(val name: String, val label: String, val allowedKinds: List<String>)

    val GROUPS = listOf(
        Group("Listen density", "Biggest verbosity dials.",
              forms = listOf("code_fence", "tool_output")),
        Group("Inline detail", "How aggressively short references get read.",
              forms = listOf("inline_code", "file_path")),
        Group("Structural pauses", "How multi-line structures get summarized.",
              forms = listOf("todo_update", "plan_block")),
    )

    val FORMS = mapOf(
        "code_fence" to FormSpec("code_fence", "Code blocks", listOf("skip", "describe", "read")),
        "tool_output" to FormSpec("tool_output", "Tool output", listOf("skip", "describe", "read")),
        "inline_code" to FormSpec("inline_code", "Inline `code`", listOf("skip", "identifier_only", "read")),
        "file_path" to FormSpec("file_path", "File paths", listOf("skip", "filename", "describe", "read")),
        "todo_update" to FormSpec("todo_update", "Todo updates", listOf("skip", "count_only", "itemize", "read")),
        "plan_block" to FormSpec("plan_block", "Plan blocks", listOf("skip", "summarize", "read")),
    )
}
```

- [ ] **Step 2: 3 unit tests for catalog completeness**

```kotlin
@Test fun `every form in groups has a spec`() { ... }
@Test fun `no group is empty`() { ... }
@Test fun `every spec's first allowed kind is the safe default`() { ... }
```

- [ ] **Step 3: MarkupQuickPanel composable**

```kotlin
@Composable
fun MarkupQuickPanel(
    current: Map<String, MarkupTreatment>,
    onChange: (formName: String, kind: String) -> Unit,
) {
    Column {
        MarkupQuickCatalog.GROUPS.forEach { group ->
            Text(group.title.uppercase(), style = MaterialTheme.typography.labelSmall)
            Text(group.hint, style = MaterialTheme.typography.bodySmall, color = textMuted)
            group.forms.forEach { formName ->
                val spec = MarkupQuickCatalog.FORMS[formName]!!
                val kind = current[formName]?.kind ?: spec.allowedKinds.first()
                Row {
                    Text(spec.label)
                    Spacer(Modifier.weight(1f))
                    DropdownMenu(...)  // pick from spec.allowedKinds
                }
            }
        }
    }
}
```

- [ ] **Step 4: Wire into SessionDetailScreen**

On change: `daemonClient.putOverlay(sid, mapOf("markup" to mapOf(formName to mapOf("kind" to kind))))`.

- [ ] **Step 5: Verify on Beam Pro**

Switch `code_fence` from describe → skip; speak Claude Code prompt with code in it; daemon respects the new kind.

- [ ] **Step 6: Commit**

`feat(ui): MarkupQuickPanel — 6 form / 3 category quick toggles (CCT-32 Task A.4)`

---

## Task A.5: CharacterPickerSheet (bottom sheet)

**Files:**
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/ui/character/CharacterPickerSheet.kt`
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/ui/character/CharacterAttachRow.kt`
- Modify: `SessionDetailScreen.kt`

- [ ] **Step 1: CharacterAttachRow — inline component for SessionDetailScreen**

Shows current character chip (if any), or "No character" placeholder. Tap → opens bottom sheet. "Detach" button when one is attached.

- [ ] **Step 2: CharacterPickerSheet — Compose ModalBottomSheet**

```kotlin
@Composable
fun CharacterPickerSheet(
    daemonClient: DaemonClient,
    onSelect: (CharacterLite) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState()
    var characters by remember { mutableStateOf<List<CharacterLite>>(emptyList()) }
    LaunchedEffect(Unit) {
        characters = withContext(Dispatchers.IO) { daemonClient.listCharacters() }
    }
    ModalBottomSheet(...) {
        LazyColumn {
            items(characters) { c ->
                Row(Modifier.clickable { onSelect(c); onDismiss() }) {
                    CharacterAvatar(c, size = 40.dp)
                    Column { Text(c.displayName); PersonaPill(c.persona) }
                }
            }
        }
    }
}
```

- [ ] **Step 3: Wire to attach/detach API**

```kotlin
onSelect = { char ->
    scope.launch(Dispatchers.IO) {
        daemonClient.attachCharacter(sessionId, char.id)
        state = daemonClient.getSession(sessionId)
    }
}
```

- [ ] **Step 4: Smoke verify**

Open SessionDetail → tap character section → bottom sheet shows characters → tap one → SessionDetail header updates with the new character.

- [ ] **Step 5: Commit**

`feat(ui): CharacterPickerSheet bottom-sheet attach (CCT-32 Task A.5)`

---

## Task A.6: SessionList → SessionDetail navigation polish

**Files:**
- Modify: `SessionListScreen.kt`
- Modify: `MainActivity.kt`

- [ ] **Step 1: Cards fully clickable**

Wrap each `Card` body in `Modifier.clickable`. Remove "Set active" button (moved to detail screen).

- [ ] **Step 2: Visual feedback on selected**

Tapped card: brief ripple + background tint until detail loads.

- [ ] **Step 3: Detail back action returns to list**

Use a single Compose state in MainActivity rather than NavHost (keeps deps minimal for v1.0).

- [ ] **Step 4: Smoke verify**

End-to-end: PairingScreen → SessionList → tap row → SessionDetail → back → SessionList preserved.

- [ ] **Step 5: Commit**

`feat(ui): clickable session cards + detail nav (CCT-32 Task A.6)`

---

## Task A.7: Audio auto-play + AudioFocusManager (TDD)

**Files:**
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/audio/AudioFocusManager.kt`
- Create: `app/src/test/kotlin/dev/opencircuit/codetalker/audio/AudioFocusManagerTest.kt`
- Modify: `SessionDetailScreen.kt` to instantiate TTSPlayer when active

- [ ] **Step 1: AudioFocusManager wraps Android AudioManager.requestAudioFocus**

Handles: AUDIOFOCUS_GAIN (resume play), LOSS_TRANSIENT (pause), LOSS (stop), GAIN_TRANSIENT_MAY_DUCK (lower volume).

- [ ] **Step 2: 4 unit tests for state transitions**

Mock AudioManager via mockk; assert state changes match input focus events.

- [ ] **Step 3: Wire TTSPlayer.playSession() → request focus on play, abandon on stop**

- [ ] **Step 4: Verify on Beam Pro**

Play TTS → call comes in → audio pauses → call ends → audio resumes.

- [ ] **Step 5: Commit**

`feat(audio): AudioFocusManager + TTS auto-play wiring (CCT-32 Task A.7)`

---

## Task A.8: STT round-trip — side-button → inject → buddy reply spoken

**Files:**
- Modify: `MainActivity.kt`
- Create: `app/src/main/kotlin/dev/opencircuit/codetalker/CompanionViewModel.kt`

- [ ] **Step 1: CompanionViewModel coordinates state**

Holds: activeSessionId, buddyId, ButtonRouter, STTRecorder, TTSPlayer. Listens to ButtonRouter state changes; when state goes to LISTENING, starts STT; when DispatchListening, sends to buddy.

```kotlin
class CompanionViewModel(
    private val daemonClient: DaemonClient,
    private val sttRecorder: STTRecorder,
    private val ttsPlayer: TTSPlayer,
) : ViewModel() {

    val activeSessionId = MutableStateFlow<String?>(null)
    val buddyId = MutableStateFlow<String?>(null)
    val captionText = MutableStateFlow("")

    fun handleButtonState(state: ButtonState) {
        when (state) {
            ButtonState.Listening -> sttRecorder.start()
            ButtonState.DispatchListening -> dispatchToBudy()
            else -> {}
        }
    }

    private fun dispatchToBudy() {
        val sid = activeSessionId.value ?: return
        viewModelScope.launch {
            val bid = buddyId.value ?: daemonClient.startBuddy(sid).also { buddyId.value = it }
            // collect final STT text from sttRecorder.events flow
            // POST /api/companion/inject {buddy_id: bid, text: finalText}
            // SSE subscribe → captionText updates
        }
    }
}
```

- [ ] **Step 2: Wire MainActivity to ViewModel**

ButtonRouter.state → ViewModel.handleButtonState(). Button events flow naturally from HardwareKeys → ButtonRouter → ViewModel.

- [ ] **Step 3: Caption rendering in HudLayer**

When captionText is non-empty, HudLayer renders a glass-panel caption box at the top.

- [ ] **Step 4: Verify on Beam Pro end-to-end**

Set active session → click side button → speak "what test failed?" → buddy starts → SSE events stream → buddy replies → audio plays through phone speakers.

- [ ] **Step 5: Commit**

`feat: STT side-button round-trip end-to-end (CCT-32 Task A.8)`

---

# Phase B — Production hardening

## Task B.1: Permission rationale screens

- [ ] Create `ui/permissions/PermissionRationaleScreen.kt` — shown before requesting CAMERA / RECORD_AUDIO / POST_NOTIFICATIONS
- [ ] If user denies → "Open Settings" button + manual permission grant flow
- [ ] Smoke verify: deny camera → see rationale → tap "Open Settings" → grant
- [ ] Commit `feat(permissions): rationale screens (CCT-32 Task B.1)`

## Task B.2: OnboardingScreen first-launch

- [ ] Create `ui/OnboardingScreen.kt` — 3 pages: welcome, daemon setup hint with copy-pasteable command, permission asks
- [ ] Persist "completed_onboarding" in DataStore — first launch only
- [ ] Smoke verify: clear app data → relaunch → see onboarding → complete → land on PairingScreen
- [ ] Commit `feat(ui): OnboardingScreen (CCT-32 Task B.2)`

## Task B.3: Error UX every failure mode

- [ ] Create `ui/errors/ErrorBanner.kt` — Snackbar-like component with Title + Description + Action
- [ ] Catalog every error: daemon unreachable, token expired, mic denied, camera denied, network down, audio focus lost permanently, invalid pairing payload, daemon API version mismatch
- [ ] Each error has user-actionable resolution: retry, open settings, reset pairing, reinstall app
- [ ] Verify on Beam Pro: kill daemon → app shows "Daemon unreachable" with "Retry" + "Open Tailscale settings"
- [ ] Commit `feat(ui): user-recoverable error banner for every failure (CCT-32 Task B.3)`

## Task B.4: BootReceiver opt-in auto-start

- [ ] Add `RECEIVE_BOOT_COMPLETED` permission + receiver registration
- [ ] PreferencesScreen toggle: "Start on device boot"
- [ ] Receiver only starts service if user opted in + has paired
- [ ] Smoke verify: enable toggle → reboot Beam Pro → app appears in foreground notification
- [ ] Commit `feat(service): BootReceiver opt-in (CCT-32 Task B.4)`

## Task B.5: Lifecycle hardening

- [ ] Pause/resume audio on screen-off via `Lifecycle.Event` observer
- [ ] Reconnect SSE on `ConnectivityManager.NetworkCallback` events
- [ ] Survive process death: persist activeSessionId in DataStore; restore on cold launch
- [ ] Verify on Beam Pro: lock screen mid-narration → audio pauses → unlock → resumes; switch WiFi networks → SSE reconnects within 5s
- [ ] Commit `feat: lifecycle + network-change resilience (CCT-32 Task B.5)`

## Task B.6: DiagnosticsScreen

- [ ] Create `ui/DiagnosticsScreen.kt` — single-pane status cards mirroring `xreal.hud.diagnostics` mockup
- [ ] Long-press anywhere → menu → "Diagnostics" entry
- [ ] Live values: pairing token expiry countdown, daemon last-success timestamp, audio buffer state, buddy session id, glasses connected (display ID enumeration), latency RTT, battery
- [ ] Commit `feat(ui): DiagnosticsScreen (CCT-32 Task B.6)`

---

# Phase C — Branding (5 tasks)

## Task C.1: App icon set

- [ ] Design: cyan-to-purple gradient orb with codetalker waveform glyph (matching dashboard logo). Adaptive: foreground glyph + background gradient + monochrome variant for themed icons (Android 13+)
- [ ] Generate via Android Studio Image Asset Studio: `ic_launcher.xml` (anydpi-v26), `ic_launcher_round.xml`, mipmap PNGs for legacy
- [ ] Re-add `android:icon`, `android:roundIcon` to manifest
- [ ] Verify on Beam Pro: launcher shows new icon
- [ ] Commit `feat(branding): app icon set (CCT-32 Task C.1)`

## Task C.2: Splash screen

- [ ] Use Android 12+ SplashScreen API; logo + brand color
- [ ] Add `android:windowSplashScreen*` theme attributes
- [ ] Smoke verify: cold launch → branded splash for ~500ms → app loads
- [ ] Commit `feat(branding): splash screen (CCT-32 Task C.2)`

## Task C.3: Store assets

- [ ] Feature graphic 1024×500 (Google Play hero)
- [ ] 5+ phone screenshots (1080×1920) — Pairing, SessionList with characters, SessionDetail full controls, MarkupQuickPanel, Diagnostics
- [ ] 5+ tablet screenshots if Beam Pro form factor counts as tablet
- [ ] High-res icon 512×512
- [ ] Save under `store-assets/google-play/` and `store-assets/xreal-store/`
- [ ] Commit `feat(store): screenshots + feature graphic (CCT-32 Task C.3)`

## Task C.4: Strings polish

- [ ] Audit every UI string in `strings.xml` — final copy
- [ ] Empty states, error messages, button labels — all rewritten for end-user clarity (not dev shorthand)
- [ ] Add `<plurals>` where needed
- [ ] Commit `chore(strings): final UI copy (CCT-32 Task C.4)`

## Task C.5: AboutScreen

- [ ] Create `ui/AboutScreen.kt` — version, license info, third-party libs, privacy policy link, ToS link, GitHub link
- [ ] Use `BuildConfig.VERSION_NAME` + `BuildConfig.VERSION_CODE`
- [ ] Commit `feat(ui): AboutScreen (CCT-32 Task C.5)`

---

# Phase D — Release pipeline (5 tasks)

## Task D.1: Release keystore

- [ ] Generate keystore: `keytool -genkey -v -keystore release.keystore -alias codetalker -keyalg RSA -keysize 2048 -validity 25000`
- [ ] Store passwords in `~/.gradle/gradle.properties` (gitignored)
- [ ] Document key rotation procedure in `docs/DEVELOPER-GUIDE.md`
- [ ] Commit `chore(release): keystore generation procedure documented (CCT-32 Task D.1)` (the actual keystore is NOT committed)

## Task D.2: Release build configuration

- [ ] `app/build.gradle.kts` — `signingConfigs.release { ... }` reading from `gradle.properties`
- [ ] `buildTypes.release { isMinifyEnabled = true; signingConfig = signingConfigs.release }`
- [ ] Verify: `./gradlew bundleRelease` produces signed AAB at `app/build/outputs/bundle/release/`
- [ ] Commit `build(release): signed AAB pipeline (CCT-32 Task D.2)`

## Task D.3: ProGuard rules

- [ ] `proguard-rules.pro` — keep rules for OkHttp, ExoPlayer, Compose runtime, ZXing internals, JsonObject usage
- [ ] Verify: `bundleRelease` succeeds; install AAB locally; functionality intact
- [ ] Commit `chore(proguard): keep rules for release build (CCT-32 Task D.3)`

## Task D.4: Versioning

- [ ] versionCode 1 / versionName "0.1.0" → first release
- [ ] Document semver bumping in `docs/DEVELOPER-GUIDE.md`
- [ ] Commit `chore(release): versioning conventions (CCT-32 Task D.4)`

## Task D.5: CHANGELOG + release script

- [ ] CHANGELOG.md — initial entry for v0.1.0
- [ ] `scripts/release.sh` — tag → bundleRelease → upload to GitHub Releases
- [ ] Smoke verify: dry-run the script
- [ ] Commit `chore(release): CHANGELOG + release.sh (CCT-32 Task D.5)`

---

# Phase E — Store listings (4 tasks)

## Task E.1: Google Play Console listing

- [ ] Create developer account + Play Console listing
- [ ] Short description (80 chars) + long description (4000 chars)
- [ ] Upload feature graphic + screenshots from store-assets/google-play
- [ ] Privacy policy URL — point at GitHub Pages or `docs.codetalker.dev` (Phase F)
- [ ] Data Safety form
- [ ] Content rating questionnaire
- [ ] Internal testing track first → closed alpha → production
- [ ] Commit `docs(store): Google Play listing data (CCT-32 Task E.1)`

## Task E.2: XREAL Store submission

- [ ] XREAL developer account application
- [ ] Submit per their listing data requirements
- [ ] Commit `docs(store): XREAL Store listing data (CCT-32 Task E.2)`

## Task E.3: GitHub Releases automation

- [ ] `.github/workflows/release.yml` — on tag push, build signed AAB + APK, attach to release
- [ ] Use GitHub Secrets for keystore + signing config
- [ ] Smoke verify: push a `v0.1.0-rc1` tag → Action runs → release created with assets
- [ ] Commit `ci(release): GitHub Actions release workflow (CCT-32 Task E.3)`

## Task E.4: Update channels

- [ ] Google Play / XREAL Store auto-update (Android handles)
- [ ] GitHub Releases path: in-app "Check for updates" link → opens releases page
- [ ] Commit `feat(updates): in-app update check (CCT-32 Task E.4)`

---

# Phase F — Privacy + legal (4 tasks)

## Task F.1: Privacy policy markdown

- [ ] Write `docs/PRIVACY-POLICY.md`
  - What data: pairing token, daemon URL, optional crash reports (Sentry, opt-in)
  - What NOT collected: voice input, voice output, transcripts, character names, session content
  - Storage: Android Keystore (token + URL); Sentry (crash reports if opted in)
  - Sharing: nothing shared; you control your daemon
  - Deletion: clear app data → all local data gone; daemon-side data is on user's PC
- [ ] Host: GitHub Pages serving `docs/legal/privacy-policy.html`
- [ ] Commit `docs(legal): privacy policy v1 (CCT-32 Task F.1)`

## Task F.2: Terms of Service

- [ ] Write `docs/TERMS.md` — usage terms, license, liability disclaimers
- [ ] Same hosting path
- [ ] Commit `docs(legal): terms of service v1 (CCT-32 Task F.2)`

## Task F.3: Manifest disclosures

- [ ] Add `<meta-data android:name="...rationale" />` for every dangerous permission
- [ ] Update `AndroidManifest.xml` with `android:usesPermissionFlags="neverForLocation"` for relevant permissions
- [ ] Verify: Google Play scanner accepts disclosures
- [ ] Commit `chore(manifest): permission disclosures (CCT-32 Task F.3)`

## Task F.4: Data Safety form

- [ ] Fill out Google Play Console Data Safety section: data types, sharing, use, collection, encryption in transit
- [ ] Document responses in `store-assets/google-play/data-safety-form.md` for reproducibility
- [ ] Commit `docs(store): Data Safety form responses (CCT-32 Task F.4)`

---

# Phase G — Telemetry (3 tasks)

## Task G.1: Sentry SDK integration (opt-in)

- [ ] Add `io.sentry:sentry-android` dependency
- [ ] Initialize in Application.onCreate ONLY when `prefs.crash_reporting_enabled == true`
- [ ] Use a Sentry project DSN you create + commit (the DSN is public-key-only, safe to check in)
- [ ] Commit `feat(telemetry): opt-in Sentry SDK (CCT-32 Task G.1)`

## Task G.2: First-launch consent dialog

- [ ] In OnboardingScreen step 4: "Help improve the app — send anonymous crash reports?" Default: declined
- [ ] Persist in DataStore; settable later in PreferencesScreen
- [ ] Commit `feat(telemetry): consent flow (CCT-32 Task G.2)`

## Task G.3: Privacy policy update

- [ ] Update PRIVACY-POLICY.md with crash reporting details: what's collected (stack traces, app version, device model), what's NOT (PII, audio, text, transcripts)
- [ ] Commit `docs(legal): privacy policy crash reporting addendum (CCT-32 Task G.3)`

---

# Phase H — Documentation (5 tasks)

## Task H.1: User Guide

- [ ] `docs/USER-GUIDE.md`
  - Getting started: install + pair
  - Day-to-day: pick session, set active, listen, speak
  - Glasses: connect + use
  - Troubleshooting: common issues
- [ ] Commit `docs(user): user guide v1 (CCT-32 Task H.1)`

## Task H.2: Developer Guide

- [ ] `docs/DEVELOPER-GUIDE.md`
  - Building from source
  - Running tests
  - Contributing
  - Architecture overview
- [ ] Commit `docs(dev): developer guide (CCT-32 Task H.2)`

## Task H.3: API Reference

- [ ] `docs/API.md` — typed endpoints with examples
- [ ] Commit `docs(dev): API reference (CCT-32 Task H.3)`

## Task H.4: Update mockups page with real screenshots

- [ ] Run `scripts/capture-screenshots.sh` (per Phase C.3) — captures Beam Pro displays at every key state
- [ ] Per-mockup edit in `docs/mockups/index.html`: replace mockup-source contents with `<img>` per Section 7 recipe
- [ ] Flip `data-status="mockup"` → `"screenshot"` on each
- [ ] Commit `docs(mockups): replace mockups with real screenshots (CCT-32 Task H.4)`

## Task H.5: XREAL Store + Google Play final copy

- [ ] Polish description, key-features bullets, screenshots' captions
- [ ] Commit `docs(store): final listing copy (CCT-32 Task H.5)`

---

# Final verification — release readiness checklist

After Phase H, verify:

1. ✅ `./gradlew testDebugUnitTest` — 32 + ~40 new tests, all green
2. ✅ `./gradlew bundleRelease` — signed AAB exists at `app/build/outputs/bundle/release/`
3. ✅ Beam Pro install → onboarding → pair → SessionDetail → mode change → audio plays → side-button STT → buddy reply → all clean
4. ✅ Foreground service notification works → tap "Disconnect" → audio stops cleanly
5. ✅ Lock screen mid-narration → audio pauses → unlock → resumes
6. ✅ Switch WiFi → SSE reconnects within 5s
7. ✅ Privacy policy + ToS render in-app and at hosted URL
8. ✅ App icon shows in launcher (adaptive + monochrome)
9. ✅ Sentry crash report fires (with crash reporting opted in) on intentional test crash
10. ✅ Sentry crash report does NOT fire (with opted out) on intentional test crash
11. ✅ Screenshots updated in `docs/mockups/index.html` — banner shows N screenshots, 0 mockups
12. ✅ CHANGELOG includes v0.1.0 entry
13. ✅ Release tag pushed; GitHub Actions builds signed AAB; release asset uploaded

Then submit:
- AAB to Google Play Console internal testing
- AAB / APK to XREAL Store
- AAB + APK on GitHub Releases

When all three accept, flip status to **shipped**.

---

## Notes for the implementer

- **TDD discipline**: every Phase A task has unit tests. Phase B-H tasks are mostly integration / config / docs — verify on real Beam Pro hardware. The `adb shell screencap` flow is documented + working.
- **Per-task commit**: every numbered task above ends with a `git commit`. Don't batch.
- **Subagent-driven**: dispatch one subagent per task with full context. Two-stage review (spec compliance, then code quality) per superpowers:subagent-driven-development.
- **Live device tests**: Beam Pro is paired (X4200 / Android 14, MSYS_NO_PATHCONV=1 for adb pull paths). Daemon at 192.168.1.86:17832 with CCT_DAEMON_HOST=0.0.0.0.
- **DRY**: extract reusable Composables aggressively. ModePicker / VoicePicker / CadencePicker share a SegmentedRow base — write that first, derive the three.
- **YAGNI**: skip Unity AR, skip cloud sync, skip multi-user collab — all v2.
- **Frequent commits**: every task ends with a commit. If a task gets long, split mid-task.

When all 40 tasks complete, the v1.0 release ships. Welcome to the XREAL Store.
