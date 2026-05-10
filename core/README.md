# claude-code-talker (core)

Python MCP server providing voice + narration for Claude Code. Engine-neutral
TTS pipeline with multiple modes (brief / direct / live / trigger), per-session
profiles, markup-aware reading, character voices, and a React Web UI shell.

Part of the Claude Code Talker monorepo (see [the parent README](../README.md)).

## Install

### From source (recommended until first PyPI release)

    pip install --user -e core/

From the repo root. Installs in editable mode so any source change is picked up
on next start.

### Optional extras

    pip install --user -e 'core/[edge,anthropic,xtts]'

| Extra | What it pulls in |
|---|---|
| `dev` | `pytest`, `pytest-asyncio`, `pytest-mock` for the test suite |
| `edge` | `edge-tts` for the Microsoft Edge online TTS engine |
| `anthropic` | `anthropic` SDK for the Anthropic LLM provider |
| `xtts` | `TTS>=0.22` for XTTS character-voice synthesis (heavy; ~2GB model) |

### From PyPI (planned)

    pip install --user claude-code-talker

The PyPI release is not yet live — the package will land at v0.2.0. Once
published, the prerequisite line in the parent README's `/plugin install`
flow will start working without a clone.

## Quick start

Run the daemon:

    claude-code-talker

By default the HTTP/SSE listener binds to `127.0.0.1:17832`. To allow an
on-LAN companion (XREAL Beam Pro, another laptop on Tailnet, etc.) to reach
it:

    CCT_DAEMON_HOST=0.0.0.0 claude-code-talker

Open the Web UI at `http://127.0.0.1:17832/` (or your LAN IP if bound). The
dashboard surfaces every Claude Code session it sees, with per-session knobs
for mode, voice, cadence, character, and markup verbosity.

## CLI entry points

Four scripts ship with the package:

| Command | Maps to | Purpose |
|---|---|---|
| `claude-code-talker` | `claude_code_talker.server:main` | Run the daemon (HTTP + MCP server). Default port 17832. |
| `claude-code-talker-hook` | `claude_code_talker.hook_cli:main` | Claude Code hook bridge — Claude Code invokes this on session events; the script forwards into the daemon. |
| `claude-code-talker-setup` | `claude_code_talker.setup:main` | First-time setup helper. Initializes the config dir, picks a default voice, prints next-step hints. |
| `claude-code-talker-mcp-stdio` | `claude_code_talker.mcp_stdio:main` | Stdio MCP server — alternative to the TCP daemon for direct MCP-client invocation (e.g., Claude Desktop's stdio config). Auto-spawns the daemon if needed. |

## MCP usage

Register the daemon as an MCP server in your client of choice. Examples:

### Claude Code (`~/.claude/claude_desktop_config.json` or `mcp.json` in project)

```json
{
  "mcpServers": {
    "codetalker": {
      "command": "claude-code-talker-mcp-stdio"
    }
  }
}
```

The stdio shim auto-launches the TCP daemon if it isn't already running.

### Cursor / VS Code

Most MCP-aware IDEs accept the same `command + args` shape. Point them at
`claude-code-talker-mcp-stdio`.

The MCP server exposes:

- `tts_status` — current mode, voice, cadence, mute state, active session.
- `tts_set_mode` — switch between brief / direct / live / trigger.
- `tts_set_voice` / `tts_list_voices` — voice library control.
- `tts_set_cadence` — slow / normal / fast narration speed.
- `tts_mute` / `tts_unmute` — gate the audio output.
- `tts_speak` — speak arbitrary text (used by the plugin's slash commands).
- `tts_shutdown` — clean daemon shutdown.

These tools let Claude self-modulate ("a little louder, please") via MCP
without leaving the session.

## Configuration

Config dir: `~/.config/claude-code-talker/` (Linux/macOS) or
`%APPDATA%\claude-code-talker\` (Windows). Created by
`claude-code-talker-setup`.

| Env var | Default | Purpose |
|---|---|---|
| `CCT_DAEMON_HOST` | `127.0.0.1` | Listen interface. Set `0.0.0.0` for LAN. |
| `CCT_PORT` | `17832` | HTTP/SSE port. |
| `CCT_CONFIG_DIR` | `~/.config/claude-code-talker` | Override the config dir location. |

Per-session state and profiles live under the config dir. Voice library is
auto-discovered from `~/.local/share/piper/` (Piper) or per-engine paths.

## Tests

    cd core
    pytest -q

Expected: **1049 passed, 6 conditional skips** (optional engines / providers
without their deps installed). Test infrastructure: pytest + pytest-asyncio
(auto mode) + pytest-mock + respx for HTTP mocking.

## Releases

See [CHANGELOG.md](CHANGELOG.md) for release notes. Current version: **0.2.0**.

Build a wheel + sdist for distribution:

    python -m build --outdir dist

Both `claude_code_talker-0.2.0-py3-none-any.whl` and `.tar.gz` land in
`dist/`. Upload via `twine upload dist/*` once you have a PyPI token.

## License

MIT — see the parent repo's [LICENSE](../LICENSE).

## Other subprojects

- [`extension/`](../extension/) — VS Code extension that spawns and controls
  the daemon, surfaces state in the status bar.
- [`claude-code-plugin/`](../claude-code-plugin/) — Claude Code plugin for
  bare CLI / JetBrains users; ships `/codetalker:*` slash commands.
- [`voice-cloner/`](../voice-cloner/) — XTTS reference-WAV pipeline for
  cloned character voices.
- `companion-android/` (separate `codetalker-pro` repo) — XREAL Beam Pro AR
  companion app.
