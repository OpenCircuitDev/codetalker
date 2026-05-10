# CodeTalker for AWS Kiro

AWS Kiro (public preview July 2025) is a VS Code OSS fork with spec-driven development. It supports MCP for multimodal context.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Kiro's MCP config

Kiro stores MCP config alongside its other settings. Edit `~/.aws/kiro/mcp.json` (or use Kiro's Settings → MCP Servers UI):

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

### 3. Restart Kiro

Kiro's agent panel will pick up the new MCP server.

## Verify

In Kiro chat:

> List the MCP context sources available.

You should see `codetalker` with its tools.

## Notes specific to Kiro

- Kiro's spec-driven workflow generates a design + tasks file before coding. If you narrate during the spec-generation step, codetalker's `brief` mode keeps the narration scoped to milestone events (spec saved, tasks generated, etc.) instead of every micro-step.
- Kiro currently supports Python + JavaScript only (as of mid-2026). codetalker's MCP integration works regardless of the target language.
- Kiro is powered by Claude Sonnet/Opus. codetalker has no special handling for any specific model — narration works via hooks/MCP, not via the model's output channel.
