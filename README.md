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

## CodeTalker Pro

Looking for the polished experience? **CodeTalker Pro** is $10/mo and adds:

- **Android companion** — narration on your phone speaker, multi-session fan-in.
- **Voice cloning** — local XTTS clone from a 10-second sample of your own voice (or someone else's, with their consent).
- **Buddy mode** — talk to your Claude session through the phone, with an OpenRouter-mediated conversational layer.
- **Direct dictation** — voice-to-Claude transcription that types straight into your editor.
- **AR companion (XREAL)** — character avatars + caption HUD on the glasses.

Try it free for 14 days at [codetalker.opencircuit.studio](https://codetalker.opencircuit.studio).

## Sub-projects

- `core/` — Python MCP server + library (`claude_code_talker`)
- `extension/` — VS Code extension (Phase 6)
- `claude-code-plugin/` — Claude Code plugin: one-shot install via `/plugin install`, slash commands, MCP-spawned daemon (Phase 18)
- `voice-cloner/` — XTTS character voice generation (Phase 5)

## Use with other AI-coding agents

CodeTalker ships an MCP server (`codetalker-mcp`) that any MCP-compatible AI coding agent can connect to. Per-agent setup snippets:

- **[Cursor](docs/integrations/cursor.md)** — `~/.cursor/mcp.json`
- **[Cline](docs/integrations/cline.md)** (VS Code) — `cline_mcp_settings.json`
- **[Continue.dev](docs/integrations/continue.md)** — `~/.continue/config.yaml`
- **[Windsurf](docs/integrations/windsurf.md)** (Codeium) — `mcp_config.json`
- **[Zed](docs/integrations/zed.md)** — `settings.json` `context_servers`
- **[Codex CLI](docs/integrations/codex-cli.md)** (OpenAI) — `~/.codex/config.toml`
- **[Goose](docs/integrations/goose.md)** (Block) — `~/.config/goose/config.yaml`
- **[Roo Code](docs/integrations/roo-code.md)** — VS Code MCP settings
- **[Replit Agent](docs/integrations/replit.md)** — remote MCP (cloud caveat applies)
- **[AWS Kiro](docs/integrations/kiro.md)** — Kiro's MCP config
- **[Google Antigravity](docs/integrations/antigravity.md)** — Antigravity's MCP config
- **[Aider](docs/integrations/aider.md)** (Pro Plus, coming in v1.x) — bespoke CLI wrapper
- **[JetBrains AI Assistant](docs/integrations/jetbrains.md)** (Pro Plus, coming in v1.x) — bespoke plugin

See [`docs/integrations/README.md`](docs/integrations/README.md) for an overview, troubleshooting, and the MCP tools catalog.

## Choosing your install path

- **Using VS Code?** Install `extension/`. Daemon spawn, status bar, command palette, secrets-to-keychain.
- **Using bare Claude Code (terminal, JetBrains, etc.)?** Install `claude-code-plugin/` via `/plugin install`. Slash commands `/codetalker:*`, daemon-aware skill, `tts_set_*` MCP tools Claude can call to self-modulate.
- **Using a different AI-coding agent?** See the [per-agent integration guides](docs/integrations/README.md) above. One `pip install --user claude-code-talker` covers the daemon for all of them.
- **Multiple at once?** They coexist — same daemon, same hooks; the daemon dedupes any duplicate hook firings.

## Narration modes

CodeTalker's narrator can run in different modes depending on how much context you need:

| Mode | Behavior | Best for |
|------|----------|----------|
| `brief` | One-sentence summary at the end of each turn (default) | Most users; low-distraction continuous narration |
| `live` | Sentence-by-sentence streaming as the agent works | Real-time awareness; ideal for pairing sessions |
| `direct` | Tool outputs spoken near-verbatim, minimal filtering | Deep technical detail; verbose but most complete |
| `critical_only` | Silent unless something errors, blocks, or needs input | Heads-down coding; narration only on obstacles |

Set your mode with `/codetalker:set-mode <mode>` (Claude Code plugin) or via the Pro app.

## Prompt prefixes (advanced)

The narrator LLM can emit special prefixes to tag narration with urgency, architecture weight, or confidence. The daemon parses these and applies audible cues or metadata:

**`[ALERT]`** — Error, blocker, or "drop everything" moment.  
Daemon audible cue: "Heads up."  
Example: `[ALERT] Schema migration failed — vendor API changed.`

**`[CHECKPOINT]`** — Architecturally-significant decision (schema shape, API contract, dependency add, migration path).  
Daemon audible cue: "Checkpoint."  
Example: `[CHECKPOINT] Switching from SQLite to Postgres for replication support.`

**`[UNSURE]`** — Narrator is hedging an inference (not a direct observation).  
Daemon audible cue: None; tags entry `confidence=low` in audit log.  
Example: `[UNSURE] Looks like this fetch failed due to network, but I didn't see the error.`

Multiple prefixes can apply to one narration; they parse in order (`[ALERT]` → `[CHECKPOINT]` → `[UNSURE]`), and audible cues fire in sequence.
