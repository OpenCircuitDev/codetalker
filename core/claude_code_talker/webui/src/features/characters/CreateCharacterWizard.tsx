import { useEffect, useReducer } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { initialWizardState, wizardReducer } from "./wizardReducer";
import { BrowserRecorder } from "./BrowserRecorder";
import { cloneVoice, createCharacter, getCloneVoiceJob } from "./characters.api";
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
      try {
        await createCharacter({
          id: state.identity.id,
          display_name: state.identity.display_name,
          voice_ref: voiceRef,
          persona: state.identity.persona,
        });
      } catch (e: any) {
        // Phase 25c: recording/upload pre-creates the character at step 3 so
        // clone-voice has a target. If it already exists, that's fine.
        if (!String(e?.message || "").includes(": 409")) throw e;
      }
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
          <button onClick={onClose} className="text-zinc-400 hover:text-white">x</button>
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

function Step2VoiceSource({ dispatch }: any) {
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
      <button onClick={() => dispatch({ type: "BACK" })} className="text-zinc-400">Back</button>
    </div>
  );
}

function Step3Preview({ state, dispatch }: any) {
  // Phase 25c v1: library voices skip the clone path; recording/upload calls
  // POST /api/characters/{id}/clone-voice and polls until succeeded/failed.
  useEffect(() => {
    if (state.cloneJob) return;
    if (!state.voiceSource) return;

    if (state.voiceSource.kind === "library") {
      dispatch({
        type: "CLONE_JOB_UPDATED",
        job: { job_id: "library", status: "succeeded", voice_ref: state.voiceSource.voiceId },
      });
      return;
    }

    // recording / upload — pre-create the character with a placeholder
    // voice_ref so the clone-voice endpoint has a target, then kick off the
    // clone and poll the resulting job.
    const blob = state.voiceSource.kind === "recording"
      ? state.voiceSource.blob
      : state.voiceSource.file;
    const mime = state.voiceSource.kind === "recording"
      ? state.voiceSource.mimeType
      : (state.voiceSource.file.type || "audio/webm");
    let cancelled = false;
    let tick: number | null = null;

    (async () => {
      try {
        // pre-create character with placeholder; tolerate 409 (already exists)
        try {
          await createCharacter({
            id: state.identity.id,
            display_name: state.identity.display_name,
            voice_ref: `char-${state.identity.id}`,
            persona: state.identity.persona,
          });
        } catch (e: any) {
          if (!String(e?.message || "").includes(": 409")) throw e;
        }
        const job = await cloneVoice(state.identity.id, blob, mime);
        if (cancelled) return;
        dispatch({ type: "CLONE_JOB_UPDATED", job });
        if (job.status === "succeeded" || job.status === "failed") return;
        tick = window.setInterval(async () => {
          try {
            const fresh = await getCloneVoiceJob(job.job_id);
            if (cancelled) return;
            dispatch({ type: "CLONE_JOB_UPDATED", job: fresh });
            if (fresh.status === "succeeded" || fresh.status === "failed") {
              if (tick) { window.clearInterval(tick); tick = null; }
            }
          } catch (e: any) {
            if (tick) { window.clearInterval(tick); tick = null; }
            dispatch({ type: "SAVE_ERROR", error: e?.message || "clone poll failed" });
          }
        }, 1500);
      } catch (e: any) {
        if (!cancelled) dispatch({ type: "SAVE_ERROR", error: e?.message || "clone failed" });
      }
    })();

    return () => {
      cancelled = true;
      if (tick) window.clearInterval(tick);
    };
  }, [state.voiceSource, state.cloneJob, state.identity.id, state.identity.display_name, state.identity.persona, dispatch]);

  return (
    <div className="space-y-3">
      <p className="text-sm">
        Voice cloning status: <strong>{state.cloneJob?.status ?? "starting..."}</strong>
      </p>
      {state.cloneJob?.status === "succeeded" && (
        <p className="text-emerald-400 text-sm">voice ref: {state.cloneJob.voice_ref}</p>
      )}
      <button onClick={() => dispatch({ type: "BACK" })} className="text-zinc-400">Back</button>
    </div>
  );
}

function Step4Save({ state, onSave, saving }: any) {
  return (
    <div className="space-y-3">
      <h3 className="font-bold">{state.identity.display_name}</h3>
      <p className="text-sm text-zinc-400">id: {state.identity.id}</p>
      <p className="text-sm text-zinc-400">persona: {state.identity.persona || "-"}</p>
      <p className="text-sm text-zinc-400">voice: {state.cloneJob?.voice_ref || "-"}</p>
      <button onClick={onSave} disabled={saving} className="w-full px-3 py-2 bg-emerald-600 text-white rounded disabled:opacity-50">
        {saving ? "Saving..." : "Save Character"}
      </button>
    </div>
  );
}
