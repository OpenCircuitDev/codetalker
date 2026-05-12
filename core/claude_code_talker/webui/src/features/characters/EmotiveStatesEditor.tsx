// v0.1.0 Tier 2 — per-character emotive state prompt editor.
//
// The user's "custom field entry sets for the builder" idea, made
// concrete: each of the 10 canonical emotive states (idle, listening,
// speaking, researching, working, questioning, thinking, confirming,
// concluding, alerted) gets a textarea. When the field is blank, the
// global STATE_PROFILES default applies. When the user fills it in,
// that character's "researching" mesh-generation prompt becomes
// character-specific.
//
// Editing is local — the parent component lifts the changed map via
// onChange and commits via PUT /api/characters/{id}. We don't auto-save
// on every keystroke because the per-state fields are long and the
// daemon write loops through a yaml serialize + atomic rename.
import { useEffect, useState } from "react";
import {
  STATE_PROFILES,
  type EmotiveState,
} from "../../hooks/useCharacterPose";

// Same canonical order as the catalog doc, top to bottom.
const STATE_ORDER: EmotiveState[] = [
  "idle",
  "listening",
  "speaking",
  "researching",
  "working",
  "questioning",
  "thinking",
  "confirming",
  "concluding",
  "alerted",
];

type Props = {
  /** Existing per-character overrides. */
  value: Record<string, string> | undefined;
  /** Called when the user clicks Save. Receives the cleaned map —
   *  only entries that differ from the global default are stored, so
   *  the yaml file stays clean and "matches default" stays implicit. */
  onChange: (next: Record<string, string>) => void;
  /** True while a save is in flight. */
  saving?: boolean;
};

/** Build the initial draft for the editor: for each state, use the
 *  per-character override if one exists; otherwise pre-fill with the
 *  global default so the user can edit-in-place rather than starting
 *  from a blank textarea. */
function buildDraft(value: Record<string, string> | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of STATE_ORDER) {
    const override = value?.[s];
    out[s] = override && override.trim() ? override : STATE_PROFILES[s].meshPromptHint;
  }
  return out;
}

/** Strip the draft down to "real overrides" — entries that differ from
 *  the global default get stored, entries that still match the default
 *  are dropped (treated as "use default"). Keeps the yaml minimal. */
function buildOverrides(draft: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of STATE_ORDER) {
    const v = (draft[s] ?? "").trim();
    if (!v) continue;
    if (v === STATE_PROFILES[s].meshPromptHint.trim()) continue;
    out[s] = v;
  }
  return out;
}

export function EmotiveStatesEditor({ value, onChange, saving }: Props) {
  // Local draft state keyed by state name. Initial pre-fill: per-character
  // override if set, else global default. Re-syncs when the parent record
  // changes (e.g. after a successful save round-trip).
  const [draft, setDraft] = useState<Record<string, string>>(() => buildDraft(value));
  useEffect(() => {
    setDraft(buildDraft(value));
  }, [value]);

  const commit = () => onChange(buildOverrides(draft));

  // Dirty when the stripped-overrides view differs from the persisted value.
  const isDirty =
    JSON.stringify(buildOverrides(draft)) !== JSON.stringify(value ?? {});

  return (
    <section className="space-y-2 pt-3 border-t border-zinc-800">
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-bold text-[var(--color-text-1)]">
          Emotive state prompts
        </h3>
        <p className="text-[10px] text-[var(--color-text-3)]">
          Defaults are pre-filled and editable. Saved only when changed.
        </p>
      </header>

      <div className="space-y-2">
        {STATE_ORDER.map((s) => {
          const fallback = STATE_PROFILES[s].meshPromptHint;
          const current = draft[s] ?? "";
          // "Using default" badge when the textarea content equals the
          // global default verbatim — visually distinguishes overrides
          // from defaults so the user sees what's been customized.
          const usingDefault = current.trim() === fallback.trim();
          return (
            <label key={s} className="block">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-2)] font-semibold flex items-center gap-2">
                {s}
                {usingDefault ? (
                  <span className="normal-case tracking-normal text-[9px] text-[var(--color-text-3)] italic">
                    (default)
                  </span>
                ) : (
                  <span className="normal-case tracking-normal text-[9px] text-cyan-400 font-semibold">
                    (custom)
                  </span>
                )}
                {!usingDefault && (
                  <button
                    type="button"
                    onClick={() =>
                      setDraft((d) => ({ ...d, [s]: fallback }))
                    }
                    className="ml-auto normal-case tracking-normal text-[9px] text-zinc-400 hover:text-cyan-300 underline-offset-2 hover:underline"
                  >
                    reset to default
                  </button>
                )}
              </span>
              <textarea
                value={current}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, [s]: e.target.value }))
                }
                rows={2}
                className={
                  "mt-0.5 w-full bg-zinc-900 border rounded px-2 py-1 text-xs resize-y focus:border-cyan-600 focus:outline-none " +
                  (usingDefault
                    ? "border-zinc-800 text-[var(--color-text-2)]"
                    : "border-cyan-800/60 text-[var(--color-text-1)]")
                }
              />
            </label>
          );
        })}
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={() => setDraft(buildDraft(value))}
          disabled={!isDirty || saving}
          className="text-[11px] px-2 py-1 rounded border bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Revert all
        </button>
        <button
          type="button"
          onClick={commit}
          disabled={!isDirty || saving}
          className="text-[11px] px-3 py-1 rounded border bg-cyan-700 text-white border-cyan-600 hover:bg-cyan-600 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? "Saving…" : "Save prompts"}
        </button>
      </div>
    </section>
  );
}
