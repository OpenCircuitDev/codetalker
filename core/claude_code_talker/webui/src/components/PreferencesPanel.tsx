// Phase 27 — Preferences panel: sound effects, density, accent.
import { usePreferences } from "../hooks/usePreferences";

export function PreferencesPanel() {
  const { prefs, setPref } = usePreferences();
  return (
    <section className="space-y-4 p-4 bg-[var(--color-surface-1)] rounded-lg border border-zinc-800">
      <h2 className="font-bold text-[var(--color-text-1)]">Preferences</h2>

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={prefs.soundEffects}
          onChange={(e) => setPref("soundEffects", e.target.checked)}
        />
        <span>Sound effects</span>
        <span className="text-xs text-[var(--color-text-3)]">(off by default)</span>
      </label>

      <fieldset className="space-y-1">
        <legend className="text-sm text-[var(--color-text-2)]">Density</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="density"
            checked={prefs.density === "comfortable"}
            onChange={() => setPref("density", "comfortable")}
          />
          <span>Comfortable</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="density"
            checked={prefs.density === "compact"}
            onChange={() => setPref("density", "compact")}
          />
          <span>Compact</span>
        </label>
      </fieldset>

      <fieldset className="space-y-1">
        <legend className="text-sm text-[var(--color-text-2)]">Accent</legend>
        {(["cyan", "emerald", "violet"] as const).map((a) => (
          <label key={a} className="flex items-center gap-2">
            <input
              type="radio"
              name="accent"
              checked={prefs.accent === a}
              onChange={() => setPref("accent", a)}
            />
            <span className="capitalize">{a}</span>
          </label>
        ))}
      </fieldset>
    </section>
  );
}
