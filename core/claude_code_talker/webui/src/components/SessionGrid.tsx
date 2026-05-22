// v0.1.0 unification — Sessions tab top-level layout.
// Replaces the flat SessionCard 3-column grid (live-only) with a
// pill-filtered, workspace-grouped, click-into-detail layout that
// mirrors the Pro Android SessionListScreen.
//
// Account-switching resilience (added 2026-05-10): when the user
// switches Claude accounts (or the session catalog changes radically
// for any reason), this component:
//   1. Drops collapsedGroups entries that no longer correspond to a
//      rendered group (otherwise localStorage accumulates dead labels).
//   2. Evicts react-query session-config caches for session IDs that
//      disappeared from the catalog (otherwise the cache grows
//      unbounded over long-running daemon sessions).
//   3. The openSessionId state is implicitly cleared because
//      `sortedSessions.find()` returns undefined for a missing SID and
//      the panel render is gated on `openSession !== null`.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { useSessions } from "../hooks/useSessions";
import { usePreferences } from "../hooks/usePreferences";
import { FilterChips, applySessionFilter } from "./FilterChips";
import {
  WorkspaceGroupSection,
  groupSessions,
} from "./WorkspaceGroupSection";
import { SessionRow } from "./SessionRow";
import { SessionDetailPanel } from "./SessionDetailPanel";
import { WorkspaceGroupSettingsModal } from "./WorkspaceGroupSettingsModal";
import type { Session } from "../types";

type Props = {
  /** Controlled open-session id from a parent that also drives the
   *  CharacterStage focus. When omitted, falls back to internal state
   *  for backward compatibility. */
  openSessionId?: string | null;
  onOpenSessionChange?: (id: string | null) => void;
};

export function SessionGrid({ openSessionId: openProp, onOpenSessionChange }: Props = {}) {
  const { data, isLoading, error } = useSessions();
  const { prefs, setPref } = usePreferences();
  const qc = useQueryClient();
  // Controlled vs uncontrolled: when a parent passes openSessionId we
  // mirror it through setOpenSessionId so all in-component logic can keep
  // using the existing variable name without branching everywhere.
  const [internalOpenSessionId, setInternalOpenSessionId] = useState<string | null>(null);
  const openSessionId = openProp !== undefined ? openProp : internalOpenSessionId;
  const setOpenSessionId: typeof setInternalOpenSessionId = (next) => {
    if (onOpenSessionChange) {
      const resolved = typeof next === "function" ? next(openSessionId) : next;
      onOpenSessionChange(resolved);
    } else {
      setInternalOpenSessionId(next);
    }
  };

  // Group settings modal state
  const [settingsGroupKey, setSettingsGroupKey] = useState<string | null>(null);

  // CCT-28: keep array identity stable across refetches when react-query
  // returns reference-equal data (placeholderData). The new layout sorts
  // before grouping so the order propagates per-group (groupSessions
  // preserves source-array order within each bucket).
  //
  // v0.1.0 unification — sort priority:
  //   1. pinned (user pinned to top of their group)
  //   2. is_live (active sessions ahead of dormant)
  //   3. last_modified desc (most recent first)
  const sortedSessions = useMemo<Session[]>(() => {
    return [...(data ?? [])].sort((a, b) => {
      const ap = !!a.pinned;
      const bp = !!b.pinned;
      if (ap !== bp) return ap ? -1 : 1;
      if (a.is_live !== b.is_live) return a.is_live ? -1 : 1;
      return b.last_modified - a.last_modified;
    });
  }, [data]);

  const filtered = useMemo(
    () => applySessionFilter(sortedSessions, prefs.sessionFilter),
    [sortedSessions, prefs.sessionFilter]
  );

  const settingsGroupSessions = useMemo(
    () =>
      settingsGroupKey
        ? filtered.filter(
            (s) => {
              const g = s.workspace_group?.trim();
              return settingsGroupKey === "Ungrouped"
                ? !g
                : g === settingsGroupKey;
            }
          )
        : [],
    [settingsGroupKey, filtered]
  );

  const groups = useMemo(() => {
    // Sort with "Ungrouped" always at the bottom (matches the
    // Claude.ai sidebar layout). Other groups sort alphabetically.
    const raw = groupSessions(filtered);
    const entries = [...raw.entries()];
    entries.sort(([a], [b]) => {
      if (a === "Ungrouped") return 1;
      if (b === "Ungrouped") return -1;
      return a.localeCompare(b);
    });
    return new Map(entries);
  }, [filtered]);

  const collapsedSet = useMemo(
    () => new Set(prefs.collapsedGroups),
    [prefs.collapsedGroups]
  );

  const toggleGroup = useCallback(
    (label: string) => {
      const next = new Set(prefs.collapsedGroups);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      setPref("collapsedGroups", [...next]);
    },
    [prefs.collapsedGroups, setPref]
  );

  const openSession = useMemo(
    () =>
      openSessionId
        ? sortedSessions.find((s) => s.session_id === openSessionId) ?? null
        : null,
    [openSessionId, sortedSessions]
  );

  // v0.1.0 unification — derive existing workspace_group labels from all
  // sessions so the Name & workspace input's autocomplete reflects what
  // the user has actually been organizing into, not a hardcoded list.
  // Sorted alphabetically; deduped.
  const existingGroups = useMemo(() => {
    const set = new Set<string>();
    for (const s of sortedSessions) {
      const g = s.workspace_group?.trim();
      if (g) set.add(g);
    }
    return [...set].sort();
  }, [sortedSessions]);

  // Account-switch hardening #1 — prune stale collapsedGroups labels.
  // Derive labels from ALL sessions (not just the current filter pill's
  // view) so toggling Live/All/Dormant doesn't drop collapse state for
  // groups that only exist in the off-filter view. Gated on `data` so
  // the prune doesn't fire during the first-paint empty state and
  // accidentally wipe everything before the catalog response lands.
  const allGroupLabels = useMemo(() => {
    if (!data) return null; // null sentinel = don't prune yet
    return new Set(groupSessions(sortedSessions).keys());
  }, [data, sortedSessions]);
  useEffect(() => {
    if (!allGroupLabels) return;
    const stale = prefs.collapsedGroups.filter((g) => !allGroupLabels.has(g));
    if (stale.length > 0) {
      setPref(
        "collapsedGroups",
        prefs.collapsedGroups.filter((g) => allGroupLabels.has(g))
      );
    }
  }, [allGroupLabels, prefs.collapsedGroups, setPref]);

  // Account-switch hardening #2 — evict session-config caches for SIDs
  // no longer in the catalog. Without this, the react-query cache grows
  // unbounded across long-running daemon sessions and account switches.
  // Gated on `data` to avoid the same first-paint-empty issue as #1.
  const sessionIdSet = useMemo(() => {
    if (!data) return null;
    return new Set(sortedSessions.map((s) => s.session_id));
  }, [data, sortedSessions]);
  useEffect(() => {
    if (!sessionIdSet) return;
    const cache = qc.getQueryCache();
    cache.findAll({ queryKey: ["session-config"] }).forEach((q) => {
      const sid = q.queryKey[1] as string | undefined;
      if (sid && !sessionIdSet.has(sid)) {
        qc.removeQueries({ queryKey: ["session-config", sid] });
      }
    });
  }, [sessionIdSet, qc]);

  if (isLoading) {
    return (
      <div className="p-6 text-[var(--color-text-3)]">Loading sessions…</div>
    );
  }
  if (error) {
    return <div className="p-6 text-rose-400">Failed to load sessions</div>;
  }

  // v0.1.0 unification — grid template adapts to whether a session is
  // open. When closed, the sessions list takes 100% width so long names
  // ("Pickng Up From A Steady Sonnet") aren't cut off. When open, the
  // detail panel takes its 360px (slightly tighter than before to leave
  // more space for the row name on narrow viewports).
  const gridCols = openSession
    ? "grid-cols-1 lg:grid-cols-[1fr_360px]"
    : "grid-cols-1";
  return (
    <div className={`grid ${gridCols} h-full`}>
      <div className="overflow-y-auto">
        <FilterChips
          value={prefs.sessionFilter}
          onChange={(v) => setPref("sessionFilter", v)}
          sessions={sortedSessions}
        />
        {filtered.length === 0 ? (
          <div className="p-6 text-[var(--color-text-3)]">
            No sessions in this filter.
          </div>
        ) : (
          <div className="pb-6">
            <AnimatePresence mode="popLayout" initial={false}>
              {[...groups.entries()].map(([label, sessions]) => (
                <WorkspaceGroupSection
                  key={label}
                  groupKey={label}
                  sessions={sessions}
                  collapsed={collapsedSet.has(label)}
                  onToggle={() => toggleGroup(label)}
                  onSettings={
                    label === "Ungrouped"
                      ? undefined
                      : () => setSettingsGroupKey(label)
                  }
                >
                  {sessions.map((s) => (
                    <SessionRow
                      key={s.session_id}
                      session={s}
                      isOpen={s.session_id === openSessionId}
                      onOpen={() =>
                        setOpenSessionId((prev) =>
                          prev === s.session_id ? null : s.session_id
                        )
                      }
                    />
                  ))}
                </WorkspaceGroupSection>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {openSession && (
        <div className="hidden lg:block border-l border-zinc-800 overflow-hidden">
          <SessionDetailPanel
            session={openSession}
            existingGroups={existingGroups}
            onClose={() => setOpenSessionId(null)}
          />
        </div>
      )}

      {settingsGroupKey && (
        <WorkspaceGroupSettingsModal
          groupKey={settingsGroupKey}
          sessions={settingsGroupSessions}
          onClose={() => setSettingsGroupKey(null)}
          onGroupUpdated={() => {
            // Re-invalidate sessions query so groups refresh
            qc.invalidateQueries({ queryKey: ["sessions"] });
          }}
        />
      )}
    </div>
  );
}
