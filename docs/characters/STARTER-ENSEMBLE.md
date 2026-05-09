# Starter Character Ensemble

Three characters generated end-to-end on the live Meshy v2 API as part of Phase 25b verification (2026-05-09). They span the persona axis useful for codetalker dev narration: **methodical** for ceremonial moments, **warm** for general-purpose, **energetic** for celebratory moments.

## Roster

| ID | Display name | Persona | Mesh size | Generation time | Use it for |
|---|---|---|---|---|---|
| [`smoke-meshy`](#smoke-meshy) | Smoke Meshy | warm | 8.6 MB | 55s | The original smoke test character — keep or delete |
| [`dr-crow`](#dr-crow) | Dr. Crow | methodical | 13.8 MB | 50s | Test runs starting, careful announcements, deploy ceremonies |
| [`spark`](#spark) | Spark | energetic | 8.1 MB | 30s | Tests passing, builds succeeding, fast-paced live narration |

All three have:
- A persisted YAML record at `~/.claude/scripts/codetalker/characters/<id>.yaml`
- A GLB at `~/.claude/scripts/codetalker/models/<id>/<job_id>.glb`
- A placeholder `voice_ref` of `char-<id>` (Phase 25c stub clone) — overwrite with a real voice when you're ready
- `mesh_provider="meshy"` and `mesh_prompt` retained, so you can re-roll variations against the same provider

---

## Smoke Meshy

- **id:** `smoke-meshy`
- **persona:** warm
- **mesh:** `~/.claude/scripts/codetalker/models/smoke-meshy/9258e26eca36.glb`
- **prompt:** `low-poly stylized cyan robot wizard, expressive eyes, friendly`
- **role hint:** general-purpose narrator, the "default voice." Disposable if you'd rather not keep the smoke test artifact around.

---

## Dr. Crow

- **id:** `dr-crow`
- **persona:** methodical
- **mesh:** `~/.claude/scripts/codetalker/models/dr-crow/c7e0adf29c09.glb`
- **prompt:** `low-poly stylized scholar raven, half-moon spectacles, dark academic robe, calm pose, perched on a stack of books`
- **role hint:** ceremonial moments — "starting test run", "preparing release", end-of-day summaries. Match with a slow, deliberate voice (e.g., a Piper voice in `low` quality with a longer cadence). Methodical persona pairs naturally with the academic raven aesthetic.

---

## Spark

- **id:** `spark`
- **persona:** energetic
- **mesh:** `~/.claude/scripts/codetalker/models/spark/8eda3c12f7d2.glb`
- **prompt:** `low-poly stylized firefly imp, glowing teal and gold tail, dynamic flying pose, mischievous grin, tiny wings`
- **role hint:** celebratory moments — "all tests passing", "build succeeded", "deploy went green". Match with a bright, high-energy voice and a fast cadence. The firefly's glow makes it visually distinctive on a SessionCard avatar (Phase 27 persona-gradient mapping picks a rose-orange ring for energetic).

---

## Why these three

The three characters were chosen to cover the codetalker dev workflow's emotional range:

```
calm / ceremonial  ──────  warm / general  ──────  bright / celebratory
   methodical                  warm                    energetic
   Dr. Crow                Smoke Meshy                  Spark
```

This gives you obvious choices for tonal switching mid-session: detach Dr. Crow before a build run, attach Spark when it goes green. Phase 25c's `attach-character` endpoint makes this a one-click dashboard action.

## Replicating or extending

To roll a new character against Meshy with the same flow:

```bash
curl -X POST http://127.0.0.1:17832/api/characters \
  -H "Content-Type: application/json" \
  -d '{"id":"<id>","display_name":"<name>","voice_ref":"char-<id>","persona":"<persona>"}'

curl -X POST http://127.0.0.1:17832/api/mesh-jobs \
  -H "Content-Type: application/json" \
  -d '{"character_id":"<id>","provider":"meshy","prompt":"<your prompt>"}'

# Poll until terminal:
curl -X POST http://127.0.0.1:17832/api/mesh-jobs/<job_id>/poll
```

Or use the dashboard: **Characters tab → + New** for the wizard, then **MeshGenerator** in the detail pane to add the avatar.

## Tips for prompts that work well on Meshy preview mode

Meshy's preview mode (the default in this build) generates fast (~30–60s) low-to-medium-poly stylized meshes. From the three jobs we ran, prompts that landed cleanly shared a few traits:

- **Lead with style** — "low-poly stylized" or "low-poly minimalist" anchors Meshy's default art style.
- **Concrete subject** — "scholar raven" beats "wise bird"; "firefly imp" beats "magical creature."
- **Two or three distinguishing details** — accessories (spectacles, robe), pose (perched, flying), color hints (teal and gold).
- **Skip cinematic terms** — "8K", "photorealistic", "ray-traced" don't help in preview mode and may hurt style adherence.

The `mesh_prompt_history` on each Character record retains every prompt you've sent for that character, so you can iterate on phrasings without losing context.
