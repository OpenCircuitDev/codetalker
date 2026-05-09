---
description: Set the live-mode cadence (periodic | per_tool_call | per_cluster | significant_only | hybrid)
allowed-tools: mcp__codetalker__tts_set_cadence, mcp__codetalker__tts_status
argument-hint: "[periodic | per_tool_call | per_cluster | significant_only | hybrid]"
---
The user wants to change codetalker's live-mode cadence. `$ARGUMENTS` is the requested cadence (may be empty).

If `$ARGUMENTS` is empty:
1. Call `mcp__codetalker__tts_status`.
2. List the five cadences (periodic, per_tool_call, per_cluster, significant_only, hybrid) and ask which to use. Do not call set yet.

If `$ARGUMENTS` is one of those five:
- Call `mcp__codetalker__tts_set_cadence` with `{"cadence": "$ARGUMENTS"}` and reply with one short confirmation.

Otherwise:
- Reply with the five valid cadence names, no tool call.
