# CodeTalker for Cline

Cline (the VS Code agent) supports MCP natively. Add codetalker to its MCP settings and Cline can narrate its work.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Cline's MCP config

Open VS Code → Cline panel → MCP Servers icon (top-right) → "Configure MCP Servers" → opens `cline_mcp_settings.json`.

Add the `codetalker` entry to `mcpServers`:

```json
{
  "mcpServers": {
    "codetalker": {
      "command": "codetalker-mcp",
      "args": [],
      "env": {},
      "alwaysAllow": [],
      "disabled": false
    }
  }
}
```

If you want Cline to call codetalker tools without per-call confirmation, add them to `alwaysAllow`:

```json
"alwaysAllow": ["tts_set_mode", "tts_mute", "tts_unmute", "tts_status"]
```

(Don't auto-allow `tts_speak` — keeping it in the confirm-each-call list prevents surprise narration.)

### 3. Reload Cline

VS Code → Command Palette → "Cline: Restart" — or just restart VS Code.

### 4. (Optional) Cline rules

In Cline's Settings → Custom Instructions, add:

```
You have access to mcp__codetalker__* tools. Default to letting hooks narrate
automatically. Switch to brief mode (tts_set_mode brief) when starting a long
agentic loop, and back to direct/live afterwards.
```

## Verify

In a Cline chat:

> Call mcp__codetalker__tts_status and tell me what you find.

Cline should call the tool and return the status text.

## Troubleshooting

- **"command not found"** — VS Code's MCP runs in a non-login shell that often misses user-scripts paths. Use the absolute path: `which codetalker-mcp` → paste into `command` field.
- **Tools missing after restart** — check Cline's "Output" panel (View → Output → "Cline") for MCP errors.

## Notes specific to Cline

- Cline's checkpoint feature interacts cleanly with codetalker — when you rewind to a checkpoint, codetalker's session state stays (it's stored in the daemon, not in Cline).
- If you use Cline's autonomous mode (long-running agent), set codetalker to `live` mode + `significant_only` cadence so you only hear about meaningful steps.
