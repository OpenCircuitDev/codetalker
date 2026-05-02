# Claude Code Talker — VS Code Extension

Voice companion for Claude Code. Wraps the Python `claude-code-talker`
daemon in a VS Code UI: status bar indicator, Command Palette commands,
and a workspace config editor.

## Features

- **Status bar** (bottom right): shows the active mode (`direct` / `brief` / `live`) and mute state. Click to toggle mute.
- **Command Palette** (`Ctrl+Shift+P` → search "Claude TTS"): 10 commands for everything you'd otherwise edit in YAML.
- **Workspace config editor**: multi-step Quick Pick that writes `.claude/tts_workspace.yaml` for the current workspace.
- **Auto-spawn daemon**: extension launches the Python daemon on activation if it isn't already running.

## Prerequisites

- Python 3.11+
- `pip install claude-code-talker` (Phase 1+ release)
- Run `claude-code-talker-setup` once to scaffold global config and verify Piper / cloud engine availability.

## Install

From a downloaded VSIX:

    code --install-extension claude-code-talker-vscode-0.1.0.vsix

Or once published to the Marketplace, search "Claude Code Talker".

## Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `claudeTts.daemonHost` | `127.0.0.1` | Daemon SSE host |
| `claudeTts.daemonPort` | `17832` | Daemon SSE port |
| `claudeTts.statusBarPollIntervalMs` | `2000` | Status-bar refresh interval |
| `claudeTts.autoSpawnDaemon` | `true` | Auto-launch daemon on activation if not running |

## Commands

| Command | Action |
|---------|--------|
| `Claude TTS: Toggle Mute` | Mute/unmute the daemon (status bar click does the same) |
| `Claude TTS: Change Mode` | Switch between `direct` / `brief` / `live` |
| `Claude TTS: Change Voice` | Pick a voice and play a sample |
| `Claude TTS: Change Cadence (Live Mode)` | Pick a cadence strategy (workspace config) |
| `Claude TTS: Change LLM Provider` | Pick a provider (workspace config) |
| `Claude TTS: Change Rate` | Set speech rate (workspace config) |
| `Claude TTS: Edit Workspace Config` | Multi-step walkthrough that writes `.claude/tts_workspace.yaml` |
| `Claude TTS: Restart Daemon` | Graceful shutdown + auto-spawn |
| `Claude TTS: View Daemon Log` | Open `~/.claude/scripts/codetalker.log` |
| `Claude TTS: Run Setup Wizard` | Run `claude-code-talker-setup` in a terminal |

## Architecture

The extension is a thin client. The daemon does all the work: hook event
processing, mode strategies, audio queue, LLM calls, etc. The extension
talks to the daemon via MCP-over-SSE on `http://127.0.0.1:17832/sse`.

```
   VS Code window
        │
        ▼
   ┌──────────────────────┐
   │ Extension (TS)       │
   │ • status bar         │
   │ • commands           │
   │ • config editor      │
   │ • MCP-over-SSE client│
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────┐
   │ Daemon (Python)      │
   │ port 17832           │
   └──────────────────────┘
```

## License

MIT — see [LICENSE](LICENSE).
