# CodeTalker for Cursor

Cursor speaks MCP natively. Add codetalker to your Cursor MCP config and the agent can narrate its work aloud.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

Verify `codetalker-mcp` is on your PATH:

```bash
which codetalker-mcp        # macOS/Linux
where.exe codetalker-mcp    # Windows
```

### 2. Add to Cursor's MCP config

**Global config** (recommended) — applies across all Cursor projects:

Edit `~/.cursor/mcp.json` (create if missing):

```json
{
  "mcpServers": {
    "codetalker": {
      "command": "codetalker-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

**Per-project config** — `.cursor/mcp.json` in your project root, same shape.

### 3. Restart Cursor

Cursor loads MCP servers at startup. After restart, the agent has access to codetalker tools (`mcp__codetalker__tts_*`).

### 4. (Optional) Tell Cursor when to use codetalker

In Cursor's Settings → AI → Rules, add:

```
You have access to mcp__codetalker__* tools. When you're about to chain many tool
calls without user input, call mcp__codetalker__tts_set_mode with mode="brief"
so the user gets a summary instead of every step. Switch back when you're done.
```

This is optional — without it, Cursor's narration just uses whatever mode the user set in codetalker's webui dashboard.

## Verify

After restart, in a Cursor chat:

> Use the codetalker tts_status tool to report current state.

You should hear (or see in chat) the daemon's status.

## Troubleshooting

- **Cursor doesn't see the tools after restart** — open Cursor's MCP status panel (Settings → MCP) and check for errors. The most common cause is `codetalker-mcp` not being on the PATH that Cursor uses (Cursor sometimes uses a different shell env than your terminal).
- **Workaround for PATH issues** — use the absolute path in the config:
  ```json
  "command": "/Users/you/.local/bin/codetalker-mcp"
  ```
- **Daemon spawn fails** — check that you can run `claude-code-talker serve` manually from a terminal. If that works but the shim's auto-spawn doesn't, file an issue with the shim's stderr output (visible in Cursor's MCP logs).

## What's next

If you want Pro features (character voices, animated avatars), subscribe at [CodeTalker.opencircuit.studio](https://codetalker.opencircuit.studio) — your existing codetalker installation will pick up the entitlement after sign-in.
