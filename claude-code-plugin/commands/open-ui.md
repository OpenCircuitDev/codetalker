---
description: Open the codetalker daemon's web UI in your default browser
---
Open the codetalker web UI:

!`"${CLAUDE_PLUGIN_ROOT}/bin/open-ui.cmd" 2>nul || "${CLAUDE_PLUGIN_ROOT}/bin/open-ui.sh"`

If the daemon isn't running, the page won't load — start it with `/codetalker:start`.
