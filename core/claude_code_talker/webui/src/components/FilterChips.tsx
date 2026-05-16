// 2026-05-16 filter pills — Active / Live / Brief / Muted.
//
// Aligned with the Pro Android SessionListScreen filter model so the
// two surfaces show the same set with the same semantics. A session is
// Active iff it had any activity (transcript write, hook, or user
// interaction) within the last RECENT_ACTIVITY_WINDOW_SEC. Within
// Active, the Live / Brief / Muted pills further narrow to the
// session's current state.
//
// - Active (DEFAULT) — sessions touched within the last hour
// - Live             — Active AND active_mode == "live"
// - Brief            — Active AND active_mode == "brief"
// - Muted            — Active AND enabled == false
//
// The Mute toggle on a row moves it from Live/Brief into Muted by
// flipping enabled=false; un-muting restores whichever mode it was in.
import type { Session } from "../types";

export type SessionFilter = "active" | "live" | "brief" | "muted";

/** 60-minute recency window. Matches the Pro Android filter and the
 *  Active reconciliation in MainActivity so audio-subscriber set,
 *  visibility filter, and reconciliation all agree. */
const RECENT_ACTIVITY_WINDOW_SEC = 60 * 60;

const PILLS: { key: SessionFilter; label: string; title: string }[] = [
  { key: "active", label: "Active", title: "Sessions touched within the last hour (default)" },
  { key: "live", label: "Live", title: "Active sessions in Live speaking mode" },
  { key: "brief", label: "Brief", title: "Active sessions in Brief speaking mode" },
  { key: "muted", label: "Muted", title: "Active sessions with narration disabled. Tap 'unmute' on the row to resume." },
];

type Props = {
  value: SessionFilter;
  onChange: (next: SessionFilter) => void;
  sessions: Session[];
  /** @deprecated AR-companion-active sid. Kept for prop-shape compat but
   *  no longer drives the "Active" bucket. */
  activeSessionId?: string | null;
};

/** Default filter — what fresh installs land on. Active is the
 *  narrowest signal and the most useful "what should I look at right
 *  now" view; Live is the escape hatch when the user wants broader
 *  context. */
export const DEFAULT_SESSION_FILTER: SessionFilter = "active";

function isActiveNow(s: Session): boolean {
  if (s.is_speaking) return true;
  if (s.is_live) return true;
  const nowSec = Date.now() / 1000;
  // Treat catalog mtime (last_modified) as activity within the recency
  // window. Catches sessions where Claude is writing tool output but
  // the strict 5-min is_live badge has rolled over.
  const mod = s.last_modified || 0;
  if (mod > 0 && (nowSec - mod) >= -2 && (nowSec - mod) < RECENT_ACTIVITY_WINDOW_SEC) return true;
  const last = s.last_user_interaction_at || 0;
  if (last <= 0) return false;
  const ageSec = nowSec - last;
  return ageSec >= -2 && ageSec < RECENT_ACTIVITY_WINDOW_SEC;
}

function activeMatchesPill(s: Session, pill: SessionFilter): boolean {
  // Every non-Active pill is a SUBSET of Active, so first require recency.
  if (!isActiveNow(s)) return false;
  switch (pill) {
    case "active":
      return true;
    case "live":
      return (s.active_mode || "").toLowerCase() === "live";
    case "brief":
      return (s.active_mode || "").toLowerCase() === "brief";
    case "muted":
      return s.enabled === false;
  }
}

function bucketCount(filter: SessionFilter, sessions: Session[]): number {
  return sessions.filter((s) => activeMatchesPill(s, filter)).length;
}

export function applySessionFilter(
  sessions: Session[],
  filter: SessionFilter,
  _activeId?: string | null
): Session[] {
  return sessions.filter((s) => activeMatchesPill(s, filter));
}

export function FilterChips({ value, onChange, sessions }: Props) {
  return (
    <div className="flex gap-2 px-6 pt-4 flex-wrap">
      {PILLS.map(({ key, label, title }) => {
        const selected = value === key;
        const count = bucketCount(key, sessions);
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            title={title}
            className={
              "px-3 py-1 rounded-full text-xs font-medium transition-colors border " +
              (selected
                ? "bg-cyan-600 text-white border-cyan-500"
                : "bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800")
            }
            aria-pressed={selected}
          >
            {label}
            <span className="ml-1.5 text-[10px] opacity-70 font-mono">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
