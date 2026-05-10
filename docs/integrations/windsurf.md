# CodeTalker for Windsurf

Windsurf (formerly Codeium) supports MCP via Cascade — its agent integrates with MCP servers from Wave 3 (Feb 2025) onward.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Windsurf's MCP config

Edit `~/.codeium/windsurf/mcp_config.json`:

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

Or use Windsurf's Settings → MCP Servers → "Add Server" UI:
- **Name:** `codetalker`
- **Command:** `codetalker-mcp`
- **Args:** *(empty)*

### 3. Restart Windsurf

The MCP server is loaded at Cascade startup. Restart Windsurf to pick up the new config.

### 4. Cascade and the 100-tool ceiling

Windsurf enforces a hard limit of 100 tools per Cascade session. CodeTalker contributes 9 agent-facing tools (plus 5 internal hook handlers not exposed via the shim). If you have many other MCP servers attached, prioritize codetalker on the "active" list in MCP settings.

## Verify

In a Cascade chat:

> Call the codetalker tts_status tool to report state.

Look for a blue-checkmark badge on the codetalker server in MCP settings — that means Windsurf verified the server passes their basic compatibility check.

## Notes specific to Windsurf

- Cascade's "Write" mode involves longer agentic loops than its "Chat" mode. Switch codetalker to `live` mode (`tts_set_mode live`) when starting a Write task, then back to `direct` for chat.
- If you toggle Cascade between local models and Anthropic Claude / OpenAI GPT, codetalker keeps working — it doesn't care which model is on the other end of MCP.
