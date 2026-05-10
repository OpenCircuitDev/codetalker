# CodeTalker for Claude Code

Claude Code is codetalker's original integration target — the experience is the most polished here.

## Install

Inside any Claude Code session:

```
/plugin marketplace add OpenCircuitDev/codetalker
/plugin install codetalker@codetalker
```

That's it. The plugin installs:
- The MCP server config (`claude-code-talker-mcp-stdio` invoked over stdio)
- Hook handlers for `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `Notification`
- Slash commands (`/codetalker:status`, `/codetalker:mute`, `/codetalker:mode`, etc.)
- A Claude self-modulation guide (see `claude-code-plugin/CLAUDE.md`)

**Prerequisite (one time):** `pip install --user claude-code-talker`.

## What you get (Claude Code-specific)

Beyond the universal MCP toolset documented in the main [README](README.md), Claude Code gets:

- **Automatic narration via hooks** — Claude Code fires hook events at every turn (`UserPromptSubmit` when you type, `PreToolUse` before each tool call, etc.). codetalker subscribes to these and narrates accordingly, with no model-side cooperation needed.
- **The `codetalker-narration` skill** — Claude is told when and how to write `## Audible <Tag>` blocks for codetalker to TTS. The skill content is fetched live from the daemon at session start, so the active tag list reflects user preferences from the webui dashboard.
- **Self-modulation** — the Claude self-modulation guide (`CLAUDE.md` in the plugin) tells Claude when to call `tts_set_mode(brief)` to spare you a long agentic loop, when to `tts_mute` if you ask it to be quiet, etc.
- **`/codetalker:status`, `/codetalker:mode`, `/codetalker:mute` slash commands** — quick controls without leaving the conversation.

## Verify

```
/codetalker:status
```

This calls `mcp__codetalker__tts_status` and prints the current state. You should hear (and see) the response.

## Notes specific to Claude Code

- The plugin's hook handlers and the MCP server share state via the daemon — there's no race condition between "Claude hook fires" and "Claude calls MCP tool."
- The daemon survives across Claude Code sessions and across IDE restarts. To stop it: `/codetalker:stop` or `claude-code-talker stop`.
- For VS Code users who run Claude Code inside VS Code's terminal, **install the `extension/` package** instead of (or in addition to) the plugin. The extension adds a status bar widget, command palette entries, and secrets-to-keychain integration. Both can coexist — they share the same daemon.
