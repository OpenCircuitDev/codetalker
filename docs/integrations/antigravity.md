# CodeTalker for Google Antigravity

Google Antigravity (public preview Nov 2025) is Gemini 3's agent platform — a VS Code OSS fork with a manager view for orchestrating multi-agent workflows.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Antigravity's MCP config

Antigravity uses a standard MCP server config. Find the config file path in Antigravity's Settings → AI → MCP Servers (typically `~/.antigravity/mcp.json` or similar).

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

Or use the Settings UI directly: Add Server → Type: stdio → Command: `codetalker-mcp`.

### 3. Restart Antigravity

The agent + manager view pick up the new MCP server on launch.

## Verify

In Antigravity's manager view, look at the MCP servers panel — `codetalker` should appear with a green status indicator.

In an agent chat:

> Call codetalker.tts_status to report the current state.

You should see the daemon's status text.

## Notes specific to Antigravity

- Antigravity's **manager view** orchestrates multiple Gemini 3 agents in parallel. Match this with codetalker's per-session settings (configure via the webui dashboard at http://localhost:17832): for each agent's session, set a different mode/cadence so the audio stream stays meaningful.
- Antigravity is free for individuals — codetalker's free tier complements that well. The Pro features ($10/mo) light up when you want character voices for differentiating agents audibly (e.g., "agent #1 sounds like Dr. Crow, agent #2 sounds like the Captain").
- Antigravity supports multi-model (Claude Sonnet 4.6, GPT-OSS-120B, Gemini 3). codetalker is model-agnostic; narration triggers off hooks/MCP not model output.
