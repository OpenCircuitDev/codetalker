import { useQuery } from "@tanstack/react-query";

type Props = {
  value: string | undefined;
  onChange: (voice: string) => void;
};

type VoiceOption = { name: string; engine: string };

/** Fetches local voices only — piper (standard local TTS) and any cloned
 *  XTTS voices. Cloud engines like edge are intentionally excluded per
 *  product direction: codetalker is privacy-first and prefers local
 *  synthesis. */
async function loadLocalVoices(): Promise<VoiceOption[]> {
  let piper: VoiceOption[] = [];
  try {
    const r = await fetch("/api/voices?engine=piper");
    if (r.ok) {
      const data = (await r.json()) as string[];
      piper = data.map((name) => ({ name, engine: "piper" }));
    }
  } catch {
    /* fall through with empty piper list */
  }
  let cloned: VoiceOption[] = [];
  try {
    const r = await fetch("/api/voices/list");
    if (r.ok) {
      const data = (await r.json()) as { voices?: { voice_id?: string; name?: string }[] };
      cloned = (data.voices ?? []).map((v) => ({
        name: v.voice_id || v.name || "",
        engine: "xtts",
      })).filter((v) => v.name);
    }
  } catch {
    // Cloned voices are optional — silently skip if endpoint fails.
  }
  return [...piper, ...cloned];
}

export function VoicePicker({ value, onChange }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["voices", "local"],
    queryFn: loadLocalVoices,
    staleTime: 60_000,
  });

  const voices = data ?? [];

  return (
    <select
      className="bg-slate-900 border border-slate-700 rounded text-xs px-2 py-1 font-mono max-w-[12rem]"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      disabled={isLoading}
    >
      {!voices.some((v) => v.name === (value ?? "")) && (
        <option value="">{value ?? "(default)"}</option>
      )}
      {voices.map((v) => (
        <option key={`${v.engine}:${v.name}`} value={v.name}>
          {v.name} ({v.engine})
        </option>
      ))}
    </select>
  );
}
