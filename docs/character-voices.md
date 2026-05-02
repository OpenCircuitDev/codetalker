# Character voice recipes

Below are starter recipes for cloning the three character voices the project's
brainstorming session settled on (Marvin the Paranoid Android, Strong Bad,
Deep Thought) using the `voice-cloner` sub-project. Each command picks a
clean ~12-second segment with minimal background noise. Adjust `--start` if
the source video has been re-uploaded or trimmed.

## Marvin the Paranoid Android (2005 film, Alan Rickman)

```
claude-code-talker-voice-cloner from-youtube \
    --url <find a clean Marvin scene clip> \
    --start 0:18 \
    --duration 12 \
    --name marvin
```

Look for the "Brain the size of a planet" or "Life. Don't talk to me about life"
scenes. Avoid clips with background music or other character dialogue.

## Strong Bad (Homestar Runner)

```
claude-code-talker-voice-cloner from-youtube \
    --url <Strong Bad email clip> \
    --start 0:30 \
    --duration 12 \
    --name strong-bad
```

Mike Chapman's voice is consistent across most Strong Bad emails. Prefer
clips where Strong Bad speaks alone (not Homestar dialogue).

## Deep Thought (2005 film, Helen Mirren)

```
claude-code-talker-voice-cloner from-youtube \
    --url <Deep Thought scene clip> \
    --start 0:45 \
    --duration 14 \
    --name deep-thought
```

Mirren's "I am Deep Thought" reveal scene works well. Slow, sonorous, low
register — ideal for cloning.

## Tips

- Clean reference matters more than length. 10s of solo voice beats 30s with music.
- XTTS-v2 captures timbre and accent well. Prosodic quirks (Marvin's sighs,
  Strong Bad's nasal exclamations) are harder.
- Test the clone with `tts_speak` before relying on it: pick the engine,
  voice, and a sentence; listen and decide.
- After cloning, set the workspace config:
  ```yaml
  voice:
    engine: xtts
    model: marvin     # the --name you used
    rate: 1.0
  ```
- XTTS-v2 first-call latency is significant: the model (~1.5GB) downloads to
  `~/.local/share/tts/` on first synthesize. Subsequent calls are model-loaded.
- Without GPU/CUDA, expect 3-8 seconds per ~10-word phrase. Mode C (live
  narration) becomes unusable on CPU. Mode B (brief, end-of-turn) is fine.

## Legal note

Voice cloning of fictional characters is a gray area. Personal use for your
own listening is generally accepted. Distribution, public release, or
commercial use of cloned voices may infringe on rights of personality,
copyright on the source recording, or platform Terms of Service. You are
responsible for what you generate.
