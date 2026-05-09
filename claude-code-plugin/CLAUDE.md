# Claude self-modulation guidance — codetalker plugin

The user has the **codetalker** plugin installed. You can call codetalker's MCP tools directly to modulate the narration without making the user reach for a slash command. Use this judgment sparingly — the user installed codetalker because they *want* to listen, so don't silence yourself reflexively.

Tools available (namespaced as `mcp__codetalker__*`):

- `tts_status` — current mode / mute state / engine
- `tts_set_mode` — `direct` | `brief` | `live` | `trigger`
- `tts_mute` / `tts_unmute`
- `tts_set_cadence` — only meaningful in `live` mode
- `tts_speak` — speak arbitrary text (rare; usually not needed because hooks narrate automatically)

## When to self-modulate

- **Long agentic loop incoming** (you're about to chain 10+ tool calls without user input): consider `tts_set_mode("brief")` so the user gets a 2–4-sentence summary at the end instead of every step. Switch back to `direct` afterwards if that's what they had.
- **You're about to dump a wall of code or output** that the user shouldn't have to listen to: write a `## Audible Summary` block at the top describing what's about to appear, instead of letting the narrator read the wall verbatim.
- **The user explicitly says "be quiet" / "stop talking" / "shut up"**: call `tts_mute`. If they say "narrate again" / "keep talking", call `tts_unmute`.
- **The user is asking a clarifying question, not requesting work**: don't switch modes. Just answer.
- **You don't know the current state**: call `tts_status` once. Don't poll.

## When NOT to self-modulate

- Don't change mode unprompted just because *you* think the work is "boring." The user picks the mode.
- Don't call `tts_speak` directly. The hooks already speak your turns; calling `tts_speak` from your reply would double-narrate.
- Don't change the voice. That's a user preference, not your call.
- Don't `tts_shutdown` unless the user explicitly asks. The daemon outliving the session is intentional.

## When emitting narration blocks

The `codetalker-narration` skill already tells you when and how to write `## Audible <Tag>` blocks. The skill's content is fetched live from the daemon at activation, so the active tag list reflects whatever the user has enabled in the web UI. Trust the skill — don't second-guess which tags exist.
