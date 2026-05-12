// Phase 27 — localStorage-backed user preferences.
// Sound effects default OFF; density and accent customizable.
// v0.1.0 unification — adds sessionFilter + collapsedGroups so the new
// Sessions screen layout state survives page reloads.
import { useCallback, useEffect, useState } from "react";

// v1.0 — filter set simplified to Active / Live / Muted. Dormant
// sessions no longer appear in any filter; they only re-emerge when
// their Claude Code conversation reopens (is_live flips true). The
// previous "all" / "dormant" filters are migrated to "active" on load
// in load() below.
export type SessionFilter = "active" | "live" | "muted";

export interface Preferences {
  soundEffects: boolean;
  density: "compact" | "comfortable";
  accent: "cyan" | "emerald" | "violet";
  sessionFilter: SessionFilter;
  collapsedGroups: string[]; // group labels currently collapsed
}

const KEY = "cct.prefs";
const DEFAULTS: Preferences = {
  soundEffects: false,
  density: "comfortable",
  accent: "cyan",
  // v1.0 default — Active (currently-in-use sessions only). Previously
  // "live"; the broader Live view is still one tap away.
  sessionFilter: "active",
  collapsedGroups: [],
};

function load(): Preferences {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw);
    // Migrate retired filter values to the new default. Users coming
    // back from a previous version had "live" / "all" / "dormant"
    // stored; map those onto the new set so the UI doesn't render with
    // an unknown selection.
    if (parsed.sessionFilter === "all" || parsed.sessionFilter === "dormant") {
      parsed.sessionFilter = "active";
    }
    return { ...DEFAULTS, ...parsed };
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
