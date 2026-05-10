# CodeTalker for Continue.dev

Continue (the open-source VS Code / JetBrains assistant) speaks MCP natively (via the YAML config).

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Continue's config

Edit `~/.continue/config.yaml` (or your assistant's specific config file):

```yaml
mcpServers:
  - name: codetalker
    command: codetalker-mcp
    args: []
    env: {}
```

If you maintain an assistant via [Continue Hub](https://hub.continue.dev), add codetalker as a tool block on the hub. The codetalker assistant page is at https://hub.continue.dev/assistants/codetalker (TBD — submission planned in SP-7 of the launch master plan).

### 3. Reload Continue

VS Code → Command Palette → "Continue: Reload" — or restart your IDE.

### 4. (Optional) Continue rules block

In your `config.yaml`, you can add a system message guiding Continue's use of codetalker:

```yaml
systemMessage: |
  You have access to codetalker tools (mcp tools from the codetalker MCP server).
  Use tts_set_mode to switch between direct/brief/live based on workload.
  Don't call tts_speak directly — narration happens via hooks.
```

## Verify

In a Continue chat:

> List the MCP tools available to you.

You should see `codetalker.tts_speak`, `codetalker.tts_set_mode`, and the rest.

## Notes specific to Continue

- Continue's "Quick Edit" command (cmd-I) doesn't typically need narration — it's fast. Save codetalker for "Chat" interactions and the autonomous "Agent" mode.
- Continue supports MCP `resources` and `prompts` in addition to `tools`. CodeTalker currently exposes tools only; resources/prompts may come in v1.x.
