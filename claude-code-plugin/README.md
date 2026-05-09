# Claude Code Talker — Plugin

Voice companion for Claude Code. Installs as a Claude Code plugin so anyone running plain Claude Code (no VS Code) gets a one-shot install, slash-command control, and a narrator that knows what mode you're in.

## Prerequisite

```
pip install --user claude-code-talker
```

(Optional extras: `claude-code-talker[edge,anthropic]` for Edge TTS + Anthropic narration.)

## Install

In Claude Code:

```
/plugin marketplace add OpenCircuitDev/codetalker
/plugin install codetalker@codetalker
```

Then verify:

```
/codetalker:status
```

If the daemon isn't already running, the plugin's MCP server entry will spawn it on first tool call.

For local development (testing the plugin from a clone before publishing), use the local marketplace path instead:

```
/plugin marketplace add /absolute/path/to/codetalker
/plugin install codetalker@codetalker
```

## What you get

- **5 hooks** auto-registered (`Stop`, `Notification`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`) — narration fires on assistant turns and tool activity.
- **MCP server** named `codetalker` exposing 9 tools Claude can call directly: `tts_speak`, `tts_set_mode`, `tts_status`, `tts_mute`, `tts_unmute`, `tts_list_voices`, `tts_set_voice`, `tts_set_cadence`, `tts_shutdown`.
- **10 slash commands**:

| Command | What it does |
|---|---|
| `/codetalker:mute` | Mute narration |
| `/codetalker:unmute` | Resume narration |
| `/codetalker:mode <name>` | Switch mode (`direct` / `brief` / `live` / `trigger`) |
| `/codetalker:voice <name>` | Pick a voice (no arg → menu) |
| `/codetalker:cadence <name>` | Set live-mode cadence |
| `/codetalker:status` | Show current mode / voice / mute state |
| `/codetalker:open-ui` | Open the daemon's web UI in your browser |
| `/codetalker:start` | Manually start the daemon (fallback) |
| `/codetalker:stop` | Shut the daemon down |
| `/codetalker:install` | Bootstrap install if `pip install` is missing |

- **Daemon-aware skill** `codetalker-narration` that queries the daemon at activation for the live tag list — edits in the web UI take effect on the next prompt without any file write.

## Coexistence with the VS Code extension

The VS Code extension still works. If you have both installed, both will register the same hook command (`claude-code-talker-hook`) and the daemon dedupes the duplicate firings. A future VS Code extension release will detect plugin presence and skip its own hook injection.

## Uninstall

```
/plugin uninstall codetalker
```

This removes the plugin tree but does **not** stop the daemon (the daemon is a separate process). Run `/codetalker:stop` first if you want it gone, or kill `claude-code-talker` from your task manager.

## License

MIT — see LICENSE in the repo root.
