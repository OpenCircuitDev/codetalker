---
description: Pick a voice for codetalker (no arg = show menu)
allowed-tools: mcp__codetalker__tts_list_voices, mcp__codetalker__tts_set_voice, mcp__codetalker__tts_status
argument-hint: "[voice-name]"
---
The user wants to change codetalker's voice. `$ARGUMENTS` is the requested voice (may be empty).

If `$ARGUMENTS` is empty:
1. Call `mcp__codetalker__tts_status` to find the current engine + voice.
2. Call `mcp__codetalker__tts_list_voices` (default engine) to get available voices.
3. Reply with the current voice marked, plus a short numbered list of the others (cap at 12). Ask which one. Do **not** change the voice yet.

If `$ARGUMENTS` is set:
- Call `mcp__codetalker__tts_set_voice` with `{"voice": "$ARGUMENTS"}` and reply with one short confirmation line.
- If the daemon returns an error (unknown voice), list available voices via `tts_list_voices` and ask the user to pick one.
