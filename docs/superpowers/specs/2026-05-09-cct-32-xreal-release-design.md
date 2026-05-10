# CCT-32 — XREAL AR Companion Release Design

**Status:** brainstormed and locked 2026-05-09. Targets release-grade v1.0 to XREAL Store + Google Play + GitHub Releases.
**Goal:** Take the working scaffold (Beam Pro paired, sessions visible, character chips rendered) and ship it as a production Android app distributed through three channels, with everything a real release requires: full feature surface, lifecycle hardening, branding, signing, privacy policy, telemetry, store listings, and a path to the Unity AR overlay (v1.1).
**Reference:** parent CCT-31 spec [2026-05-09-cct-31-xreal-android-companion-design.md](./2026-05-09-cct-31-xreal-android-companion-design.md). Open-core fit per [2026-05-09-cct-30-open-core-strategy.md](./2026-05-09-cct-30-open-core-strategy.md).

## Decisions locked in

1. **v1.0 architecture: Kotlin + Jetpack Compose, DisplayPort-mirror to glasses.** XREAL SDK 3.1.0 is Unity-only; native Kotlin AR is not on offer. The Beam Pro mirrors its Android screen to the XREAL One Pro glasses by default — our Compose UI renders cleanly through that path. Spatial AR (head-pinned HUD, world-anchored menus) is deferred to v1.1.
2. **v1.1 architecture: Unity overlay via XREAL SDK 3.1.0.** Separate Unity sub-project that reuses the v1.0 daemon endpoints and pairing token. Compose stays as the configuration surface; Unity replaces the rendering layer when AR mode is detected.
3. **Distribution: triple channel.** XREAL Store (primary), Google Play (broad reach), GitHub Releases (sideload-friendly for power users).
4. **Edition: paid Android, OSS daemon** (per CCT-30). The companion-android directory becomes the seed for the future codetalker-pro private repo.
5. **Pricing: deferred to release.** Spec will accommodate either one-time-purchase or subscription. License verification mechanism designed to be flippable.

## Audience and use case

**Primary user**: a Claude Code dev wearing XREAL Air 2 Pro glasses with a Beam Pro handheld. They want hands-free voice control of their Claude Code sessions while away from the keyboard, with audio narration of agent actions through the glasses' speakers.

**Secondary user**: a Claude Code dev with a regular Android phone (not Beam Pro). They want voice-driven session control as a standalone app — glasses optional. The phone-only mode renders the same Compose UI without DisplayPort-mirror and without spatial AR.

**Tertiary user**: an OSS contributor or curious dev who finds the GitHub Releases APK. Sideload, manual configuration, full feature parity with paid distribution.

## Hard product requirements (verbatim from earlier rounds + new)

- Single click on Beam Pro side button → STT mode → text injected into active session
- Double click → menu overlay
- Volume up/down rocker → switch active session in menu
- VNC-like view → see PC screen mirrored
- Phone speakers play codetalker TTS narration
- Phone mic captures voice for STT
- **NEW**: Per-session preferences UI (mute, mode, voice, cadence, markup quick toggles)
- **NEW**: Character attach UI (browse, attach, detach)
- **NEW**: Diagnostics screen (daemon reachability, pairing token expiry, audio stream state, buddy state)
- **NEW**: Foreground service notification with quick controls (pause audio, disconnect)
- **NEW**: First-launch onboarding flow (permission rationale, daemon setup hints)
- **NEW**: Error recovery UI for every failure mode (daemon unreachable, token expired, mic denied, glasses unplugged, etc.)
- **NEW**: Branded app icon, splash, adaptive launcher
- **NEW**: Privacy policy + ToS accessible in-app

## System architecture (v1.0)

```
                                              ┌──────────────────────┐
                                              │ XREAL Air 2 Pro      │ DisplayPort mirror
                                              │   (passive display)  │ ←─────────────────┐
                                              └──────────────────────┘                   │
┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│ Beam Pro / Android phone (Android 12+, API 31+)                                      │ │
│                                                                                      │─┘
│  ┌────────────────────────────────────────────────────────────────────────────────┐  │
│  │ codetalker-companion (CCT-32 v1.0)                                             │  │
│  │                                                                                │  │
│  │  ui/                                                                           │  │
│  │   ├── PairingScreen          Choose / QR / Manual                              │  │
│  │   ├── SessionListScreen      List with character chips                         │  │
│  │   ├── SessionDetailScreen    Full per-session controls (NEW)                   │  │
│  │   │     ├── ModePicker / VoicePicker / CadencePicker (NEW)                     │  │
│  │   │     ├── MutedToggle (NEW)                                                  │  │
│  │   │     ├── MarkupQuickPanel (6 toggles, 3 categories) (NEW)                   │  │
│  │   │     └── CharacterAttachSheet (NEW)                                         │  │
│  │   ├── DiagnosticsScreen      Daemon health, token expiry, audio state (NEW)   │  │
│  │   ├── OnboardingScreen       Permission rationale + daemon setup hints (NEW)  │  │
│  │   ├── PreferencesScreen      App-level prefs: telemetry, theme (NEW)          │  │
│  │   └── AboutScreen            Version, privacy policy, ToS, licenses (NEW)     │  │
│  │                                                                                │  │
│  │  ar/ (renders through DisplayPort mirror to glasses)                           │  │
│  │   ├── HudLayer               Active char + state                               │  │
│  │   ├── MenuLayer              Session switcher (rocker-driven)                  │  │
│  │   └── MirrorLayer            (deferred to v1.0.1) MJPEG screen mirror          │  │
│  │                                                                                │  │
│  │  audio/                                                                        │  │
│  │   ├── TTSPlayer              ExoPlayer with X-CCT-Pairing-Token                │  │
│  │   ├── STTRecorder            AndroidSpeechRecognizer wrapper                   │  │
│  │   └── AudioFocusManager      (NEW) handles BT routing, audio focus loss        │  │
│  │                                                                                │  │
│  │  input/                                                                        │  │
│  │   ├── ButtonRouter           State machine: idle / listening / menu            │  │
│  │   └── HardwareKeys           dispatchKeyEvent → ButtonInput translator         │  │
│  │                                                                                │  │
│  │  net/                                                                          │  │
│  │   ├── DaemonClient           REST + SSE wrapper, all endpoints typed           │  │
│  │   ├── PairingFlow            Keystore-backed token + URL persist               │  │
│  │   └── ConnectionGuard        Patient-cadence retry policy                      │  │
│  │                                                                                │  │
│  │  service/                                                                      │  │
│  │   ├── CompanionForegroundService  mediaPlayback type, audio + SSE alive        │  │
│  │   └── BootReceiver           (NEW) auto-start service if user opted in         │  │
│  │                                                                                │  │
│  │  qr/                                                                           │  │
│  │   ├── QrDecoder              ZXing pure-Kotlin decoder                         │  │
│  │   └── QrScannerScreen        CameraX preview + permission flow                 │  │
│  │                                                                                │  │
│  │  screen/                                                                       │  │
│  │   └── MjpegStream            Pure-Kotlin parser (used by v1.0.1+)              │  │
│  │                                                                                │  │
│  │  telemetry/ (NEW)                                                              │  │
│  │   ├── CrashReporter          opt-in Sentry; defaults off                       │  │
│  │   └── AnalyticsToggle        Settings UI for telemetry consent                 │  │
│  │                                                                                │  │
│  │  legal/ (NEW)                                                                  │  │
│  │   ├── PrivacyPolicyScreen    In-app rendering of policy markdown               │  │
│  │   └── TermsScreen            In-app rendering of ToS markdown                  │  │
│  │                                                                                │  │
│  │  ui/theme/                                                                     │  │
│  │   └── CodetalkerTheme        Phase 27 surface palette                          │  │
│  └────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                                ↕ WiFi / Tailscale (LAN by default)
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ codetalker daemon (PC) — OSS, unchanged from CCT-31                                  │
│   /api/companion/* + /api/sessions/* + /api/voices + /api/characters                 │
│   CCT_DAEMON_HOST=0.0.0.0 enables LAN binding (already shipped in d0ca564)           │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## Phase breakdown — 8 phases, ~40 tasks

### Phase A — Feature completeness (8 tasks)

The functional gaps revealed by the live Beam Pro session: SessionListScreen has no detail drill-down, no per-session preferences, no character browse, no audio playback, no STT round-trip.

| Task | Output |
|---|---|
| A.1 | Extend `DaemonClient` with full session-cfg + voice + character endpoints (`GET /api/sessions/{id}`, `PUT /overlay`, `GET /api/voices`, `GET /api/characters`, `POST /attach-character`, `DELETE /character`) |
| A.2 | `ui/SessionDetailScreen.kt` — header (avatar + name + persona + back), Make Active toggle, Diagnostics link |
| A.3 | `ui/pickers/{ModePicker, VoicePicker, CadencePicker, MutedToggle}.kt` — 4 reusable Composables |
| A.4 | `ui/MarkupQuickPanel.kt` — 6 form rows in 3 categories matching CCT-29; writes to overlay |
| A.5 | `ui/character/CharacterPickerSheet.kt` — bottom sheet listing characters, tap to attach |
| A.6 | Wire SessionListScreen rows fully tappable → SessionDetailScreen |
| A.7 | TTSPlayer auto-starts when active session set; AudioFocusManager handles BT/loss |
| A.8 | STT round-trip: side-button → ButtonRouter LISTENING → STTRecorder → POST /inject → SSE captions in HUD |

### Phase B — Production hardening (6 tasks)

| Task | Output |
|---|---|
| B.1 | Permission rationale screens for CAMERA + RECORD_AUDIO + POST_NOTIFICATIONS + lifecycle for partial grants |
| B.2 | `OnboardingScreen.kt` — first-launch flow with permission asks + daemon setup hints |
| B.3 | Error UX: every IOException + auth fail + permission deny gets a user-recoverable message + retry/fix action (e.g., "Daemon unreachable — Open Tailscale" / "Camera denied — Open Settings") |
| B.4 | `service/BootReceiver` — opt-in: foreground service auto-starts on device boot if user has paired + opted in |
| B.5 | Lifecycle hardening: pause/resume audio on screen-off; reconnect SSE on network-change events; survive process death |
| B.6 | `ui/DiagnosticsScreen.kt` — long-press anywhere → diagnostics: daemon reachability, token expiry, audio buffer health, buddy session, glasses connected, latency, battery |

### Phase C — Branding (5 tasks)

| Task | Output |
|---|---|
| C.1 | App icon design — adaptive (foreground + background), monochrome variant; ic_launcher in `mipmap-{anydpi-v26,hdpi,mdpi,xhdpi,xxhdpi,xxxhdpi}` |
| C.2 | Splash screen — uses Android 12+ SplashScreen API; logo + brand color |
| C.3 | Store assets — feature graphic 1024×500, screenshots (phone 1080×1920, tablet 1200×1920), high-res icon 512×512 |
| C.4 | Strings polish — final copy for every UI string (label, error message, empty state); i18n-ready scaffolding |
| C.5 | About screen with version, license info, third-party libs (ZXing/ExoPlayer/etc.) |

### Phase D — Release pipeline (5 tasks)

| Task | Output |
|---|---|
| D.1 | Generate release keystore + document key rotation procedure |
| D.2 | `app/build.gradle.kts` — release build type with R8 minification + ProGuard rules; `bundleRelease` produces signed AAB |
| D.3 | ProGuard rules for OkHttp + ExoPlayer + Compose + Compose-tooling exclusion + ZXing |
| D.4 | Versioning: `versionCode` (monotonic int) + `versionName` (semver). Initial 1 / "0.1.0" |
| D.5 | CHANGELOG.md, RELEASE-NOTES.md template, automated build script (`scripts/release.sh`) |

### Phase E — Store listings (4 tasks)

| Task | Output |
|---|---|
| E.1 | Google Play Console listing — short + long description, screenshots, content rating, privacy policy URL, target audience, data safety section |
| E.2 | XREAL Store submission — XREAL developer account application, listing data per their requirements |
| E.3 | GitHub Releases automation — script to tag release, build signed AAB + APK, upload to Releases page with notes |
| E.4 | Update channels — Google Play + XREAL Store auto-update; GitHub Releases manual; in-app "Check for updates" link |

### Phase F — Privacy and legal (4 tasks)

| Task | Output |
|---|---|
| F.1 | Privacy policy markdown — what data the app collects, how it's used, data retention, deletion procedure. Hosted at a stable URL (e.g., `docs/legal/privacy-policy.md` rendered as page) |
| F.2 | Terms of Service markdown — usage terms, license, liability disclaimers |
| F.3 | Manifest disclosures — every dangerous permission with `usesPermissionsRationale` |
| F.4 | Data Safety form (Google Play) — declare every data type, sharing, use |

### Phase G — Telemetry (3 tasks)

| Task | Output |
|---|---|
| G.1 | Sentry SDK integration — opt-in flag in PreferencesScreen, defaults off |
| G.2 | First-launch consent dialog — asks user opt-in/decline, persists |
| G.3 | What's collected: crash stack traces only, no PII, no audio/text content. Documented in privacy policy. |

### Phase H — Documentation (5 tasks)

| Task | Output |
|---|---|
| H.1 | User Guide — pairing, day-to-day use, troubleshooting, FAQ |
| H.2 | Developer Guide — building from source, contributing |
| H.3 | API Reference — DaemonClient typed endpoints, integration examples |
| H.4 | Update mockups page (`docs/mockups/index.html`) — replace mockups with real screenshots, mark `data-status="screenshot"` |
| H.5 | XREAL Store listing copy + screenshots prepared in Phase C, finalized here |

## v1.1 — Unity AR overlay (deferred, sketched)

When ready to add spatial AR, the Unity sub-project lives at `companion-unity/` parallel to `companion-android/`. Imports XREAL SDK 3.1.0 (Unity .tar.gz from XREAL developer portal). Scene hierarchy:

```
ARRoot (Unity scene)
├── HUDChip (head-pinned via XREAL anchor)
├── MenuPanel (world-pinned, billboarded, 50cm out)
├── ScreenMirror (world-pinned plane, MJPEG decoded)
└── DaemonClient (C# port; reuses HTTP endpoints + pairing token)
```

The Kotlin app and Unity overlay communicate via:
- Unity intent + AAR bridge: Kotlin app spawns Unity Activity when glasses connected
- OR: Unity is the standalone app; Kotlin app delegates AR mode to it

Decision deferred to v1.1 spec.

## Open follow-up decisions (don't block v1.0 spec)

- **Pricing model** — one-time vs subscription. v1.0 ships with license-verification stub; flippable to either path
- **License verification** — online check at boot vs offline grace period vs honor system
- **Crash reporter choice** — Sentry vs Bugsnag vs custom upload-to-daemon
- **App name on store** — "Codetalker AR" / "Codetalker Companion" / "codetalker for XREAL"

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| XREAL Store review delays | Submit early in Phase E; have GitHub Releases ready as primary distribution |
| Google Play rejects audio-foreground-service use | Manifest correctly types it as mediaPlayback; documented disclosure in Data Safety |
| Beam Pro firmware updates break HardwareKeys | Hardware-keys logging on first install captures actual keycode emitted; auto-tunes via remote config (CCT-32a follow-up) |
| Tailscale not installed → users hit "daemon unreachable" | Onboarding screen detects + offers Tailscale install link |
| User loses pairing token | Generate new from dashboard; old auto-expires after TTL |
| Daemon API changes break older app versions | Server returns API version in `/api/sessions`; app warns if version mismatch |
| Battery drain from continuous SSE | Patient retry policy (already shipped); foreground service has Disconnect action; Android 14 power-management auto-doses |
| Privacy policy hosting requirements | Host on `docs.codetalker.dev` or repo's GitHub Pages — both work as Google Play accepts a stable URL |

## Test strategy — full E2E harness integrated per task

Every feature task ends with a **failing test → impl → passing test → commit** cycle PLUS an E2E test that exercises the feature against either a MockWebServer or real device. **No task is "done" without its E2E.**

**Four test layers**:

1. **Unit (JVM, fast)** — pure-logic state machines, parsers, decoders, retry policy. ~70 tests target.
2. **Instrumented UI (`androidTest/`)** — Compose UI tests with `createComposeRule()`. Each new screen / picker / sheet has at least one test that renders, simulates interaction, and asserts state change OR HTTP request via MockWebServer.
3. **E2E smoke (`scripts/e2e/`)** — adb-driven shell scripts that exercise the real Beam Pro against the live daemon. Each captures screencaps for visual regression.
4. **On-device manual** — pre-release acceptance run; the 13-item release-readiness checklist at the end of the plan.

**E2E harness file structure**:
```
scripts/e2e/
├── README.md                   # how to run, prerequisites
├── lib/
│   ├── adb_helpers.sh          # connect, screencap, pm clear, send keyevent
│   ├── daemon_helpers.sh       # curl wrappers for fixture state
│   └── assert_helpers.sh       # check screen contains text, tap matching
├── e2e_pairing.sh
├── e2e_session_detail.sh
├── e2e_mode_change.sh / voice_change / cadence_change
├── e2e_markup_quick.sh
├── e2e_character_attach.sh
├── e2e_audio_play.sh
├── e2e_stt_roundtrip.sh
├── e2e_lifecycle.sh            # screen-off / network-change / process-death
├── e2e_permissions.sh          # camera deny → rationale → recover
├── e2e_full_flow.sh            # composes everything
└── run_all.sh                  # CI-style runner; non-zero exit on any fail
```

**Pre-tag gate**: `run_all.sh` must pass on fresh `pm clear` before any release tag.

## Acceptance criteria for v1.0

A user with Beam Pro + XREAL Air 2 Pro can:
1. Install from XREAL Store / Google Play / GitHub Releases
2. Open the app and complete onboarding (permissions + pairing)
3. See their codetalker session list with character chips
4. Tap a session → see full controls (mute, mode, voice, cadence, markup, character)
5. Set a session as active → daemon's TTS plays through phone/glasses speakers
6. Click side button → speak → text injected into buddy → buddy response speaks back
7. Double-click side button → menu → rocker scrolls → click confirms session switch
8. Close the app → audio keeps playing (foreground service notification)
9. Tap the notification → return to detail screen, no state lost
10. Open About → see version, privacy policy, ToS, third-party licenses
11. Tap "Disconnect" in notification → audio stops, foreground service stops cleanly

All eleven happen smoothly; no crashes, no token exposure in logs, no surprise behaviors.
