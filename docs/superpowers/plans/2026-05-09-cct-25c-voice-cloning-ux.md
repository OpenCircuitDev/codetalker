# CCT Phase 25c — Voice Cloning UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Characters tab in the React dashboard with a 4-step wizard (Identity → Voice source → Preview → Save) that lets users record/upload voice samples, kick off cloning, and attach the resulting Character to a session.

**Architecture:** New `core/claude_code_talker/webui/src/features/characters/` directory. The Characters tab itself is a route panel inside the existing dashboard layout. State machine via React `useReducer`; persistence via existing REST + the new `POST /api/characters/{id}/clone-voice` endpoint. `BrowserRecorder.tsx` wraps `MediaRecorder` with a mime fallback chain (webm → mp4 → wav). All Characters list state hydrates via React Query.

**Tech Stack:** React 19, TypeScript, Vite 6, Tailwind v4, framer-motion (already on package.json), `@tanstack/react-query` (already on package.json), `react-hook-form` for the wizard form, browser `MediaRecorder` API.

**Reference spec:** [docs/superpowers/specs/2026-05-09-cct-25c-voice-cloning-ux-design.md](../specs/2026-05-09-cct-25c-voice-cloning-ux-design.md) — read before starting.

**File structure**:
```
core/claude_code_talker/webui/src/features/characters/
├── CharactersTab.tsx             # NEW — top-level tab pane
├── CharactersList.tsx            # NEW — left rail of characters
├── CharacterDetail.tsx           # NEW — right pane with persona, voice, mesh hooks
├── CreateCharacterWizard.tsx     # NEW — 4-step modal
├── BrowserRecorder.tsx           # NEW — MediaRecorder wrapper component
├── PersonaBadge.tsx              # NEW — color-mapped chip
├── characters.api.ts             # NEW — fetch helpers (list/create/clone-voice/attach)
├── characters.types.ts           # NEW — Character, WizardState, VoiceSource types
└── wizardReducer.ts              # NEW — useReducer state machine

core/claude_code_talker/webui/src/components/
└── DashboardShell.tsx            # MODIFY — register Characters tab in nav

core/claude_code_talker/
├── api.py                        # MODIFY — POST /api/characters/{id}/clone-voice
└── voice/cloning_jobs.py         # NEW — in-process tracker shim (Phase 25b reuses)

core/tests/
├── test_api_clone_voice.py       # NEW — 4 tests
└── test_voice_cloning_jobs.py    # NEW — 6 tests
```

---

## Task 1: Frontend types + API helpers (no UI yet)

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/characters.types.ts`
- Create: `core/claude_code_talker/webui/src/features/characters/characters.api.ts`

- [ ] **Step 1: Write the type contract**

Create `characters.types.ts`:

```typescript
export type Persona =
  | "methodical" | "warm" | "technical"
  | "plain" | "sarcastic" | "energetic";

export type VoiceSource =
  | { kind: "library"; voiceId: string }
  | { kind: "recording"; blob: Blob; mimeType: string }
  | { kind: "upload"; file: File };

export interface Character {
  id: string;
  display_name: string;
  voice_ref: string;
  persona: Persona | null;
  mesh_path: string | null;
  mesh_provider: string | null;
  mesh_prompt: string | null;
  created_at: number;
  updated_at: number;
}

export interface VoiceLibraryEntry {
  voice_id: string;
  engine: string;
  display_name: string;
  language: string;
}

export interface CloneVoiceJob {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  voice_ref?: string;
  error?: string;
}

export interface WizardState {
  step: 1 | 2 | 3 | 4;
  identity: { id: string; display_name: string; persona: Persona | null };
  voiceSource: VoiceSource | null;
  cloneJob: CloneVoiceJob | null;
  preview: { audioUrl: string | null; isPlaying: boolean };
  saving: boolean;
  error: string | null;
}
```

- [ ] **Step 2: Write the fetch helpers**

Create `characters.api.ts`:

```typescript
import type { Character, CloneVoiceJob, VoiceLibraryEntry } from "./characters.types";

const base = "";  // same-origin

export async function listCharacters(): Promise<Character[]> {
  const r = await fetch(`${base}/api/characters`);
  if (!r.ok) throw new Error(`listCharacters: ${r.status}`);
  return r.json();
}

export async function createCharacter(input: {
  id: string;
  display_name: string;
  voice_ref: string;
  persona: string | null;
}): Promise<Character> {
  const r = await fetch(`${base}/api/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`createCharacter: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function listVoices(): Promise<VoiceLibraryEntry[]> {
  const r = await fetch(`${base}/api/voices`);
  if (!r.ok) throw new Error(`listVoices: ${r.status}`);
  return r.json();
}

export async function cloneVoice(
  characterId: string,
  audioBlob: Blob,
  mimeType: string,
): Promise<CloneVoiceJob> {
  const fd = new FormData();
  fd.append("audio", audioBlob, `sample.${mimeType.split("/")[1] || "webm"}`);
  fd.append("mime_type", mimeType);
  const r = await fetch(`${base}/api/characters/${characterId}/clone-voice`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) throw new Error(`cloneVoice: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getCloneVoiceJob(jobId: string): Promise<CloneVoiceJob> {
  const r = await fetch(`${base}/api/voice-clone-jobs/${jobId}`);
  if (!r.ok) throw new Error(`getCloneVoiceJob: ${r.status}`);
  return r.json();
}

export async function attachCharacter(sessionId: string, characterId: string): Promise<void> {
  const r = await fetch(`${base}/api/sessions/${sessionId}/attach-character`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ character_id: characterId }),
  });
  if (!r.ok) throw new Error(`attachCharacter: ${r.status} ${await r.text()}`);
}

export async function detachCharacter(sessionId: string): Promise<void> {
  const r = await fetch(`${base}/api/sessions/${sessionId}/character`, { method: "DELETE" });
  if (!r.ok) throw new Error(`detachCharacter: ${r.status}`);
}
```

- [ ] **Step 3: Type-check passes**

Run: `cd core/claude_code_talker/webui && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/characters.types.ts core/claude_code_talker/webui/src/features/characters/characters.api.ts
git commit -m "feat(webui): characters feature types + API client (Phase 25c Task 1)"
```

---

## Task 2: Wizard reducer (TDD with vitest)

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/wizardReducer.ts`
- Create: `core/claude_code_talker/webui/src/features/characters/wizardReducer.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
import { describe, expect, it } from "vitest";
import { initialWizardState, wizardReducer } from "./wizardReducer";

describe("wizardReducer", () => {
  it("starts at step 1", () => {
    expect(initialWizardState.step).toBe(1);
  });

  it("advances to step 2 on IDENTITY_SUBMIT", () => {
    const next = wizardReducer(initialWizardState, {
      type: "IDENTITY_SUBMIT",
      identity: { id: "buddy", display_name: "Buddy", persona: "warm" },
    });
    expect(next.step).toBe(2);
    expect(next.identity.id).toBe("buddy");
  });

  it("rejects empty id", () => {
    const next = wizardReducer(initialWizardState, {
      type: "IDENTITY_SUBMIT",
      identity: { id: "", display_name: "X", persona: null },
    });
    expect(next.step).toBe(1);
    expect(next.error).toMatch(/id/i);
  });

  it("VOICE_SOURCE_SET advances to step 3", () => {
    const s2 = wizardReducer(initialWizardState, {
      type: "IDENTITY_SUBMIT",
      identity: { id: "x", display_name: "X", persona: null },
    });
    const next = wizardReducer(s2, {
      type: "VOICE_SOURCE_SET",
      source: { kind: "library", voiceId: "en_US-amy-medium" },
    });
    expect(next.step).toBe(3);
    expect(next.voiceSource?.kind).toBe("library");
  });

  it("CLONE_JOB_UPDATED transitions success to step 4", () => {
    const s = { ...initialWizardState, step: 3 as const };
    const next = wizardReducer(s, {
      type: "CLONE_JOB_UPDATED",
      job: { job_id: "j1", status: "succeeded", voice_ref: "char-buddy" },
    });
    expect(next.step).toBe(4);
  });

  it("CLONE_JOB_UPDATED failure stays on step 3 with error", () => {
    const s = { ...initialWizardState, step: 3 as const };
    const next = wizardReducer(s, {
      type: "CLONE_JOB_UPDATED",
      job: { job_id: "j1", status: "failed", error: "boom" },
    });
    expect(next.step).toBe(3);
    expect(next.error).toBe("boom");
  });

  it("BACK rewinds one step", () => {
    const s = { ...initialWizardState, step: 3 as const };
    expect(wizardReducer(s, { type: "BACK" }).step).toBe(2);
    expect(wizardReducer(initialWizardState, { type: "BACK" }).step).toBe(1);
  });
});
```

- [ ] **Step 2: Implement reducer**

```typescript
import type { CloneVoiceJob, Persona, VoiceSource, WizardState } from "./characters.types";

export const initialWizardState: WizardState = {
  step: 1,
  identity: { id: "", display_name: "", persona: null },
  voiceSource: null,
  cloneJob: null,
  preview: { audioUrl: null, isPlaying: false },
  saving: false,
  error: null,
};

export type WizardAction =
  | { type: "IDENTITY_SUBMIT"; identity: { id: string; display_name: string; persona: Persona | null } }
  | { type: "VOICE_SOURCE_SET"; source: VoiceSource }
  | { type: "CLONE_JOB_UPDATED"; job: CloneVoiceJob }
  | { type: "PREVIEW_AUDIO_READY"; url: string }
  | { type: "PREVIEW_PLAYING"; isPlaying: boolean }
  | { type: "SAVE_START" }
  | { type: "SAVE_DONE" }
  | { type: "SAVE_ERROR"; error: string }
  | { type: "BACK" }
  | { type: "RESET" };

const isKebabId = (s: string) => /^[a-z][a-z0-9-]*$/.test(s);

export function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "IDENTITY_SUBMIT": {
      const { id, display_name, persona } = action.identity;
      if (!isKebabId(id)) return { ...state, error: "id must be kebab-case (lowercase, dashes)" };
      if (!display_name.trim()) return { ...state, error: "display name required" };
      return { ...state, step: 2, identity: { id, display_name, persona }, error: null };
    }
    case "VOICE_SOURCE_SET":
      return { ...state, step: 3, voiceSource: action.source, error: null };
    case "CLONE_JOB_UPDATED":
      if (action.job.status === "succeeded") return { ...state, step: 4, cloneJob: action.job, error: null };
      if (action.job.status === "failed") return { ...state, cloneJob: action.job, error: action.job.error ?? "clone failed" };
      return { ...state, cloneJob: action.job };
    case "PREVIEW_AUDIO_READY":
      return { ...state, preview: { audioUrl: action.url, isPlaying: false } };
    case "PREVIEW_PLAYING":
      return { ...state, preview: { ...state.preview, isPlaying: action.isPlaying } };
    case "SAVE_START":
      return { ...state, saving: true, error: null };
    case "SAVE_DONE":
      return initialWizardState;
    case "SAVE_ERROR":
      return { ...state, saving: false, error: action.error };
    case "BACK":
      if (state.step === 1) return state;
      return { ...state, step: (state.step - 1) as WizardState["step"], error: null };
    case "RESET":
      return initialWizardState;
  }
}
```

- [ ] **Step 3: Tests pass**

Run: `cd core/claude_code_talker/webui && npx vitest run wizardReducer`
Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/wizardReducer.ts core/claude_code_talker/webui/src/features/characters/wizardReducer.test.ts
git commit -m "feat(webui): wizard reducer state machine (Phase 25c Task 2)"
```

---

## Task 3: PersonaBadge component

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/PersonaBadge.tsx`

- [ ] **Step 1: Implement**

```tsx
import type { Persona } from "./characters.types";

const PERSONA_COLORS: Record<Persona, string> = {
  methodical: "bg-slate-700 text-slate-100",
  warm: "bg-amber-700 text-amber-100",
  technical: "bg-cyan-700 text-cyan-100",
  plain: "bg-zinc-700 text-zinc-100",
  sarcastic: "bg-fuchsia-700 text-fuchsia-100",
  energetic: "bg-rose-700 text-rose-100",
};

export function PersonaBadge({ persona }: { persona: Persona | null }) {
  if (!persona) return <span className="text-zinc-500 text-xs italic">no persona</span>;
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${PERSONA_COLORS[persona]}`}>
      {persona}
    </span>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd core/claude_code_talker/webui && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/PersonaBadge.tsx
git commit -m "feat(webui): PersonaBadge with persona-color mapping (Phase 25c Task 3)"
```

---

## Task 4: BrowserRecorder component

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/BrowserRecorder.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useEffect, useRef, useState } from "react";

const MIME_FALLBACK = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/wav",
];

function pickMime(): string {
  for (const m of MIME_FALLBACK) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

interface Props {
  onRecorded: (blob: Blob, mimeType: string) => void;
  maxSeconds?: number;
}

export function BrowserRecorder({ onRecorded, maxSeconds = 30 }: Props) {
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const tickRef = useRef<number | null>(null);

  useEffect(() => () => stopAll(), []);

  function stopAll() {
    if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (recRef.current && recRef.current.state !== "inactive") recRef.current.stop();
    recRef.current = null;
  }

  async function start() {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickMime();
      const opts = mime ? { mimeType: mime } : undefined;
      const rec = new MediaRecorder(stream, opts);
      recRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || mime || "audio/webm" });
        onRecorded(blob, rec.mimeType || mime || "audio/webm");
        stopAll();
        setRecording(false);
        setElapsed(0);
      };
      rec.start();
      setRecording(true);
      tickRef.current = window.setInterval(() => {
        setElapsed((s) => {
          if (s + 1 >= maxSeconds) { stop(); return s + 1; }
          return s + 1;
        });
      }, 1000);
    } catch (e: any) {
      setError(e?.message || "microphone access denied");
    }
  }

  function stop() {
    if (recRef.current && recRef.current.state !== "inactive") recRef.current.stop();
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {!recording ? (
          <button onClick={start} className="px-3 py-1 bg-rose-600 text-white rounded">Record</button>
        ) : (
          <button onClick={stop} className="px-3 py-1 bg-zinc-600 text-white rounded">Stop</button>
        )}
        <span className="text-sm text-zinc-400">{elapsed}s / {maxSeconds}s</span>
      </div>
      {error && <p className="text-rose-400 text-sm">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Manual smoke**

Mount `<BrowserRecorder onRecorded={(blob, mt) => console.log(blob.size, mt)} />` in a sandbox page and verify clicking Record streams 1-second ticks and produces a blob on Stop.

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/BrowserRecorder.tsx
git commit -m "feat(webui): BrowserRecorder with mime fallback (Phase 25c Task 4)"
```

---

## Task 5: CreateCharacterWizard skeleton

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/CreateCharacterWizard.tsx`

- [ ] **Step 1: Implement 4-step wizard skeleton**

```tsx
import { useReducer } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { initialWizardState, wizardReducer } from "./wizardReducer";
import { BrowserRecorder } from "./BrowserRecorder";
import { cloneVoice, createCharacter, listVoices } from "./characters.api";
import type { Persona } from "./characters.types";

const PERSONA_OPTIONS: Persona[] = ["methodical", "warm", "technical", "plain", "sarcastic", "energetic"];

export function CreateCharacterWizard({ onClose }: { onClose: () => void }) {
  const [state, dispatch] = useReducer(wizardReducer, initialWizardState);
  const qc = useQueryClient();

  const saveMutation = useMutation({
    mutationFn: async () => {
      dispatch({ type: "SAVE_START" });
      const voiceRef = state.cloneJob?.voice_ref ?? (state.voiceSource?.kind === "library" ? state.voiceSource.voiceId : "");
      if (!voiceRef) throw new Error("no voice ref");
      await createCharacter({
        id: state.identity.id,
        display_name: state.identity.display_name,
        voice_ref: voiceRef,
        persona: state.identity.persona,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["characters"] });
      dispatch({ type: "SAVE_DONE" });
      onClose();
    },
    onError: (e: Error) => dispatch({ type: "SAVE_ERROR", error: e.message }),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-6 w-[480px] space-y-4">
        <header className="flex items-center justify-between">
          <h2 className="text-lg font-bold">New Character — Step {state.step}/4</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white">✕</button>
        </header>
        {state.error && <div className="bg-rose-900/40 border border-rose-700 p-2 rounded text-rose-200 text-sm">{state.error}</div>}

        {state.step === 1 && <Step1Identity state={state} dispatch={dispatch} />}
        {state.step === 2 && <Step2VoiceSource state={state} dispatch={dispatch} />}
        {state.step === 3 && <Step3Preview state={state} dispatch={dispatch} />}
        {state.step === 4 && <Step4Save state={state} onSave={() => saveMutation.mutate()} saving={saveMutation.isPending} />}
      </div>
    </div>
  );
}

function Step1Identity({ state, dispatch }: any) {
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      const fd = new FormData(e.currentTarget);
      dispatch({
        type: "IDENTITY_SUBMIT",
        identity: {
          id: String(fd.get("id") || ""),
          display_name: String(fd.get("display_name") || ""),
          persona: (fd.get("persona") as any) || null,
        },
      });
    }}>
      <label className="block text-sm">id (kebab-case)
        <input name="id" defaultValue={state.identity.id} className="block w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1" />
      </label>
      <label className="block text-sm mt-2">display name
        <input name="display_name" defaultValue={state.identity.display_name} className="block w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1" />
      </label>
      <label className="block text-sm mt-2">persona
        <select name="persona" defaultValue={state.identity.persona ?? ""} className="block w-full mt-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
          <option value="">(none)</option>
          {PERSONA_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      <div className="mt-4 flex justify-end">
        <button type="submit" className="px-3 py-1 bg-cyan-600 text-white rounded">Next</button>
      </div>
    </form>
  );
}

function Step2VoiceSource({ state, dispatch }: any) {
  return (
    <div className="space-y-3">
      <p className="text-sm">Pick a voice source:</p>
      <BrowserRecorder onRecorded={(blob, mimeType) => dispatch({
        type: "VOICE_SOURCE_SET",
        source: { kind: "recording", blob, mimeType },
      })} />
      <div className="border-t border-zinc-700 pt-3">
        <input type="file" accept="audio/*" onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) dispatch({ type: "VOICE_SOURCE_SET", source: { kind: "upload", file } });
        }} />
      </div>
      <button onClick={() => dispatch({ type: "BACK" })} className="text-zinc-400">← Back</button>
    </div>
  );
}

function Step3Preview({ state, dispatch }: any) {
  // For Phase 25c v1, library voices skip the clone step.
  // For recording/upload, kick off cloneVoice and poll the job.
  // TODO: implement clone polling here.
  return (
    <div className="space-y-3">
      <p className="text-sm">Preview your voice. Press play.</p>
      {state.preview.audioUrl ? (
        <audio src={state.preview.audioUrl} controls />
      ) : (
        <p className="text-zinc-400 text-sm italic">preview not ready yet</p>
      )}
      <div className="flex justify-between">
        <button onClick={() => dispatch({ type: "BACK" })} className="text-zinc-400">← Back</button>
        <button onClick={() => dispatch({ type: "CLONE_JOB_UPDATED", job: { job_id: "stub", status: "succeeded", voice_ref: "stub" }})} className="px-3 py-1 bg-cyan-600 text-white rounded">Continue</button>
      </div>
    </div>
  );
}

function Step4Save({ state, onSave, saving }: any) {
  return (
    <div className="space-y-3">
      <h3 className="font-bold">{state.identity.display_name}</h3>
      <p className="text-sm text-zinc-400">id: {state.identity.id}</p>
      <p className="text-sm text-zinc-400">persona: {state.identity.persona || "—"}</p>
      <p className="text-sm text-zinc-400">voice: {state.cloneJob?.voice_ref || "—"}</p>
      <button onClick={onSave} disabled={saving} className="w-full px-3 py-2 bg-emerald-600 text-white rounded disabled:opacity-50">
        {saving ? "Saving..." : "Save Character"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd core/claude_code_talker/webui && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/CreateCharacterWizard.tsx
git commit -m "feat(webui): CreateCharacterWizard with 4-step skeleton (Phase 25c Task 5)"
```

---

## Task 6: CharactersList + CharacterDetail components

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/CharactersList.tsx`
- Create: `core/claude_code_talker/webui/src/features/characters/CharacterDetail.tsx`

- [ ] **Step 1: Implement list**

```tsx
import { useQuery } from "@tanstack/react-query";
import { listCharacters } from "./characters.api";
import { PersonaBadge } from "./PersonaBadge";
import type { Character } from "./characters.types";

export function CharactersList({ selectedId, onSelect }: { selectedId: string | null; onSelect: (c: Character) => void }) {
  const { data: chars = [], isLoading } = useQuery({ queryKey: ["characters"], queryFn: listCharacters });
  if (isLoading) return <p className="text-zinc-500">Loading…</p>;
  if (chars.length === 0) return <p className="text-zinc-500 text-sm">No characters yet. Click + to create.</p>;
  return (
    <ul className="space-y-1">
      {chars.map(c => (
        <li key={c.id}>
          <button
            onClick={() => onSelect(c)}
            className={`w-full text-left px-3 py-2 rounded border ${
              selectedId === c.id ? "bg-zinc-800 border-cyan-600" : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            <div className="font-medium">{c.display_name}</div>
            <div className="text-xs text-zinc-400">{c.id}</div>
            <PersonaBadge persona={c.persona} />
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: Implement detail**

```tsx
import type { Character } from "./characters.types";
import { PersonaBadge } from "./PersonaBadge";

export function CharacterDetail({ character }: { character: Character | null }) {
  if (!character) return <p className="text-zinc-500">Select a character to see details.</p>;
  return (
    <div className="space-y-3">
      <header>
        <h2 className="text-xl font-bold">{character.display_name}</h2>
        <p className="text-zinc-400 text-sm">{character.id}</p>
        <PersonaBadge persona={character.persona} />
      </header>
      <dl className="text-sm space-y-1">
        <div><dt className="text-zinc-500 inline">voice_ref:</dt> <dd className="inline">{character.voice_ref}</dd></div>
        {character.mesh_path && <div><dt className="text-zinc-500 inline">mesh:</dt> <dd className="inline">{character.mesh_path}</dd></div>}
        <div><dt className="text-zinc-500 inline">created:</dt> <dd className="inline">{new Date(character.created_at * 1000).toLocaleString()}</dd></div>
      </dl>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/CharactersList.tsx core/claude_code_talker/webui/src/features/characters/CharacterDetail.tsx
git commit -m "feat(webui): CharactersList + CharacterDetail (Phase 25c Task 6)"
```

---

## Task 7: CharactersTab top-level pane

**Files:**
- Create: `core/claude_code_talker/webui/src/features/characters/CharactersTab.tsx`

- [ ] **Step 1: Implement two-column tab pane**

```tsx
import { useState } from "react";
import { CharactersList } from "./CharactersList";
import { CharacterDetail } from "./CharacterDetail";
import { CreateCharacterWizard } from "./CreateCharacterWizard";
import type { Character } from "./characters.types";

export function CharactersTab() {
  const [selected, setSelected] = useState<Character | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  return (
    <div className="grid grid-cols-[280px_1fr] gap-4 h-full">
      <aside className="border-r border-zinc-800 pr-4 space-y-3 overflow-y-auto">
        <header className="flex items-center justify-between">
          <h2 className="font-bold">Characters</h2>
          <button onClick={() => setShowWizard(true)} className="px-2 py-1 bg-cyan-700 text-white rounded text-sm">+ New</button>
        </header>
        <CharactersList selectedId={selected?.id ?? null} onSelect={setSelected} />
      </aside>
      <section className="overflow-y-auto p-2">
        <CharacterDetail character={selected} />
      </section>
      {showWizard && <CreateCharacterWizard onClose={() => setShowWizard(false)} />}
    </div>
  );
}
```

- [ ] **Step 2: Register in DashboardShell**

In `webui/src/components/DashboardShell.tsx` (or wherever the top-level tab nav lives), add a Characters tab that renders `<CharactersTab />`.

- [ ] **Step 3: Build + manual smoke**

Run: `cd core/claude_code_talker/webui && npm run build`
Open dashboard, click Characters tab, verify list loads, wizard opens.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/CharactersTab.tsx core/claude_code_talker/webui/src/components/DashboardShell.tsx
git commit -m "feat(webui): Characters tab two-column pane (Phase 25c Task 7)"
```

---

## Task 8: Backend voice clone job tracker (TDD)

**Files:**
- Create: `core/claude_code_talker/voice/cloning_jobs.py`
- Create: `core/tests/test_voice_cloning_jobs.py`

- [ ] **Step 1: Write failing tests**

```python
"""Phase 25c — voice cloning job tracker tests."""
from __future__ import annotations

import time

import pytest

from claude_code_talker.voice.cloning_jobs import CloneJob, CloneJobTracker


def test_create_job_queues_and_returns_id(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("char-buddy", b"audio bytes", "audio/webm")
    assert job.status == "queued"
    assert job.character_id == "char-buddy"


def test_get_returns_persisted_job(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("char-buddy", b"a", "audio/webm")
    same = t.get(job.job_id)
    assert same is not None
    assert same.job_id == job.job_id


def test_set_running_and_succeeded(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("c", b"a", "audio/webm")
    t.set_running(job.job_id)
    assert t.get(job.job_id).status == "running"
    t.set_succeeded(job.job_id, voice_ref="char-c")
    assert t.get(job.job_id).status == "succeeded"
    assert t.get(job.job_id).voice_ref == "char-c"


def test_set_failed_records_error(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("c", b"a", "audio/webm")
    t.set_failed(job.job_id, error="boom")
    j = t.get(job.job_id)
    assert j.status == "failed"
    assert j.error == "boom"


def test_get_unknown_job_returns_none(tmp_path):
    t = CloneJobTracker(tmp_path)
    assert t.get("nope") is None


def test_jobs_persist_across_tracker_instances(tmp_path):
    t1 = CloneJobTracker(tmp_path)
    job = t1.create("c", b"a", "audio/webm")
    t1.set_succeeded(job.job_id, voice_ref="char-c")
    t2 = CloneJobTracker(tmp_path)  # new instance
    assert t2.get(job.job_id).status == "succeeded"
```

- [ ] **Step 2: Implement tracker**

```python
"""Phase 25c — voice cloning job tracker with sidecar JSON persistence."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CloneJob:
    job_id: str
    character_id: str
    mime_type: str
    status: str  # queued | running | succeeded | failed
    voice_ref: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class CloneJobTracker:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _save(self, job: CloneJob) -> None:
        job.updated_at = time.time()
        self._path(job.job_id).write_text(json.dumps(asdict(job)), encoding="utf-8")

    def create(self, character_id: str, _audio: bytes, mime_type: str) -> CloneJob:
        job_id = uuid.uuid4().hex[:12]
        job = CloneJob(job_id=job_id, character_id=character_id, mime_type=mime_type, status="queued")
        self._save(job)
        return job

    def get(self, job_id: str) -> CloneJob | None:
        p = self._path(job_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return CloneJob(**data)

    def set_running(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "running"
        self._save(job)

    def set_succeeded(self, job_id: str, voice_ref: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "succeeded"
        job.voice_ref = voice_ref
        self._save(job)

    def set_failed(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        job.status = "failed"
        job.error = error
        self._save(job)
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_voice_cloning_jobs.py -v`
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/voice/cloning_jobs.py core/tests/test_voice_cloning_jobs.py
git commit -m "feat(voice): CloneJobTracker with sidecar JSON persistence (Phase 25c Task 8)"
```

---

## Task 9: REST endpoints — POST /api/characters/{id}/clone-voice + GET /api/voice-clone-jobs/{job_id} (TDD)

**Files:**
- Modify: `core/claude_code_talker/api.py`
- Modify: `core/claude_code_talker/server.py` (wire CloneJobTracker into ServerState)
- Create: `core/tests/test_api_clone_voice.py`

- [ ] **Step 1: Write failing API tests**

```python
"""Phase 25c — clone-voice REST tests."""
from __future__ import annotations

import io

import pytest
from starlette.testclient import TestClient

from claude_code_talker.server import build_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_TALKER_HOME", str(tmp_path))
    app = build_app()
    return TestClient(app)


def test_clone_voice_returns_job_id(client):
    # First create a character
    client.post("/api/characters", json={
        "id": "buddy", "display_name": "Buddy", "voice_ref": "stub",
    })
    files = {"audio": ("sample.webm", b"fake bytes", "audio/webm")}
    data = {"mime_type": "audio/webm"}
    r = client.post("/api/characters/buddy/clone-voice", files=files, data=data)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_id"]


def test_clone_voice_unknown_character_returns_404(client):
    files = {"audio": ("x.webm", b"x", "audio/webm")}
    r = client.post("/api/characters/nope/clone-voice", files=files)
    assert r.status_code == 404


def test_get_clone_job(client):
    client.post("/api/characters", json={"id": "x", "display_name": "X", "voice_ref": "stub"})
    files = {"audio": ("a.webm", b"a", "audio/webm")}
    r = client.post("/api/characters/x/clone-voice", files=files, data={"mime_type": "audio/webm"})
    job_id = r.json()["job_id"]
    g = client.get(f"/api/voice-clone-jobs/{job_id}")
    assert g.status_code == 200
    assert g.json()["job_id"] == job_id


def test_get_clone_job_unknown_returns_404(client):
    assert client.get("/api/voice-clone-jobs/nope").status_code == 404
```

- [ ] **Step 2: Implement endpoints in api.py**

```python
async def characters_clone_voice(request: Request) -> Response:
    cid = request.path_params["character_id"]
    char = state.characters.get(cid)
    if not char:
        return JSONResponse({"error": "character not found"}, status_code=404)
    form = await request.form()
    audio = form.get("audio")
    mime_type = form.get("mime_type") or "audio/webm"
    if not audio:
        return JSONResponse({"error": "audio required"}, status_code=400)
    audio_bytes = await audio.read() if hasattr(audio, "read") else bytes(audio)
    job = state.clone_jobs.create(cid, audio_bytes, str(mime_type))
    # Phase 25c v1: stub clone — set succeeded immediately with voice_ref = char-<id>
    state.clone_jobs.set_succeeded(job.job_id, voice_ref=f"char-{cid}")
    body = state.clone_jobs.get(job.job_id)
    return JSONResponse({"job_id": body.job_id, "status": body.status, "voice_ref": body.voice_ref}, status_code=202)


async def voice_clone_job_get(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    job = state.clone_jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "job not found"}, status_code=404)
    return JSONResponse({
        "job_id": job.job_id, "status": job.status,
        "voice_ref": job.voice_ref, "error": job.error,
    })

routes.append(Route("/api/characters/{character_id}/clone-voice", characters_clone_voice, methods=["POST"]))
routes.append(Route("/api/voice-clone-jobs/{job_id}", voice_clone_job_get, methods=["GET"]))
```

- [ ] **Step 3: Wire CloneJobTracker into ServerState**

In `server.py`, where `ServerState` is constructed:

```python
from .voice.cloning_jobs import CloneJobTracker
state.clone_jobs = CloneJobTracker(home / "voice_clone_jobs")
```

- [ ] **Step 4: Tests pass**

Run: `pytest core/tests/test_api_clone_voice.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/api.py core/claude_code_talker/server.py core/tests/test_api_clone_voice.py
git commit -m "feat(api): POST /clone-voice + GET /voice-clone-jobs (Phase 25c Task 9)"
```

---

## Task 10: Wire wizard step 3 to call clone-voice + poll

**Files:**
- Modify: `core/claude_code_talker/webui/src/features/characters/CreateCharacterWizard.tsx`

- [ ] **Step 1: Replace stub with real clone-voice call + polling**

In `Step3Preview`:

```tsx
import { useEffect } from "react";
import { cloneVoice, getCloneVoiceJob } from "./characters.api";

function Step3Preview({ state, dispatch }: any) {
  useEffect(() => {
    if (state.cloneJob) return;
    if (state.voiceSource?.kind === "library") {
      dispatch({ type: "CLONE_JOB_UPDATED", job: { job_id: "library", status: "succeeded", voice_ref: state.voiceSource.voiceId } });
      return;
    }
    if (state.voiceSource?.kind === "recording" || state.voiceSource?.kind === "upload") {
      const blob = state.voiceSource.kind === "recording" ? state.voiceSource.blob : state.voiceSource.file;
      const mime = state.voiceSource.kind === "recording" ? state.voiceSource.mimeType : state.voiceSource.file.type;
      cloneVoice(state.identity.id, blob, mime).then(job => {
        dispatch({ type: "CLONE_JOB_UPDATED", job });
        // poll until done
        const tick = setInterval(async () => {
          const fresh = await getCloneVoiceJob(job.job_id);
          dispatch({ type: "CLONE_JOB_UPDATED", job: fresh });
          if (fresh.status === "succeeded" || fresh.status === "failed") clearInterval(tick);
        }, 1500);
      }).catch((e: Error) => dispatch({ type: "SAVE_ERROR", error: e.message }));
    }
  }, [state.voiceSource, state.cloneJob, dispatch, state.identity.id]);

  return (
    <div className="space-y-3">
      <p className="text-sm">Voice cloning status: <strong>{state.cloneJob?.status ?? "starting…"}</strong></p>
      {state.cloneJob?.status === "succeeded" && <p className="text-emerald-400">voice ref: {state.cloneJob.voice_ref}</p>}
      <button onClick={() => dispatch({ type: "BACK" })} className="text-zinc-400">← Back</button>
    </div>
  );
}
```

- [ ] **Step 2: Manual smoke**

Open dashboard → Characters → New → fill identity → record 3-second sample → step 3 shows succeeded → step 4 saves.

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/CreateCharacterWizard.tsx
git commit -m "feat(webui): wizard step 3 calls clone-voice and polls (Phase 25c Task 10)"
```

---

## Task 11: Attach character to a session from the dashboard

**Files:**
- Modify: `core/claude_code_talker/webui/src/features/characters/CharacterDetail.tsx`

- [ ] **Step 1: Add session-attach button**

```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { attachCharacter } from "./characters.api";

// inside CharacterDetail:
const { data: sessions = [] } = useQuery({ queryKey: ["sessions"], queryFn: () => fetch("/api/sessions").then(r => r.json()) });
const qc = useQueryClient();
const attach = useMutation({
  mutationFn: ({ sessionId, characterId }: { sessionId: string; characterId: string }) => attachCharacter(sessionId, characterId),
  onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
});

// JSX:
<div className="space-y-1">
  <p className="text-zinc-500 text-sm">Attach to session:</p>
  <select className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1" onChange={(e) => {
    if (e.target.value) attach.mutate({ sessionId: e.target.value, characterId: character.id });
  }}>
    <option value="">— pick session —</option>
    {sessions.map((s: any) => <option key={s.session_id} value={s.session_id}>{s.title || s.session_id.slice(0, 8)}</option>)}
  </select>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/webui/src/features/characters/CharacterDetail.tsx
git commit -m "feat(webui): attach character to session from CharacterDetail (Phase 25c Task 11)"
```

---

## Task 12: Final regression sweep

- [ ] **Step 1: Backend tests pass**

Run: `pytest core/tests/ -x`

- [ ] **Step 2: Frontend tests pass**

Run: `cd core/claude_code_talker/webui && npx vitest run && npm run build`

- [ ] **Step 3: Manual smoke**

- Create character "robin" with persona warm
- Record a 5-second voice sample, verify clone succeeds
- Attach to active session, verify SSE shows attached_character.id == "robin"
- Detach, verify it disappears

- [ ] **Step 4: Hand off to Phase 25b**

Tasks 8–11 produce a Phase 25c v1 where library voices work and recording/upload funnels through the stub clone path. Real cloning lands when Phase 25b's API-keyed providers come online.

---

## Notes for the implementer

- Don't add a Mesh tab to the wizard yet — that's Phase 25b Task 11.
- BrowserRecorder must clean up MediaStream tracks on unmount; otherwise the mic indicator stays on.
- `getUserMedia` requires HTTPS or localhost. Test with `http://127.0.0.1:17832` (allowed origin); not via `0.0.0.0`.
- `MediaRecorder.isTypeSupported` is undefined in some browsers — guard it.
- React Query `invalidateQueries({ queryKey: ["characters"] })` after every create/clone/attach.
- DRY: persona-color mapping lives in PersonaBadge only. Don't duplicate.
- YAGNI: skip avatar mesh preview in step 4; it lands in 25b.
