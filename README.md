# Claude Code Talker

Multi-mode voice companion for Claude Code. Ships as an MCP server consumable
by VS Code, Cursor, Claude Desktop, CLI, or any MCP client.

Built on the CodeTalker core (engine-neutral: engines, providers, modes, MCP server shell).

See `docs/superpowers/specs/` (in BF_Workspace) for the full design spec.

## Install for Claude Code

Inside any Claude Code session:

```
/plugin marketplace add OpenCircuitDev/codetalker
/plugin install codetalker@codetalker
```

Prerequisite (one time): `pip install --user claude-code-talker`. Then run `/codetalker:status` to confirm the daemon is reachable.

## Sub-projects

- `core/` — Python MCP server + library (`claude_code_talker`)
- `extension/` — VS Code extension (Phase 6)
- `claude-code-plugin/` — Claude Code plugin: one-shot install via `/plugin install`, slash commands, MCP-spawned daemon (Phase 18)
- `voice-cloner/` — XTTS character voice generation (Phase 5)

## Choosing your install path

- **Using VS Code?** Install `extension/`. Daemon spawn, status bar, command palette, secrets-to-keychain.
- **Using bare Claude Code (terminal, JetBrains, etc.)?** Install `claude-code-plugin/` via `/plugin install`. Slash commands `/codetalker:*`, daemon-aware skill, `tts_set_*` MCP tools Claude can call to self-modulate.
- **Both?** They coexist — same daemon, same hooks; the daemon dedupes any duplicate hook firings.
