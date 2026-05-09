---
description: Start the codetalker daemon manually (fallback if MCP shim died)
---
Spawn the codetalker daemon in the background:

!`claude-code-talker serve --background 2>&1 || claude-code-talker serve 2>&1 &`

This is a manual fallback. Normally the plugin's MCP server entry auto-spawns the daemon on first tool call.
