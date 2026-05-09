---
description: Verify codetalker is installed; print specific fix commands for any missing piece
allowed-tools: mcp__codetalker__tts_status, mcp__codetalker__tts_list_voices
---

Diagnose codetalker's install state and tell the user exactly what to run if anything is missing.

Steps:
1. Try calling `mcp__codetalker__tts_status`.
   - If the call succeeds, parse the response. Note the active engine (e.g. `engines=['piper']`).
   - If the call fails (server not connected, command not found), the daemon isn't reachable. Skip to step 4.

2. Try calling `mcp__codetalker__tts_list_voices` with `{}`.
   - If the response is empty, the engine has no voices installed. Tell the user:
     ```
     Engine reachable but no voices installed. Run:
       claude-code-talker setup
     ```
     Then stop.

3. If status worked and voices list is non-empty, reply: "codetalker is installed and ready" plus the one-line status, then stop.

4. (Daemon unreachable branch.) Tell the user that the daemon isn't running. Give them the **first** of these that applies:
   - If `claude-code-talker` is not on PATH: instruct `pip install --user claude-code-talker`.
   - If it IS on PATH: instruct `claude-code-talker serve` in a separate terminal, or just run `/codetalker:start` to background it.

   Pick exactly one fix to suggest based on the failure mode. Don't dump every possible cause.

5. Never run pip yourself. The user runs it; you tell them what to type.
