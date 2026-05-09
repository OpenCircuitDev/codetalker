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
