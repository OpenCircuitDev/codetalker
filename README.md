# Claude Code Talker

Multi-mode voice companion for Claude Code. Ships as an MCP server consumable
by VS Code, Cursor, Claude Desktop, CLI, or any MCP client.

Built on the CodeTalker core (engine-neutral: engines, providers, modes, MCP server shell).

See `docs/superpowers/specs/` (in BF_Workspace) for the full design spec.

## Sub-projects

- `core/` — Python MCP server + library (`claude_code_talker`)
- `extension/` — VS Code extension (Phase 6)
- `voice-cloner/` — XTTS character voice generation (Phase 5)
