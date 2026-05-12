// v0.1.0 unification — three-sink multi-select for audio routing.
// Mirrors the Pro Android DestinationPicker (SessionDetailScreen.kt) so
// the same widget pattern appears in: SessionDetailPanel (per-session),
// PreferencesPanel (fleet default), and the future companion shortcut.
//
// Semantics match `_resolve_audio_outputs` in audio.py:
//   - `null` (or undefined) = inherit fleet default
//   - `[]`                  = explicit silence everywhere
//   - any subset of {desktop, phone, glasses} = override
//
// When showing "Inheriting fleet default" we fetch the actual default
// from /api/cfg/audio-defaults so the chips truthfully reflect what the
// session would play. Falls back to {desktop, phone, glasses} if the
// endpoint is unavailable (daemon predates v0.1.0 or transient error).
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AudioOutput } from "../types";

const SINKS: { key: AudioOutput; label: string }[] = [
  { key: "desktop", label: "Desktop" },
  { key: "phone", label: "Phone" },
  { key: "glasses", label: "Glasses" },
];

const ALL_SINKS: AudioOutput[] = ["desktop", "phone", "glasses"];

type Props = {
  value: AudioOutput[] | null | undefined;
  onChange: (next: AudioOutput[] | null) => void;
  /** When false, hides the "Reset to default" affordance. Useful for
   *  the global Preferences widget where there's nothing to fall back to. */
  allowReset?: boolean;
};

export function AudioOutputPicker({ value, onChange, allowReset = true }: Props) {
  // Share one cache entry across all picker instances; staleTime keeps
  // it from refetching on every per-session detail panel mount.
  const { data: defaults } = useQuery({
    queryKey: ["audio-defaults"],
    queryFn: api.audioDefaults,
    staleTime: 30_000,
    retry: false, // gracefully accept 404 from daemons predating v0.1.0
  });

  const isOverride = value !== null && value !== undefined;
  const fleetDefault: AudioOutput[] =
    (defaults?.default_outputs as AudioOutput[] | undefined) ?? ALL_SINKS;
  const effective = new Set<AudioOutput>(isOverride ? value! : fleetDefault);

  const toggle = (key: AudioOutput) => {
    const next = new Set(effective);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    const sorted = SINKS.map((s) => s.key).filter((k) => next.has(k));
    onChange(sorted);
  };

  return (
    <div className="space-y-1">
      <div className="flex gap-2">
        {SINKS.map(({ key, label }) => {
          const selected = effective.has(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => toggle(key)}
              className={
                "px-3 py-1 rounded-full text-xs font-medium border transition-colors " +
                (selected
                  ? "bg-cyan-700 text-white border-cyan-600 shadow-soft-1"
                  : "bg-zinc-900 text-zinc-400 border-zinc-700 hover:bg-zinc-800")
              }
              aria-pressed={selected}
            >
              {label}
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2 text-[10px] text-[var(--color-text-3)]">
        <span>
          {isOverride
            ? "Per-session override"
            : `Inheriting fleet default${
                defaults ? ` (${fleetDefault.join(", ")})` : ""
              }`}
        </span>
        {allowReset && isOverride && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-cyan-400 hover:text-cyan-300 underline-offset-2 hover:underline"
          >
            Reset to default
          </button>
        )}
      </div>
    </div>
  );
}
