---
description: Gracefully shut down the codetalker daemon
allowed-tools: mcp__codetalker__tts_shutdown
---
Call `mcp__codetalker__tts_shutdown` with no arguments. Reply with one short confirmation line.

The daemon will exit; subsequent `/codetalker:*` commands will respawn it on demand.
