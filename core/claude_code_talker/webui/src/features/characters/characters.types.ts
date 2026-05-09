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
