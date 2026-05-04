# Changelog

## 0.3.0 (2026-05-03)

### Added — Extension
- 12 Command Palette commands (was 2): toggle, openWebUI, setSecret,
  changeMode, changeVoice, changeCadence, changeProvider, changeRate,
  editWorkspaceConfig, restartDaemon, viewLog, runSetup.
- Silent Claude Code hook auto-install on first activation.
- OS keychain storage for API keys via `vscode.SecretStorage`. Keys are
  injected as env vars when the daemon spawns; the daemon's existing
  env-first SecretsStore consumes them transparently.
- One-time migration prompt for users with an existing `secrets.yaml`.
- Cross-platform daemon process management — extension state replaces
  the POSIX-only PID-file approach. `tree-kill` for portable termination.
- Vitest test infrastructure for the extension (20 tests).

### Companion daemon-side changes shipped alongside

- **Phase 13** — Virtual user evaluation system. 5 LLM-generated personas
  score recent narrations; auto-tuner proposes teacher_mode cfg changes
  with max-divergence safety gate; new Settings → Eval tab in the Web UI.
- **Phase 13.5** — Narrator context enrichment. PRE_TOOL/POST_TOOL events
  now carry concrete file/command/outcome details. New per-session
  SessionFocus block injected into narration prompts (current task header,
  recent user requests, files-in-play). Teacher directives explicitly
  reference these. Auto-tuner gains a signal→knob rubric.
- **Phase 13.6** — Session-scoped narrate. Concurrent Claude Code sessions
  are now properly isolated; narrations no longer bleed across folders.
  Removed singleton race condition in LiveMode.

### Daemon-side companion changes
- `secrets_store.py` adds `GEMINI_API_KEY` env override.
- New `GET /api/hooks-status` endpoint for extensions to query before installing.

## 0.1.0 — 2026-05-02

Initial release. Phase 6 of Claude Code Talker.

### Added
- Status bar item showing active mode and mute state (click to toggle).
- 10 Command Palette commands: toggle, changeMode, changeVoice, changeCadence,
  changeProvider, changeRate, editWorkspaceConfig, restartDaemon, viewLog, runSetup.
- Multi-step `editWorkspaceConfig` Quick Pick that writes `.claude/tts_workspace.yaml`.
- Auto-spawn daemon on extension activation (configurable via `claudeTts.autoSpawnDaemon`).
- Settings: daemon host/port, status bar poll interval, auto-spawn toggle.
- MCP-over-SSE client wrapping the daemon.

### Known limitations
- Cadence/provider/rate commands surface informational messages; the actual
  config write goes through the `Edit Workspace Config` walkthrough.
- Status bar polling fires every 2s; `tts_status` is in-memory but each call
  opens an SSE message exchange. Raise the interval if you find it noisy.
- Auto-spawn requires `claude-code-talker` to be on PATH. If not, the extension
  shows a warning; install the Python package and reload.
