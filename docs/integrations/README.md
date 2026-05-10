# CodeTalker — Multi-Platform AI-Coding Agent Integrations

CodeTalker ships an MCP (Model Context Protocol) server that any MCP-compatible AI coding agent can connect to. Once connected, the agent can narrate its work aloud, switch narration modes, mute itself for long agentic loops, and (with Pro) use cloned voices and animated character avatars.

This directory contains per-agent installation snippets so users can wire codetalker into their preferred AI-coding setup without hunting through docs.

## Prerequisites (one time)

```bash
pip install --user claude-code-talker
```

That installs both the daemon (`claude-code-talker`) and the MCP stdio shim (`codetalker-mcp`). The daemon runs locally on port 17832 by default; the shim auto-spawns the daemon when an agent first connects, so users don't need to start it manually.

For voice models, run `claude-code-talker-setup` once to download Piper voices (~100 MB).

## Per-agent integration guides

| Agent | Integration mechanism | Guide |
|---|---|---|
| **Claude Code** (Anthropic) | Native hooks + MCP via plugin | [`claude-code.md`](claude-code.md) |
| **Cursor** | MCP via `.cursor/mcp.json` | [`cursor.md`](cursor.md) |
| **Cline** (VS Code) | MCP via `cline_mcp_settings.json` | [`cline.md`](cline.md) |
| **Continue.dev** | MCP via `config.yaml` | [`continue.md`](continue.md) |
| **Windsurf** (Codeium) | MCP via `mcp_config.json` | [`windsurf.md`](windsurf.md) |
| **Zed** | MCP via `settings.json` `context_servers` | [`zed.md`](zed.md) |
| **Codex CLI** (OpenAI) | MCP via `~/.codex/config.toml` | [`codex-cli.md`](codex-cli.md) |
| **Goose** (Block) | Extension via `~/.config/goose/` | [`goose.md`](goose.md) |
| **Roo Code** | MCP via VS Code settings | [`roo-code.md`](roo-code.md) |
| **Replit Agent** | MCP via Replit's MCP settings | [`replit.md`](replit.md) |
| **AWS Kiro** | MCP via Kiro's MCP config | [`kiro.md`](kiro.md) |
| **Google Antigravity** | MCP via Antigravity's MCP config | [`antigravity.md`](antigravity.md) |
| **Aider** | Bespoke CLI wrapper (not MCP) | [`aider.md`](aider.md) — coming in v1.x |
| **JetBrains AI Assistant** | Bespoke plugin (not MCP) | [`jetbrains.md`](jetbrains.md) — coming in v1.x |

## What you get

Once connected, the agent can call these MCP tools (free tier — no subscription required):

- `tts_speak(text)` — speak arbitrary text
- `tts_set_mode(mode)` — switch between `direct` / `brief` / `live` / `trigger`
- `tts_status()` — get current state
- `tts_mute()` / `tts_unmute()` — silence without changing config
- `tts_list_voices(engine?)` — list available voices
- `tts_set_voice(voice, engine?)` — change active voice
- `tts_set_cadence(cadence)` — for `live` mode: `periodic` / `per_tool_call` / `per_cluster` / `significant_only` / `hybrid`
- `tts_shutdown()` — gracefully stop the daemon

With a **Pro subscription** ($10/mo at [CodeTalker.opencircuit.studio](https://codetalker.opencircuit.studio)), additional tools unlock:

- `attach_character(session_id, character_name)` — attach a character with cloned voice + animated 3D avatar
- `list_characters()` — show the character library
- (and platform-specific Pro features depending on the agent)

## How the connection works

```
┌──────────────────┐     stdio MCP     ┌─────────────────┐    HTTP+SSE    ┌─────────────────┐
│ Your AI agent    │ ───────────────▶ │ codetalker-mcp  │ ─────────────▶ │ codetalker      │
│ (Cursor / Cline /│                  │ (stdio shim,    │                │ daemon          │
│  Continue / ...) │                  │  auto-spawns    │                │ (Python, local) │
└──────────────────┘                  │  daemon)        │                │ port 17832      │
                                      └─────────────────┘                └─────────────────┘
```

The shim is short-lived per-session; the daemon is a singleton that survives across agent sessions. Multiple agents can connect to the same daemon simultaneously (e.g., Claude Code in one terminal + Cursor in another) and share state.

## Troubleshooting

- **"daemon failed to start"** — ensure `claude-code-talker` is on your PATH. Try `which claude-code-talker` (macOS/Linux) or `where.exe claude-code-talker` (Windows). If missing, run `pip install --user claude-code-talker` and ensure your Python user-scripts dir is on PATH.
- **"unknown tool"** — make sure your agent is using the latest version of codetalker. The tool list expanded in v0.2.0+.
- **No audio** — run `claude-code-talker-setup` to download voice models, or check that your system's default audio device is selected.
- **Daemon won't shut down** — `claude-code-talker stop` or kill the PID in `~/.claude-code-talker/daemon.pid`.

For deeper issues, file at https://github.com/OpenCircuitDev/codetalker/issues.

## Submitting to MCP registries

CodeTalker is listed on several MCP discovery sites. See [`mcp-registries.md`](mcp-registries.md) for the submission metadata used for each registry.
