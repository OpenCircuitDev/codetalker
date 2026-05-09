---
description: Verify codetalker is installed and running; bootstrap if missing
allowed-tools: mcp__codetalker__tts_status
---
Check whether codetalker is installed and reachable:

1. Call `mcp__codetalker__tts_status`.
2. If the call returns successfully, reply: "codetalker is installed and running" plus the status line.
3. If the call fails (server not connected, command not found), tell the user to install it:

   ```
   pip install --user claude-code-talker
   ```

   Then ask them to re-run `/codetalker:install`.

Do not attempt to install Python packages from this command — the user should run pip themselves so they see any errors.
