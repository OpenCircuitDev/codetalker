---
name: codetalker-narration
description: When the user has codetalker running, write tagged narration blocks for the user-selected trigger types so codetalker can speak them verbatim through TTS.
---

# Codetalker Narration

The user is listening to your work via codetalker (a TTS narrator daemon). For specific moments listed below, write a markdown block with the exact header form shown. Codetalker extracts the content beneath each header and speaks it verbatim. Use this to keep the listener informed without forcing them to read the chat.

!`curl -s --max-time 3 http://127.0.0.1:17832/api/triggers/skill-body 2>/dev/null || echo "(codetalker daemon not running — narration is off; nothing to write)"`
