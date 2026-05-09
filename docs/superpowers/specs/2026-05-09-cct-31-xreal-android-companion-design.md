# CCT-31 — XREAL Android AR Companion App

**Status:** brainstormed 2026-05-09. Locked decisions captured below; full implementation plan to follow.
**Goal:** Android app for XREAL Air 2 Pro + Beam Pro that turns codetalker into a heads-up, hands-free control surface — voice-driven sessions, screen mirroring, audio narration, all without touching the keyboard.
**Reference:** parent roadmap [2026-05-08-cct-v1-design.md](./2026-05-08-cct-v1-design.md). Open-core fit deferred to [2026-05-09-cct-30-open-core-strategy.md](./2026-05-09-cct-30-open-core-strategy.md) (see "Edition fit" below).

## Context

After Phase 27 the React dashboard is the canonical desk-bound control surface for codetalker. Useful when you're at the keyboard. Useless when you're stretching your legs, eating, walking, or wearing AR glasses to keep windows out of your line of sight while audio narrates. The XREAL Air 2 Pro + Beam Pro pair is increasingly common with dev users — they're already wearing glasses for media. Adding a "control codetalker from the glasses" mode unlocks a hands-free workflow Claude Code itself can't reach today.

Three things make this feasible right now: (1) codetalker daemon already exposes REST + SSE on `0.0.0.0:17832`, (2) Claude Agent SDK lets us spawn a parallel buddy Claude without coupling to Claude Code's input pipeline, (3) Beam Pro is a real Android device with side buttons and a touchpad, no extra controller needed.

## Locked decisions

1. **Voice→Claude path:** Claude Agent SDK companion session (option 3 from brainstorm). Phone-injected text routes to a parallel Claude Agent SDK conversation managed by the codetalker daemon, **not** the user's main Claude Code window. The companion can read the main session's transcript for context but its responses are its own.
2. **Network:** LAN-only design for v1. Daemon binds to `0.0.0.0:17832` (already does); phone hits the LAN IP directly. Tailscale is a documented community recipe — install Tailscale on phone + PC, daemon listens on the Tailnet IP transparently, works from anywhere. No "Tailscale mode" in code; it's just a network the daemon happens to be reachable on. **Cloud relay (option C) is on the roadmap as a future paid-edition offering** (see "Future direction: managed relay" below).
3. **Hardware target:** XREAL Air 2 Pro glasses + XREAL Beam Pro Android handheld as the compute + controller device. Beam Pro's side buttons (power click, volume rocker) drive the control flow. Optional pairing with a 3DoF Bluetooth controller as a v2 add-on.

## Hard requirements (verbatim from user)

- **Single click on Beam Pro side button** → STT (speech-to-text) mode → text response to active session
- **Double click** → menu overlay
- **Volume up/down rocker** → switch active session in menu
- **VNC-like view** → see the live PC screen (Claude Code window or full desktop)
- **Phone speakers** play codetalker's TTS narration
- **Phone mic** captures voice for STT responses

## System architecture

```
┌─────────────────────────────┐
│   XREAL Air 2 Pro glasses   │  ← display + IMU
│   (3DoF / 6DoF via Beam)    │
└──────────┬──────────────────┘
           │ DisplayPort over USB-C
┌──────────┴──────────────────┐
│   XREAL Beam Pro (Android)  │
│   ├── codetalker-companion  │  ← this project
│   ├── XREAL Nebula SDK      │  ← AR overlay rendering
│   ├── Android SpeechRec     │  ← on-device STT
│   └── ExoPlayer             │  ← Opus audio playback
└──────────┬──────────────────┘
           │ WiFi (LAN or Tailscale)
┌──────────┴──────────────────┐
│   Codetalker daemon (PC)    │
│   ├── existing REST/SSE      │
│   ├── /api/companion/*  NEW │  ← inject, list-sessions, etc.
│   ├── /api/audio-stream NEW │  ← Opus-encoded TTS out
│   ├── /api/screen-frames NEW│  ← screenshot stream
│   └── BuddyClaude session   │  ← Agent SDK process
│       └── reads user's transcript for context
└──────────┬──────────────────┘
           │ existing hooks
┌──────────┴──────────────────┐
│   Claude Code (PC)          │  ← user's "real" session
└─────────────────────────────┘
```

## Daemon-side new endpoints (CCT-31a)

Five new surfaces. All under the existing `0.0.0.0:17832` host so Tailscale works transparently.

### `POST /api/companion/start-buddy`
Spawn a Claude Agent SDK process bound to a specific user session (so it can read the user's transcript). Body: `{user_session_id: string, model?: string, system_prompt?: string}`. Returns: `{buddy_id: string, status: "starting"|"ready"}`.

### `POST /api/companion/inject`
Send a user message to the buddy session. Body: `{buddy_id: string, text: string}`. Returns: `{message_id: string}`. Buddy's response streams back via the next endpoint.

### `GET /api/companion/stream/{buddy_id}` (SSE)
Stream events from the buddy: `partial_text`, `final_text`, `tool_use`, `done`. Phone subscribes when STT input is sent and disconnects after `done`.

### `GET /api/audio-stream/{session_id}` (long-poll WebSocket or SSE)
Opus-encoded TTS frames as codetalker speaks. Multiplexed per session — phone subscribes to whichever session is currently "active." Stream emits frames in real time so phone speaker latency is sub-200ms.

### `GET /api/screen-frames/{kind}` (MJPEG or WebRTC)
Screen capture stream. `kind = "claude-window"` (just Claude Code window via Windows enumeration) or `kind = "fullscreen"`. Frame rate adaptive (5 fps idle, 15 fps when content changes). MJPEG for v1 simplicity; WebRTC for v2 latency.

### `POST /api/companion/active-session`
Phone tells daemon "I'm now listening to session X" so audio-stream and inject route correctly. Body: `{session_id: string}`.

## Phone-side app structure (CCT-31b)

```
codetalker-companion/                        # NEW Android Studio project
├── app/src/main/
│   ├── kotlin/dev/opencircuit/codetalker/
│   │   ├── MainActivity.kt              # Hosts XREAL display
│   │   ├── ar/
│   │   │   ├── AROverlay.kt             # Nebula SDK overlay rendering
│   │   │   ├── SessionMenu.kt           # Floating menu UI
│   │   │   ├── HUD.kt                   # Always-visible session badge + status
│   │   │   └── ScreenMirror.kt          # MJPEG frame display
│   │   ├── audio/
│   │   │   ├── TTSPlayer.kt             # Opus stream → speaker
│   │   │   └── STTRecorder.kt           # Mic → Android SpeechRecognizer
│   │   ├── input/
│   │   │   ├── ButtonRouter.kt          # Click / double-click / rocker state machine
│   │   │   └── HardwareKeys.kt          # Beam Pro side button capture
│   │   ├── net/
│   │   │   ├── DaemonClient.kt          # REST + SSE/WebSocket to codetalker
│   │   │   ├── PairingFlow.kt           # QR code from dashboard → daemon URL
│   │   │   └── ConnectionGuard.kt       # Reconnect, network-change handling
│   │   └── viewmodel/
│   │       └── CompanionViewModel.kt    # State machine: idle/listening/menu/mirror
│   └── AndroidManifest.xml
├── build.gradle.kts
└── README.md                            # Pairing + Tailscale setup
```

## Controller / button state machine

```
                       ┌─────────────┐
                       │   IDLE      │ ← always-visible HUD: active session
                       │ (passive)   │   chip + audio-playing indicator
                       └──┬───┬──────┘
                  click │   │ double-click
                  ┌─────┘   └────────┐
                  ▼                  ▼
          ┌─────────────┐    ┌──────────────┐
          │  LISTENING  │    │   MENU       │
          │  (mic on)   │    │  (sessions)  │
          │  recording  │    │  rocker ↑↓   │
          └──┬─────┬────┘    └──┬───────────┘
   click/    │     │ silence    │ click on selection
   send      │     │ 1.5s       │
             ▼     ▼             ▼
          send to buddy       set active session
          → /api/companion    → /api/companion/
            /inject              active-session
             │                   │
             ▼                   ▼
            buddy responds      back to IDLE
            via SSE; audio
            streams back
            via TTSPlayer
```

**Hold-to-talk vs click-to-toggle**: v1 ships click-to-toggle (click starts, click stops, or 1.5s silence auto-stops). Hold-to-talk is a later refinement for users who prefer push-to-talk discipline.

**Back gesture**: long-press the side button → exit any mode back to IDLE. Acts as universal escape.

## AR overlay design (XREAL Nebula SDK)

Three layered surfaces, all rendered by Nebula in the user's spatial frame:

1. **HUD layer** (always visible, bottom-center, ~6° below gaze): active session chip + green/rose mute indicator + small mic icon (lit when listening). Sized to be glanceable but not intrusive. Pinned to head, not world.

2. **Menu layer** (appears on double-click, fades in 200ms, world-pinned at arm's length): vertical session list, current selection highlighted cyan. Up to 8 visible at once with scroll. Shows session display_name + cwd + project_slug. Persists until user clicks-to-select or long-presses to exit.

3. **Mirror layer** (appears when user toggles "show screen" via menu, world-pinned, larger): MJPEG-decoded screenshot of the Claude Code window or full desktop. Auto-aspect-ratio. Toggle on/off via menu item. Fades on inactivity.

Color palette reuses Phase 27 surface tokens (`--color-surface-1`, `--color-accent-live`) so the AR overlay feels coherent with the dashboard.

## Audio path

**Codetalker → phone speaker (TTS out):**
1. Daemon's existing `/api/narration-stream` SSE already emits text events with timing markers.
2. New: daemon's TTS pipeline (Piper) writes Opus-encoded audio frames to `/api/audio-stream/{session_id}` in addition to the local sound card.
3. Phone subscribes to that endpoint on startup and on `active-session` change.
4. Phone uses `ExoPlayer` to decode + play with adaptive jitter buffer (target 150ms).
5. Phone respects user's mute toggle (set via `PUT /api/sessions/{sid}/overlay { enabled: false }`).

**Phone mic → buddy Claude (STT in):**
1. User clicks side button → `STTRecorder.start()`.
2. Android `SpeechRecognizer` (offline mode if available, else online) streams partial transcripts.
3. User clicks again or 1.5s silence → recording stops.
4. Final text → `POST /api/companion/inject` with `{buddy_id, text}`.
5. Phone subscribes to `/api/companion/stream/{buddy_id}` if not already.
6. Buddy's `partial_text` events render as captions in HUD; `final_text` triggers TTS playback (which streams back via the audio path above).

**Why Android SpeechRecognizer first, Whisper later**: Android's API is free, fast, low-battery, and on-device on Pixel 7+. Whisper.cpp on Beam Pro is a v2 option for users who want offline-everywhere. Don't bundle a 1GB model in v1.

## Screen mirror

**v1: MJPEG over HTTP.** PC daemon adds a `windows-graphics-capture` based screenshotter (via `pywin32` + `dxcam`) running at 5 fps idle, ramps to 15 fps during active scrolling. Each frame is JPEG-encoded at quality 70, ~150 KB per frame. Sent to phone as `multipart/x-mixed-replace`. Phone decodes with `ImageDecoder` and renders to `ImageView` inside the AR mirror layer.

Latency: ~250ms end-to-end (capture → encode → wire → decode → display). Acceptable for "glance at terminal output," not for precision pointing.

**v2: WebRTC.** Sub-100ms latency, hardware-accelerated. Significant Android-side complexity. Defer.

**Capture target**: defaults to Claude Code window (`pywin32`'s window-enumerate finds windows by class/title). Falls back to full desktop if window not found. User toggles via menu.

## Pairing flow

First-launch UX:
1. App opens, asks "Where's your codetalker daemon?" — three options: scan QR code from dashboard, enter manually, or auto-discover via mDNS.
2. Dashboard gets a new "Pair AR Companion" button in Preferences that generates a QR encoding `{daemon_url, pairing_token}`.
3. App stores `daemon_url` + `pairing_token` in Android Keystore.
4. All requests include the token as a `X-CCT-Pairing-Token` header.
5. Daemon validates the token (configurable expiry; default 30 days).

This avoids exposing the daemon to unauthenticated phones on the same WiFi while not requiring a full auth system.

## BuddyClaude session model

The buddy is a Claude Agent SDK process the daemon spawns when phone first connects:

```python
# core/claude_code_talker/companion/buddy.py (sketch)
class BuddyClaude:
    def __init__(self, user_session_id: str, anthropic_api_key: str):
        self.transcript_path = SessionCatalog.path_for(user_session_id)
        self.system_prompt = (
            "You are an AR voice companion. The user is wearing AR glasses "
            "controlling another Claude Code session at <transcript_path>. "
            "Read the latest transcript before answering. Keep responses short "
            "and conversational; they will be spoken aloud."
        )
        self.client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)
        self.history: list[dict] = []

    async def inject(self, text: str) -> AsyncIterator[BuddyEvent]:
        # Read fresh transcript context
        ctx = read_recent_transcript(self.transcript_path, max_messages=20)
        self.history.append({"role": "user", "content": text})
        async with self.client.messages.stream(
            model="claude-sonnet-4-5",
            system=self.system_prompt,
            messages=[{"role": "system", "content": ctx}, *self.history],
        ) as stream:
            async for evt in stream:
                yield BuddyEvent.from_anthropic(evt)
        # save to history, return final
```

Buddy's tools: read-only access to user's session via transcript reads. **No write access** (buddy can describe, summarize, advise — not commit code or run shell). v2 might add a "shared scratchpad" mechanism so buddy and main session can collaborate.

Buddy can be stopped via `POST /api/companion/stop-buddy`. Multiple buddies one-per-session is supported but typical use is 1.

## Phase breakdown (10 phases)

| | Phase | Scope | Tests |
|---|---|---|---|
| **1** | Daemon: companion REST + buddy SDK process | `/api/companion/*`, `BuddyClaude` class, history persistence | `test_companion_api.py`, `test_buddy_session.py` |
| **2** | Daemon: audio stream endpoint | Opus-encoded TTS frames over SSE/WebSocket | `test_audio_stream.py` |
| **3** | Daemon: screen frame endpoint | dxcam + JPEG MJPEG stream | `test_screen_frames.py` |
| **4** | Daemon: pairing flow | QR token issue + validation, dashboard "Pair AR Companion" button | `test_pairing.py` + manual UI |
| **5** | Android: project skeleton + LAN client | Kotlin project, `DaemonClient`, pairing screen | unit tests for client |
| **6** | Android: button + STT input | `ButtonRouter` state machine, `STTRecorder`, click → inject flow | UI tests |
| **7** | Android: TTS playback | `TTSPlayer` ExoPlayer, audio stream subscribe | playback unit tests |
| **8** | Android: AR HUD + menu | Nebula SDK integration, HUD + menu rendering, rocker → session switch | manual on-device |
| **9** | Android: screen mirror | MJPEG decode + AR mirror layer | manual on-device |
| **10** | Polish: reconnection, network changes, battery, Tailscale recipe | resilience pass + docs | end-to-end manual tests |

Phases 1–4 are daemon-side and ship to OSS first (or pro — see "Edition fit"). Phases 5–10 are the Android app, a separate Android Studio project. Phases 1–4 can land before any Android work begins, so the daemon side is testable via curl alone.

## Edition fit (open-core split, per CCT-30)

Open question to settle before implementation: does the AR companion belong in OSS or paid?

**Argument for OSS:**
- No character-system dependency. Stays clean of Phase 25a/b/c.
- Helps grow the OSS user base (cool feature → buzz → adoption).
- Matches the "control surface" pattern, which OSS already covers (dashboard, hooks, slash commands).

**Argument for paid:**
- High engineering effort + ongoing hardware-specific maintenance (XREAL SDK updates, Android version churn).
- Hardware-specific features tend to be premium in dev tools (e.g., GitLab Premium, Sentry's mobile crash analytics).
- Pairs naturally with the character system — characters become "AR avatars" in v2.

**My lean: OSS daemon-side (Phases 1–4), paid Android app (Phases 5–10).** Reasoning: the daemon endpoints are general-purpose (anyone can build a phone client). The Android app is the productized polish. This gives OSS users a way to build their own clients while monetizing the official one.

Confirm before kickoff.

## Open questions (non-blocking)

These don't gate starting the spec→plan→implementation flow but need answers along the way:

1. **STT engine v1 default**: Android `SpeechRecognizer` (online, free) vs Whisper.cpp on-device (offline, ~1GB model). My lean: Android first, Whisper as a settings toggle in v2.
2. **Buddy's read access scope**: just the user's session transcript, or also project files? File access opens up more useful queries ("what's in `auth.py`?") but expands the security surface.
3. **Buddy's write access**: locked to read-only in v1. v2 could add "shared scratchpad" or "leave a comment for main session."
4. **Active session detection**: how does the phone know which session is "active"? Heuristics (most recent transcript activity?) or explicit user choice via menu? My lean: explicit choice; "follow most recent" as a toggle.
5. **Audio mute on AR**: when user is in a meeting, phone speakers shouldn't blare. Detect AR mode + auto-route audio to glasses' built-in speakers (XREAL Air 2 Pro has them). Confirmed needs Nebula SDK API support.
6. **Battery profile**: Beam Pro battery is small. Continuous SSE + audio playback + AR rendering is hot. Document expected runtime + provide aggressive sleep modes.
7. **Multi-PC support**: one phone watching sessions across two PCs (laptop + desktop)? Architecturally simple — phone has multiple `daemon_url`s — but UX gets complex (which session is "active" when both PCs have live sessions?). v2.
8. **Privacy / telemetry**: any phone-side analytics? My lean: zero telemetry by default; opt-in crash reports only.

## Risks

- **XREAL Nebula SDK breakage** — XREAL has shipped breaking SDK updates historically. Mitigation: pin to a tested SDK version; document upgrade procedure.
- **Anthropic API key requirement** — buddy needs an API key. Users without one can't use voice mode. Document clearly + degrade gracefully (mirror + audio still work without buddy).
- **Audio/screen latency mismatch** — TTS describes a screen state that's already changed. Mitigation: timestamp synchronization; "describe what was on screen 200ms ago" framing in buddy's system prompt.
- **Android background restrictions** — Android 14 aggressively kills background apps. Use foreground service for audio + companion connection.
- **Beam Pro hardware availability** — relatively new device, small user base. Mitigation: also test on stock Android phones in DP mode + USB-C-tethered XREAL glasses; Beam Pro becomes a "best supported" target rather than the only one.
- **Window-capture permissions** — `dxcam` and equivalent require Windows display capture permission. Document clearly; macOS path needs different APIs (TBD for v2 macOS support).
- **Open-core split timing** — if AR companion ships before CCT-30 lands, retrofitting a license check is harder. Coordinate the two.

## Future direction: managed relay (option C, paid offering)

The user is interested in a cloud relay model as a future enhancement, not v1 scope. This becomes a natural premium feature once OSS adoption proves the LAN/Tailscale path works:

- **What it is**: a managed websocket relay that codetalker daemons dial out to. Phone connects to the relay URL. Daemon never needs an inbound port, no Tailscale install required.
- **Why paid**: ongoing infra cost (servers, bandwidth, monitoring), plus operational responsibility (uptime, debugging, support). Charging covers maintenance + creates a clean upgrade path for users who want zero-setup remote access.
- **Architecture**: daemon registers a long-lived websocket to `relay.codetalker.dev`; phone authenticates with the same pairing token + relay-issued account token; relay routes frames between them. Encrypted end-to-end (relay can't read content).
- **Dependencies**: requires CCT-30 paid-edition infrastructure (license verification, billing, account system) to be in place first. Doesn't gate v1.
- **Open questions for the future plan**: relay tech (Cloudflare Workers Durable Objects? Self-hosted on Fly.io? Roll our own?); pricing tier (one relay slot per license? metered bandwidth?); migration path from "no relay" to "with relay" without disrupting existing users.

For now: ship v1 LAN+Tailscale, gather usage signal, then design the relay against real demand patterns rather than guessed-at ones.

## Out of scope for v1

- iOS version (different SDK, different distribution; revisit after v1 traction)
- Standalone glasses operation (no phone) — XREAL doesn't support this yet
- Multi-user collaboration (multiple phones watching same daemon)
- Full character avatars in AR (Phase 25 character system integrates as "AR companion avatar" in v2)
- Voice input languages other than English (defer; depends on STT engine)
- Hand tracking / gesture input (XREAL Air 2 Pro doesn't have great hand tracking; defer to glasses with onboard cameras)
- Macro recording ("when I say 'run tests' do X")
- Direct Claude Code main-session injection (locked to buddy-only in v1; revisit if Anthropic ships a remote-input API)

## Verification

End-to-end smoke (after Phase 10):

1. Pair phone with daemon via QR code from dashboard.
2. Put on glasses + Beam Pro. HUD shows the active session badge.
3. TTS narration plays through phone speakers as Claude Code emits Audible blocks.
4. Click → "Hey, what test is currently failing?" → buddy reads transcript → speaks back the answer.
5. Double-click → menu appears → rocker down to next session → click → menu closes, audio re-routes to new session.
6. Menu → toggle screen mirror → see Claude Code window in AR space.
7. Walk to kitchen, daemon stays accessible via Tailscale, no degradation.

## Success criteria

A user can: (1) wear Air 2 Pro + Beam Pro at their desk; (2) hear codetalker narration through glasses speakers; (3) ask the buddy questions via voice without touching the keyboard; (4) switch between active codetalker sessions via the rocker; (5) glance at their PC screen via the AR mirror; (6) walk away from the desk and keep the same flow via Tailscale. All without any keyboard interaction.
