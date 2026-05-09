// Phase 27 — localStorage-backed user preferences.
// Sound effects default OFF; density and accent customizable.
import { useCallback, useEffect, useState } from "react";

export interface Preferences {
  soundEffects: boolean;
  density: "compact" | "comfortable";
  accent: "cyan" | "emerald" | "violet";
}

const KEY = "cct.prefs";
const DEFAULTS: Preferences = {
  soundEffects: false,
  density: "comfortable",
  accent: "cyan",
};

function load(): Preferences {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return DEFAULTS;
  }
}

export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(() => load());

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      /* localStorage may be disabled in private mode */
    }
  }, [prefs]);

  const setPref = useCallback(
    <K extends keyof Preferences>(k: K, v: Preferences[K]) => {
      setPrefs((p) => ({ ...p, [k]: v }));
    },
    []
  );

  return { prefs, setPref };
}
