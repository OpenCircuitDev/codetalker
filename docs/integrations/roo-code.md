# CodeTalker for Roo Code

Roo Code is a community-driven fork of Cline focused on experimental features. MCP integration follows Cline's pattern.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Roo Code's MCP config

VS Code → Roo Code panel → MCP Servers → "Configure" → edit the JSON:

```json
{
  "mcpServers": {
    "codetalker": {
      "command": "codetalker-mcp",
      "args": [],
      "env": {},
      "alwaysAllow": ["tts_status", "tts_set_mode", "tts_mute", "tts_unmute"]
    }
  }
}
```

### 3. Reload Roo Code

VS Code → Command Palette → "Roo Code: Reload" or restart VS Code.

## Verify

In Roo Code chat:

> What MCP servers are connected?

Roo Code should list `codetalker` with the tools count.

## Notes specific to Roo Code

- Roo Code merges new features faster than upstream Cline — if you hit any MCP-handling quirk, check the Roo Code Discord before filing on the codetalker repo.
- Roo Code's autonomous mode is more aggressive than Cline's default. Pair codetalker's `live` mode with `cadence=significant_only` to filter narration to important steps.
