# Changelog

All notable changes to the **claude-code-talker** core package are documented
here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Active development against `main`. Released v0.2.0 entry below describes
the most recent shipped cut.

---

## [0.2.0] — 2026-05-09

### Added

- **AR Companion daemon support (CCT-31).** REST endpoints under
  `/api/companion/*` for buddy session management
  (`BuddyManager`, `BuddyClaude`), per-session TTS audio frame fan-out
  (`AudioStreamHub`), pairing token store with TTL + persistence
  (`PairingStore`), and screen-capture source on Windows
  (`ScreenCaptureSource` via dxcam + win32gui).
- **LAN binding for the daemon.** Setting `CCT_DAEMON_HOST=0.0.0.0`
  binds the HTTP/SSE listener to all interfaces so an Android
  companion on the same Wi-Fi or Tailnet can reach it. Default
  remains `127.0.0.1`.
- **QR pairing `daemon_url` resolution.** Pair-AR-Companion QR codes
  now embed the daemon's reachable LAN URL instead of the loopback
  trap that previous builds emitted.
- **Mesh provider system (Phase 25b).** `Mesh3DProvider` ABC,
  three concrete adapters (Hyper3D Rodin Gen-2, Meshy v2, Tripo3D),
  `MeshJobTracker` with sidecar JSON persistence, 5 REST endpoints
  under `/api/mesh-jobs/*`, secrets-store entries for the three API
  keys.
- **Voice cloning system (Phase 25c).** `CloneJobTracker` with
  sidecar persistence, `POST /api/clone-voice` and
  `GET /api/voice-clone-jobs`, character-attach lifecycle wired
  through `cfg.resolve_for_session`.
- **Character system maturity (Phase 25a).** Full attach/detach
  lifecycle, persona colour, voice_ref + cloned-voice routing,
  mesh_path passthrough.
- **WebUI tab navigation (Phase 27).** Top-level
  Sessions / Characters / Markup / Activity / Preferences tabs;
  SessionCard 4-zone redesign; LiveTicker with filter ribbon;
  CharacterAvatar with persona gradient.
- **Per-session quick markup toggles (Phase 29).** Inline overlay
  PUT controls on every session card.
- **Multiple WebUI fixes (Phase 28).** Stable refs to keep
  Select popups from dismissing on re-render; `display_name`
  flows through SessionCard headlines, CharacterDetail attach
  dropdowns, and overall session ordering.
- **Cadence picker in SessionControls.** End-user knob for narration
  rate (slow / normal / fast) wired to the resolved cfg layer.
- **Resizable narration right-rail.** WebUI shell column is
  drag-resizable and persisted across reloads.

### Changed

- **`__version__`** in `claude_code_talker/__init__.py` now matches
  `pyproject.toml`: `0.2.0`.
- **API key surface** in `/api/secrets`: now includes
  `hyper3d`, `meshy`, and `tripo3d` slots.
- **`mesh_path` URL handling.** Signed CDN URLs (`?Signature=…&Expires=…`)
  no longer break the file-extension extraction.

### Fixed

- **CharacterDetail attach dropdown** previously sorted by character
  `id` instead of `display_name`.
- **`mesh_path` round-trip.** Persistence regression covered by a
  test case in Phase 25b Task 11.
- **GET `/api/secrets`** now returns the three new mesh-provider
  api_key slots.

### Tests

- 1049 unit tests passing, 6 conditional-skip (optional deps:
  edge-tts, anthropic, XTTS).
- Full `pytest -q` run-time ~95s on a Ryzen 5800 + Python 3.13.

---

## [0.1.0] — initial public scope

First public-facing scope of the codetalker core. Although never
formally released to PyPI, the 0.1.0 line is the design baseline
that landed in this repo before the version bump.

### Added

- **MCP server** (`claude_code_talker.server`) exposing TTS-control
  tools to any MCP client (Claude Code, Cursor, Claude Desktop, VS
  Code, CLI). Tools: `tts_status`, `tts_set_mode`, `tts_mute`,
  `tts_unmute`, `tts_list_voices`, `tts_set_voice`,
  `tts_set_cadence`, `tts_speak`, `tts_shutdown`.
- **Stdio MCP shim** (`claude_code_talker.mcp_stdio`) for
  direct MCP-client invocation when a TCP daemon is undesirable.
- **Modes:** brief (turn-end summary), direct (stream-as-you-go),
  live (turn-by-turn live read), trigger (markup-keyed activations).
- **Cadence engine** (`claude_code_talker.cadence`) with strategies
  for token-rate-aware narration pacing.
- **Profiles + persistent sessions.** Session state survives
  restarts via `persistent_sessions.py`; profile resolution layered
  through `config.resolve_for_session`.
- **Markup awareness** (Phase 26). Per-form treatments
  (`code_fence`, `tool_output`, `inline_code`, `file_path`,
  `todo_update`, `plan_block`) with allowed kinds (skip / describe /
  read / etc.).
- **Engines:** Piper (default), edge-tts (optional), ElevenLabs
  (optional), OpenAI (optional), XTTS (optional, via the voice-cloner
  pipeline).
- **Provider:** Ollama LLM provider for offline summarization.
- **Web UI** (React + Vite, served from `claude_code_talker/webui/`)
  with Sessions / Markup / Activity / Preferences tabs.
- **Hook system** (`hook_cli`) bridges the Claude Code hook
  protocol into the daemon's narration pipeline.
- **Setup CLI** (`setup.py`) for first-time configuration.
- **Token tracker, narration log, narration stream, TTS cache** —
  the baseline observability + caching infrastructure.
- **Triggers + tags** for fine-grained narration activation.

---

[Unreleased]: https://github.com/OpenCircuitDev/codetalker/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/OpenCircuitDev/codetalker/releases/tag/v0.2.0
[0.1.0]: https://github.com/OpenCircuitDev/codetalker/releases/tag/v0.1.0
