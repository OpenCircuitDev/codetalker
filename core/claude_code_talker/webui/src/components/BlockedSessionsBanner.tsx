// Blocked sessions banner — surfaces sessions needing attention for quick triage.
// Renders at the top of SessionGrid when ≥1 session is in blocked state.
// Click on a session chip to scroll that row into view.

import { useMemo } from "react";
import { deriveSessionHealth } from "./SessionRow";
import { getSessionHeadline } from "../types";
import type { Session } from "../types";

type Props = {
  /** All sessions (already filtered by active filter pill) */
  sessions: Session[];
};

export function BlockedSessionsBanner({ sessions }: Props) {
  const blockedSessions = useMemo(() => {
    return sessions
      .filter((s) => deriveSessionHealth(s, undefined) === "blocked")
      .sort((a, b) => (b.last_modified ?? 0) - (a.last_modified ?? 0));
  }, [sessions]);

  if (blockedSessions.length === 0) {
    return null;
  }

  const handleScrollToSession = (sessionId: string) => {
    const el = document.getElementById(`session-${sessionId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  const count = blockedSessions.length;
  const countText = count === 1 ? "1 session needs attention" : `${count} sessions need attention`;

  return (
    <div
      className="mx-3 mt-3 px-3 py-2.5 rounded border bg-amber-900/30 border-amber-700/50 text-amber-100"
      role="status"
      aria-label={`${count} session${count === 1 ? "" : "s"} blocked and may need attention`}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span aria-hidden="true" className="shrink-0">
          ⚠
        </span>
        <span className="text-sm font-semibold">{countText}:</span>
        <div className="flex gap-1.5 flex-wrap">
          {blockedSessions.map((s) => (
            <button
              key={s.session_id}
              type="button"
              onClick={() => handleScrollToSession(s.session_id)}
              className="text-xs px-2 py-1 rounded bg-amber-700/40 hover:bg-amber-700/60 text-amber-50 border border-amber-600/50 hover:border-amber-600 transition-colors"
              title={`Scroll to ${getSessionHeadline(s)}`}
            >
              [{getSessionHeadline(s)}]
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
