# Character Emotive States — v0.1.0 catalog

The canonical set of states the CharacterStage reacts to. Each state is
triggered by daemon signals (hook events, narration content, session
flags) and produces a coordinated visual reaction across **camera /
lighting / glow / future facial morph** layers.

Designed for **Path C** (talking-head + facial rig) — the visual
vocabulary works on any character form (humanoid, crow, abstract) so we
don't need every character to be rigged identically. When facial morphs
land later, they slot into the `morphs` column without touching the
trigger or camera/lighting wiring.

## Trigger priority (top of list wins when multiple fire)

1. **alerted** — interrupts everything; user attention urgently needed
2. **speaking** — character is the audio source right now
3. **listening** — user is the audio source / typing right now
4. **questioning / researching / working / thinking / confirming /
   concluding** — task-state palette, equal priority (most recent wins)
5. **idle** — default

States 1–3 are **sticky** (held while the trigger is active). States 4 are **transient** (held for `durationMs`, then return to idle).

---

## State catalog

### `idle`
- **When**: no other state active.
- **Trigger**: default fallback.
- **Duration**: ∞ until another state preempts.
- **Camera**: persona-base orbit + 32s sinusoidal drift (Tier 1).
- **Lighting**: persona-base exposure.
- **Glow**: none.
- **Background tint**: persona gradient (Tier 1).
- **Morphs (future)**: neutral; subtle blink loop every 3-5s.
- **Verbal flavor**: ambient — no narration tone implied.
- **Per-state mesh prompt** (if we ever generate a state-specific clip): *"calm neutral pose, eyes forward, mouth closed, gentle breathing"*.

### `listening`
- **When**: user is providing input — typing in CC, or speaking through the AR companion.
- **Trigger**: `session.last_user_interaction_at` is within the last 5s.
- **Duration**: held while the recency window is fresh; falls back to `idle` after.
- **Camera**: lean **toward** the viewer 8°, slight zoom-in (radius 95%).
- **Lighting**: +15% exposure (brighter, alert).
- **Glow**: subtle cool blue rim glow.
- **Background tint**: persona gradient + cool blue overlay 10%.
- **Morphs (future)**: head tilt slightly forward, eyes wide, brows neutral, mouth slightly open as if anticipating.
- **Verbal flavor**: silent (character isn't speaking — character is hearing).
- **Per-state mesh prompt**: *"attentive forward-leaning pose, eyes wide and engaged, ears alert, mouth slightly parted as if about to respond"*.

### `speaking`
- **When**: daemon's TTS is producing audio for this session.
- **Trigger**: `session.is_speaking === true`.
- **Duration**: held while speaking; falls back to whichever state had recent activity otherwise.
- **Camera**: persona-base orbit, accelerated auto-rotate (+30% rotation/sec).
- **Lighting**: +10% exposure.
- **Glow**: cyan pulse (1.2s cycle, matches Tier 1 speak-pulse keyframe).
- **Background tint**: persona gradient + cyan overlay 12%.
- **Morphs (future)**: jaw open amplitude driven by audio analyzer, occasional brow lift on emphasis. Blink suppressed.
- **Verbal flavor**: present-tense narration; whatever the LLM emits.
- **Per-state mesh prompt**: *"expressive mid-sentence pose, mouth open mid-speech, eyes engaged with viewer, slight forward gesture"*.

### `researching`
- **When**: Claude Code is reading files / running searches.
- **Trigger**: `PreToolUse` hook fires with tool name in `{Read, Grep, Glob, WebFetch, WebSearch, ToolSearch}`.
- **Duration**: 2.5s, then idle (or override by next trigger).
- **Camera**: orbit shifts 25° to the side as if "looking at something off-screen", radius pulls back to 115%.
- **Lighting**: -5% exposure (slightly dimmer, focused).
- **Glow**: warm amber rim.
- **Background tint**: persona gradient + amber overlay 8%.
- **Morphs (future)**: eyes narrowed, head tilted in concentration, mouth closed.
- **Verbal flavor**: implies "let me look this up..." — narration might mention what's being read.
- **Per-state mesh prompt**: *"studious focused pose, head tilted reading, eyes narrowed examining something off to the side, scholarly posture"*.

### `working`
- **When**: Claude Code is producing output / running commands.
- **Trigger**: `PreToolUse` hook fires with tool name in `{Edit, Write, Bash, NotebookEdit, MultiEdit}`.
- **Duration**: 2.5s, then idle.
- **Camera**: tighter zoom (radius 95%), orbit centered, no drift jitter.
- **Lighting**: neutral persona base, +5% saturation.
- **Glow**: warm green rim (active production).
- **Background tint**: persona gradient + green overlay 8%.
- **Morphs (future)**: brow furrowed in concentration, eyes downward as if focusing on hands/work.
- **Verbal flavor**: action-tense — "writing the function...", "applying the fix...".
- **Per-state mesh prompt**: *"focused working pose, eyes downward at task, mouth set in concentration, hands implied to be active"*.

### `questioning`
- **When**: the character would naturally ask something.
- **Trigger primary**: narration LLM emits an `<emote name="question">` tag (Path 1, future).
- **Trigger fallback**: narration chunk text ends with `?` or matches `^(Why|What|How|When|Where|Should|Can)` (text-shape inference, Path 2).
- **Trigger event-driven**: `Notification` hook with a question-style message.
- **Duration**: 3s.
- **Camera**: head tilt — orbit shifts 12° to one side AND phi tilts up 6° (looking up + sideways).
- **Lighting**: +5% exposure.
- **Glow**: violet rim.
- **Background tint**: persona gradient + violet overlay 10%.
- **Morphs (future)**: eyebrow raise (single brow if rig supports asymmetric), mouth slightly open, head tilt.
- **Verbal flavor**: rising intonation; "...?" sentences.
- **Per-state mesh prompt**: *"inquiring head-tilt pose, one eyebrow raised, mouth slightly open mid-question, curious expression"*.

### `thinking`
- **When**: between tool events; idle but not yet conclusive.
- **Trigger**: `PostToolUse` followed by no further hooks within 2s, OR a long pause in narration-stream.
- **Duration**: 3s decay.
- **Camera**: orbit drifts up + outward (phi tilts up 10°, radius 115%), as if "looking off into the distance".
- **Lighting**: -15% exposure (dimmer, contemplative).
- **Glow**: muted lavender.
- **Background tint**: persona gradient + lavender overlay 6%.
- **Morphs (future)**: eyes upward, brow slightly furrowed, mouth closed, slight head turn.
- **Verbal flavor**: hesitation markers — "hmm", "let me think", trailing off.
- **Per-state mesh prompt**: *"contemplative pose, eyes gazing upward in thought, hand implied at chin, soft pondering expression"*.

### `confirming`
- **When**: a step succeeded; positive resolution.
- **Trigger primary**: narration emits `<emote name="confirm">`.
- **Trigger fallback**: narration text contains `^(Done|Confirmed|Success|Fixed|Solved|Working|Green)\b` OR `PostToolUse` with `result: "ok"` style indication.
- **Duration**: 2s.
- **Camera**: slight forward nudge (radius 100%), centered orbit.
- **Lighting**: +20% exposure (bright/affirmative).
- **Glow**: soft green pulse (1s).
- **Background tint**: persona gradient + green overlay 12%.
- **Morphs (future)**: soft smile, slight nod, eyes meet viewer.
- **Verbal flavor**: declarative affirmative — "Done.", "Confirmed.".
- **Per-state mesh prompt**: *"satisfied nodding pose, gentle smile, eyes meeting viewer, calm affirming expression"*.

### `concluding`
- **When**: end of a session phase / task.
- **Trigger**: `Stop` hook fires; OR narration emits `<emote name="conclude">`.
- **Duration**: 3s before returning to idle.
- **Camera**: pulls back to wide (radius 130%), centered orbit, halt rotation.
- **Lighting**: persona base, soft fade.
- **Glow**: warm amber rim (sunset-y).
- **Background tint**: persona gradient + amber overlay 8%.
- **Morphs (future)**: eyes relaxed half-closed, mouth slight upward curve, body relaxed.
- **Verbal flavor**: summary/wrap-up — "All set.", "Wrapping up.".
- **Per-state mesh prompt**: *"settled concluding pose, eyes relaxed, mouth gently closed in satisfaction, body language at ease"*.

### `alerted`
- **When**: error, warning, unexpected outcome that needs user attention.
- **Trigger primary**: `Notification` hook fires with severity >= warning.
- **Trigger fallback**: narration text matches `^(Error|Failed|Broken|Stuck|Help|Wait|Stop)\b` or contains `\bERROR\b`.
- **Duration**: 2.5s; then returns to whatever state had been active before.
- **Camera**: rapid jitter — small theta oscillation ±8° for 600ms, then settle to centered orbit.
- **Lighting**: +25% exposure (urgent flash).
- **Glow**: red rim, 0.6s pulse.
- **Background tint**: persona gradient + red overlay 15%.
- **Morphs (future)**: eyes wide, brows up, mouth slightly open in surprise/alarm.
- **Verbal flavor**: imperative — "Heads up.", "Caught an error.".
- **Per-state mesh prompt**: *"alert wide-eyed pose, eyebrows raised in concern, mouth open as if about to warn, posture forward and tense"*.

---

## Source signals (current daemon surface)

The state machine subscribes to / polls these:

| Signal | Source | Refresh |
|---|---|---|
| `session.is_speaking` | `/api/sessions` | 5s poll |
| `session.last_user_interaction_at` | (need to expose on /api/sessions — currently in-memory only) | 5s poll |
| `session.last_modified` | `/api/sessions` | 5s poll |
| Narration text chunks | `/api/narration-stream` SSE | push (immediate) |
| Hook event type (PreToolUse, PostToolUse, Stop, Notification, UserPromptSubmit) | (need to expose on narration-stream as event metadata — currently only narration text is streamed) | push |
| Tool name (within PreToolUse) | (same — needs daemon to surface) | push |

**Daemon gaps for full Tier 2:**

1. `last_user_interaction_at` not on `/api/sessions` response. Add to list_sessions handler.
2. Hook event type + tool name not on narration-stream. Extend the SSE payload schema to include `{type: "PreToolUse", tool: "Read"}` etc. so the webui can react to events even when no narration is emitted.

Both are small additions. Until they land, Tier 2 runs in **inference mode** — derives state from `is_speaking`, `last_modified` deltas, and narration text content alone.

---

## Per-character per-state mesh prompts (Meshy hint catalog)

If/when we generate per-state mesh variants (Path A territory, not Path C), the **Per-state mesh prompt** entries above feed directly into Meshy's text-to-3D or image-to-3D refine prompts. For Dr. Crow specifically, prepend `"stylized scholar crow, dark academic robe, half-moon spectacles, perched, "` to each state's prompt so the visual identity stays consistent across the cast.

For the **default Refine pass** (Path C texture step), use a single prompt:

> *"stylized scholar crow with iridescent black feathers, half-moon golden spectacles, deep navy academic robe with subtle bronze trim, intelligent eyes, soft volumetric lighting, painterly textures"*

This gives Meshy enough detail to produce a richly textured base mesh that all the emotive states will share.

---

## Implementation phases

- **Phase 1 (this iteration)**: hook events → state machine → camera/lighting/glow reactions (no facial morphs). Works on any mesh, textured or not.
- **Phase 2**: Meshy refine pass for textures (daemon endpoint), then character meshes finally look right per the prompt.
- **Phase 3**: Meshy facial-rig pass for the standard morph set (mouth, blink, brow). State machine starts driving morphs.
- **Phase 4**: TTS amplitude → mouth-open morph (cheap lip-sync without phoneme timing).
- **Phase 5**: Narration LLM emits `<emote>` tags in addition to text, replacing the text-shape inference fallback with explicit semantic markers.

Phases 2-5 are each independent ship-points; the state machine works through all of them with just additional output channels wired in.
