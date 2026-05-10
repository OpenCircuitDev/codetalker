# CodeTalker for Zed

Zed (1.0, released April 2026) supports MCP via its `context_servers` config.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Zed's settings

Open Zed → Settings (cmd-,) → `settings.json`. Add a `context_servers` block:

```json
{
  "context_servers": {
    "codetalker": {
      "command": {
        "path": "codetalker-mcp",
        "args": [],
        "env": {}
      }
    }
  }
}
```

If `codetalker-mcp` isn't on Zed's PATH, use the absolute path:

```json
"path": "/Users/you/.local/bin/codetalker-mcp"
```

### 3. Restart Zed

Zed's Agent Panel will discover the new context server on startup.

### 4. Per-action permissions

Zed deliberately requires explicit permission for each tool call (its "permissioned per-action" model). The first time the Agent Panel wants to call `mcp__codetalker__tts_speak`, you'll see a permission prompt — accept "allow always" for the tools you trust.

Recommended per-action allowlist:
- `tts_status` — always allow
- `tts_set_mode` — always allow
- `tts_mute` / `tts_unmute` — always allow
- `tts_speak` — ask each time (prevents surprise narration)
- `tts_shutdown` — ask each time (rare)

## Verify

In Zed's Agent Panel:

> Use codetalker.tts_status and tell me the state.

You should see a permission prompt followed by the status output.

## Notes specific to Zed

- Zed 1.0's **parallel agents** feature is a perfect match for codetalker — when multiple agents run in parallel, codetalker's per-session mode + cadence settings (via the webui dashboard) let you narrate one of them in `live` mode while the others are `brief` or muted. Set this up via `claude-code-talker serve` + open the dashboard at http://localhost:17832.
- If you use Zed's collaboration feature (shared editing), only the host's codetalker daemon narrates — codetalker is local-first by design.
