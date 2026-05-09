# CCT Phase 25c — Browser-based voice cloning UX

**Status**: approved 2026-05-09 (autonomous overnight build), awaiting user verification.
**Scope**: React dashboard "Characters" tab + character creation wizard with browser-recorded voice cloning. No daemon changes.
**Reference**: parent roadmap entry in [2026-05-08-cct-v1-design.md](./2026-05-08-cct-v1-design.md). Phase 25a foundation already shipped.

## Context

The voice-cloning *backend* is finished (Phases 5 + 14). `/api/voices/clone-from-file` accepts any multipart audio/video, runs ffmpeg + XTTS, returns a usable voice. WhisperX timestamps, voice metadata sidecar, voice CRUD endpoints — all live. What's missing is the *UX*.

Phase 25c is the first user-facing voice cloning experience: a Characters tab in the React dashboard with a 4-step wizard (Identity → Voice source → Preview → Save). Voice source supports browser MediaRecorder, audio upload, video upload (audio extraction handled daemon-side), and "use existing voice" shortcut. The flow is **character-centric** — voices exist as standalone records but the wizard creates them tied to a Character.

## Decisions locked in

- **Top-level tab navigation** in `App.tsx` — `Sessions` tab + new `Characters` tab. `useState<'sessions' | 'characters'>` switch (no URL routing yet).
- **Wizard, not flat form**: 4 steps via `useReducer` inside `<CharacterWizard>` modal.
- **Three voice-source paths in step 2**: record-in-browser, upload audio, upload video, plus "use existing voice" shortcut. All three upload paths converge on `/api/voices/clone-from-file`.
- **MediaRecorder mime fallback chain**: `audio/webm;codecs=opus` → `audio/webm` → `audio/mp4` → `audio/ogg;codecs=opus`. First supported wins; ffmpeg accepts all.
- **Voice CRUD scope in 25c**: list + delete + rename only. Replace-source out of scope.
- **No daemon changes**. Pure frontend + API client work.
- **Persona color mapping** for visual distinction across 6 valid personas.

## Architecture

```
core/claude_code_talker/webui/src/
├── App.tsx                                  # MODIFY — tab nav (Sessions | Characters)
├── api/client.ts                            # MODIFY — voice + character methods
├── types.ts                                 # MODIFY — Voice, Character, NewCharacter, Persona
├── components/
│   ├── TabNav.tsx                           # NEW — minimal tab bar
│   ├── characters/
│   │   ├── CharactersTab.tsx                # NEW — grid + create button
│   │   ├── CharacterCard.tsx                # NEW — one per character
│   │   ├── CharacterWizard.tsx              # NEW — modal, 4-step state machine
│   │   ├── personaColors.ts                 # NEW — persona → tailwind class map
│   │   ├── steps/
│   │   │   ├── IdentityStep.tsx             # NEW
│   │   │   ├── VoiceSourceStep.tsx          # NEW
│   │   │   ├── PreviewStep.tsx              # NEW
│   │   │   └── SaveStep.tsx                 # NEW
│   │   ├── recorder/
│   │   │   ├── BrowserRecorder.tsx          # NEW — MediaRecorder UI
│   │   │   ├── LevelMeter.tsx               # NEW — AnalyserNode bar
│   │   │   └── RecordingTimer.tsx           # NEW — elapsed seconds
│   │   └── VoiceLibraryPicker.tsx           # NEW — list + delete + rename
│   └── ConfirmDialog.tsx                    # NEW
├── hooks/
│   ├── useCharacters.ts                     # NEW — React Query
│   ├── useVoices.ts                         # NEW — React Query
│   ├── useMediaRecorder.ts                  # NEW
│   └── useAudioLevel.ts                     # NEW
└── __tests__/
    ├── CharactersTab.test.tsx
    ├── CharacterWizard.test.tsx
    ├── BrowserRecorder.test.tsx
    ├── VoiceLibraryPicker.test.tsx
    ├── useCharacters.test.tsx
    ├── useVoices.test.tsx
    ├── useMediaRecorder.test.tsx
    └── api-client.test.tsx
```

~14 components, 4 hooks, 8 test files. App.tsx grows by ~15 lines.

## Section 1 — Characters tab + grid

`CharactersTab.tsx` mirrors `SessionGrid` semantically: grid of `CharacterCard`s populated by `useCharacters()`, plus a sticky "New Character" button at top-right opening `<CharacterWizard mode="create" />`. Each card shows display_name, persona badge (color-coded), voice_ref chip, mesh status (none/pending/ready), edit pencil, delete trash icon.

Empty state: "No characters yet. Create one to give a session a custom voice." with primary CTA.

Card visual style mirrors SessionCard: border-l-4 left accent (color from persona), rounded panel.

## Section 2 — Wizard state machine

```ts
type State = {
  step: 'identity' | 'voice' | 'preview' | 'save';
  id: string;                  // derived from display_name (kebab-case)
  display_name: string;
  persona: Persona;            // default 'methodical'
  voiceSource: 'record' | 'audio' | 'video' | 'existing' | null;
  voiceBlob: Blob | null;
  voiceBlobMime: string;
  selectedExistingVoice: string | null;
  voice_ref: string | null;
  uploadStatus: 'idle' | 'uploading' | 'done' | 'error';
  uploadError: string | null;
  previewError: string | null;
};
```

Step gating:
- **Identity**: name required, id auto-slugified, dedupe-checked against existing characters list, persona dropdown
- **Voice source**: 4 paths converging on either `voiceBlob`+upload OR `selectedExistingVoice`. Upload via POST `/api/voices/clone-from-file`. Edit-mode pre-selects "existing" with the character's current voice_ref.
- **Preview**: POST `/api/voices/preview/<voice_ref>` returns audio/wav blob; played via `<audio controls>`. Best-effort — failure doesn't block.
- **Save**: POST `/api/characters` (or PUT for edit). 409 collision bounces back to step 1.

Cancel mid-upload: AbortController. Voice may orphan on daemon if upload completes server-side after client abort — accepted, user can clean up via picker.

Edit mode: prefills steps 1+2, locks id field, starts on step 1, PUT instead of POST.

## Section 3 — BrowserRecorder

Three states: `idle` → `recording` → `done`.

1. Mount: probe `navigator.permissions.query({name:'microphone'})`. If `denied`, show error.
2. Click record: `getUserMedia({audio:true})` → instantiate `MediaRecorder(stream, {mimeType: pickSupportedMime()})` + connect to AnalyserNode for level meter.
3. Recording: `<RecordingTimer max={MAX_S=30}>`. Auto-stop at MAX_S.
4. Click stop: `recorder.stop()` → blob assembled → release stream tracks.
5. State `done`: shows duration, `<audio>` preview via blob URL, "Re-record" button (resets), "Use this take" button (lifts state up).

`useMediaRecorder` hook returns `{state, blob, mimeType, error, start, stop, reset}`.
`useAudioLevel` hook polls AnalyserNode at 30 Hz via rAF, returns `level: number` in [0, 1].

Mime probe order: `audio/webm;codecs=opus`, `audio/webm`, `audio/mp4;codecs=mp4a.40.2`, `audio/ogg;codecs=opus`.

## Section 4 — Voice library picker

`VoiceLibraryPicker.tsx`: list voices from `useVoices()`, per-row rename (PATCH `/api/voices/<name>`) + delete (DELETE with confirm). Cross-reference with `useCharacters()` to show "used by N characters" warning chip on voices currently referenced.

When opened from wizard step 2, picker shows "Use" button per row instead of edit/delete.

## Section 5 — API client extensions

```ts
// webui/src/api/client.ts
listVoices(): Promise<Voice[]>
deleteVoice(name: string): Promise<void>
renameVoice(name: string, newName: string): Promise<Voice>
cloneVoiceFromFile(blob: Blob, opts: {name; filename; start?; end?}, signal?): Promise<{name; voice_path}>
previewVoice(name: string): Promise<Blob>

listCharacters(): Promise<Character[]>
getCharacter(id: string): Promise<Character>
createCharacter(c: NewCharacter): Promise<Character>
updateCharacter(id: string, c: Character): Promise<Character>
deleteCharacter(id: string): Promise<void>
attachCharacter(sessionId: string, characterId: string): Promise<void>
detachCharacter(sessionId: string): Promise<void>
```

`cloneVoiceFromFile` uses `FormData` with `audio` field. `signal` enables AbortController. Filename extension sniffed from MediaRecorder mime (`.webm`/`.mp4`/`.ogg`) or upload type.

## Section 6 — State management

| What | Where |
|---|---|
| Characters list | React Query `['characters']`, `staleTime: 30_000` |
| Voices list | React Query `['voices']`, `staleTime: 30_000` |
| Wizard state | Local `useReducer` |
| Recorder state | Local in `useMediaRecorder` |
| Audio level | Local in `useAudioLevel` (rAF cancelled on unmount) |
| Tab selection | `useState` in `App.tsx` (no persistence) |

## Section 7 — Tests (~16 new)

- `CharactersTab.test.tsx`: empty state, populated grid, delete confirm flow, "New" opens wizard
- `CharacterWizard.test.tsx`: identity step Next gating, auto-slugify, voice-existing path skips upload, voice-upload path triggers fetch, save POSTs character, 409 bounces back
- `BrowserRecorder.test.tsx`: getUserMedia + MediaRecorder mocked; start → recording → onComplete with blob; auto-stop at MAX_S via fake timers; permission-denied path
- `VoiceLibraryPicker.test.tsx`: rename PATCH, delete with cross-ref warning chip
- `useMediaRecorder.test.tsx`: state transitions
- `api-client.test.tsx`: cloneVoiceFromFile FormData shape + AbortController
- `useCharacters.test.tsx` + `useVoices.test.tsx`: query keys + invalidation

MediaRecorder mocked globally in `setup.ts`.

## Section 8 — Implementation phases (12 TDD tasks)

1. Types + API client extensions + api-client.test.tsx
2. `useCharacters` + `useVoices` hooks + tests
3. `TabNav` + App.tsx wiring + empty `CharactersTab`
4. `CharactersTab` + `CharacterCard` (read-only grid) + tests
5. `useMediaRecorder` hook + setup.ts MediaRecorder mock
6. `useAudioLevel` hook
7. `BrowserRecorder` component (composes hooks + timer + meter)
8. `VoiceLibraryPicker`
9. `CharacterWizard` shell + `IdentityStep`
10. `VoiceSourceStep` (4 paths integrated)
11. `PreviewStep` + `SaveStep`
12. Edit-mode flow + delete-character cascade UX polish

Tasks 1–4 establish scaffolding without MediaRecorder risk. 5–7 isolate browser API. 8 unblocks step 2's existing path. 9–11 build wizard incrementally. 12 closes loop.

## Risks / open questions

- **MediaRecorder Safari support**: only `audio/mp4`. Mime fallback chain handles. Old browsers fail; render error pointing at upload-file path.
- **Codec → ffmpeg compat**: confirmed safe; `clone_from_local_file` uses ffmpeg auto-detect.
- **Permission denied**: no re-prompt path — instructions point at browser settings.
- **File size**: soft client-side limit 100MB. Larger files warn but upload.
- **Voice deletion while attached**: cfg merge tolerates dangling refs (Phase 25a). Picker warns with "used by N characters" chip; allow.
- **Concurrency on /api/voices**: daemon's `sanitize_voice_name` collision-resolves with `-2/-3` suffixes; wizard uses `response.name` (not requested name).
- **Tab nav + URL**: hard-coded `useState` defers URL routing. One-task refactor when needed.
- **Persona color palette**: methodical=slate, warm=amber, technical=cyan, plain=zinc, sarcastic=fuchsia, energetic=rose. Subjective; tweakable in `personaColors.ts`.

## Out of scope

- Wizard for trimming long source files (uses `preview-extract` — future polish phase)
- Replace-source / re-clone (delete + re-record covers it)
- Install-dependencies UI (daemon auto-installs)
- React-native voice CRUD beyond list/rename/delete
- 3D mesh integration (Phase 25b lands first; Phase 27 surfaces avatars)
- Attach character to session from CharacterCard (REST endpoint exists; UI defers to Phase 27)

## Verification

1. `npm test` in webui — all 9 existing + ~16 new pass
2. `npm run build` — no TS errors
3. `pytest core/tests/` — 906+ existing stay green (no daemon changes)
4. Manual end-to-end: open `/ui-react/`, switch to Characters tab, create New Character, record 6 sec via mic, hear preview synthesized in own voice, save → file at `~/.claude/scripts/codetalker/characters/<id>.yaml` and reference WAV at voice-cloner storage location
5. Manual: edit character (change persona), save; cfg merge picks up new persona on next narration
6. Manual: delete a voice referenced by a character; UI shows "voice missing" warning, cfg falls back to global

## Success criteria

A user can record their voice in the browser, hear a preview synthesized in their voice, and save it as a Character — without leaving the dashboard or touching the legacy UI. All four voice-source paths work. Voice library CRUD reachable from Characters tab.
