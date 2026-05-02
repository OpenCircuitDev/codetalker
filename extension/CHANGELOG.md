# Changelog

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
