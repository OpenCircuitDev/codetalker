# Character Texture Validation Runbook

**When to run:** After any GLB regeneration, after any webui rebuild touching CharacterStage, when a user reports "characters appear gray."

## Procedure

1. Confirm renderer config is in source:
   ```bash
   grep -nE 'environment-image|exposure=' core/claude_code_talker/webui/src/components/CharacterStage.tsx
   ```
   Expected: Lines showing `environmentImage="legacy"` and `exposure={...}` around line 329–331.

2. Rebuild:
   ```bash
   cd core/claude_code_talker/webui && npm run build
   ```
   Expected: Build completes in ~15–25s with no errors.

3. Verify dist:
   ```bash
   grep -c 'environment-image' core/claude_code_talker/webui/dist/assets/*.js
   ```
   Expected: At least one match (the renderer JS contains the prop).

4. Restart daemon (`Stop-Process -Id <pid> -Force` on Windows; auto-respawns).

5. Open `http://localhost:17832/ui-react/characters` with hard-refresh (Cmd+Shift+R or Ctrl+Shift+R).

6. For each character: visual check, screenshot to `screenshots/`.

## Failure modes

- **All characters gray** → renderer config not deployed. Re-check Step 2/3.
- **One specific character gray** → that GLB is broken. Open the .glb at
  `http://localhost:17832/api/characters/<cid>/mesh-file` in
  https://gltf-viewer.donmccurdy.com. If gray there too, regenerate via Meshy
  or Hyper3D (`POST /api/mesh-jobs` with `rig: true` per vNext §7.2).
- **Some textures missing, some present** → likely an embedded-vs-separate-textures
  issue in the GLB; regenerate.

## Provider notes

- **Meshy** preview mode (`mesh/meshy.py:33`) ships static unrigged meshes with
  embedded textures. Refine mode adds rig + clips.
- **Hyper3D Rodin** (`mesh/hyper3d.py:35`) ships static unrigged similarly.
- After Phase 2-A, both providers should be invoked with `rig: true` by default.
