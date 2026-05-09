---
description: Switch codetalker narration mode (direct | brief | live | trigger)
allowed-tools: mcp__codetalker__tts_set_mode, mcp__codetalker__tts_status
argument-hint: "[direct | brief | live | trigger]"
---
The user wants to change codetalker's narration mode. `$ARGUMENTS` is the requested mode (may be empty).

If `$ARGUMENTS` is empty:
1. Call `mcp__codetalker__tts_status` to find the current mode.
2. Reply with the current mode and the four options on one line each, then ask which to use. Do **not** change the mode in this case.

If `$ARGUMENTS` is one of `direct`, `brief`, `live`, `trigger`:
- Call `mcp__codetalker__tts_set_mode` with `{"mode": "$ARGUMENTS"}` and reply with one short confirmation line.

Otherwise:
- Reply with the four valid mode names, do not call any tool.
