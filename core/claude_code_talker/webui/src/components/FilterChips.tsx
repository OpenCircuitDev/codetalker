// v1.0 filter pills — Active (default) / Live / Muted.
//
// Per-user direction: dormant sessions don't appear in the list anymore.
// They only reappear once their Claude Code conversation re-opens (and
// becomes is_live). The previous "Dormant" + "All" chips are gone — the
// list intentionally hides closed CC conversations to keep focus on
// what the user is doing right now.
//
// - Active (DEFAULT)  — currently in use: is_speaking, or
//                       last_user_interaction_at within 30s.
// - Live              — every live CC session (escape hatch when the
//                       Active narrow view is too restrictive).
// - Muted             — sessions with enabled==false. Surfaced as a
//                       filter so the user can find muted sessions and
//                       turn them back on (otherwise they're invisible
//                       in Active/Live by virtue of being silent).
import type { Session } from "../types";

export type SessionFilter = "active" | "live" | "muted";

/** Sessions are considered "active" if the user interacted with them in
 *  the last N seconds OR the daemon is currently narrating their audio.
 *  30s matches `evaluate_auto_mode`'s default idle threshold so the
 *  pill and the brief/live auto-flip line up on the same clock. */
const ACTIVE_WINDOW_SEC = 30;

const PILLS: { key: SessionFilter; label: string; title: string }[] = [
  { key: "active", label: "Active", title: `Sessions narrating audio or with user activity in the last ${ACTIVE_WINDOW_SEC}s (default)` },
  { key: "live", label: "Live", title: "All Claude Code sessions currently open (broader than Active)" },
  { key: "muted", label: "Muted", title: "Sessions with narration disabled (enabled=false). Open one and tap 'unmute' to resume." },
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
  const last = s.last_user_interaction_at || 0;
  if (!last) return false;
  // last_user_interaction_at is epoch seconds (daemon-side wall clock).
  // Date.now() is browser ms. Allow ±2s skew tolerance.
  const ageSec = Date.now() / 1000 - last;
  return ageSec >= -2 && ageSec < ACTIVE_WINDOW_SEC;
}

function bucketCount(filter: SessionFilter, sessions: Session[]): number {
  switch (filter) {
    case "active":
      // Active is a subset of live — dormant sessions never count.
      return sessions.filter((s) => s.is_live && isActiveNow(s)).length;
    case "live":
      return sessions.filter((s) => s.is_live).length;
    case "muted":
      // Muted shows any session with enabled==false. Include dormant
      // muted sessions too so the user can find historically-muted
      // sessions and re-enable them. Otherwise muted dormant sessions
      // would be permanently invisible.
      return sessions.filter((s) => s.enabled === false).length;
  }
}

export function applySessionFilter(
  sessions: Session[],
  filter: SessionFilter,
  _activeId?: string | null
): Session[] {
  switch (filter) {
    case "active":
      return sessions.filter((s) => s.is_live && isActiveNow(s));
    case "live":
      return sessions.filter((s) => s.is_live);
    case "muted":
      return sessions.filter((s) => s.enabled === false);
  }
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
