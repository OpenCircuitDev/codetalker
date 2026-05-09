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
