// Phase 4 (2026-05-16) — single SSE subscription that invalidates the
// relevant React Query caches when the daemon publishes an event.
//
// Replaces (well, augments — Phase 6 removes the timers entirely) the
// per-query refetchInterval polling on:
//
//   * useSessions           (was 5s)
//   * useDaemonHealth       (was 5s)
//   * master-enabled query  (was 5s)
//
// On a SessionChanged or MasterConfigChanged event, the matching
// queries get invalidated and React Query refetches immediately. The
// existing refetchInterval polls remain as a safety net so we still
// catch state changes even if SSE silently drops (network blip, NAT
// timeout, etc.) — Phase 6 raises those intervals to 30s once SSE
// has had a few weeks of production soak.
//
// The hook is mounted once at App root. It does not return anything;
// its side effect is the cache invalidation pipeline.

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

// Mirror of the daemon's Event base + discriminator. We only need the
// `event_type` here for dispatch; specific event payloads land on
// queries via cache invalidation rather than this hook.
type DaemonEventName =
  | "SessionChanged"
  | "LifecycleChanged"
  | "MasterConfigChanged"
  | "AudioJobStateChanged"
  | "SubscriptionChanged"
  | "CharacterPoseChanged"
  | "__overflow__";

export function useDaemonEvents(
  topics?: DaemonEventName[],
): void {
  const qc = useQueryClient();

  useEffect(() => {
    const url = topics && topics.length > 0
      ? `/api/events?topics=${encodeURIComponent(topics.join(","))}`
      : "/api/events";
    const es = new EventSource(url);

    // Per-event-type handlers — dispatched by the `event:` header.
    // Listeners are added explicitly so the browser routes them; the
    // generic onmessage handler only fires for events without an
    // explicit `event:` field, which our daemon doesn't emit.
    //
    // SessionChanged + LifecycleChanged carry a session_id in their
    // payload; we use it to scope cache invalidation to just that
    // session's per-session config query so unrelated panels don't
    // re-render needlessly.
    const onSessionChanged = (e: MessageEvent) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      try {
        const data = JSON.parse(e.data) as { session_id?: string };
        if (data.session_id) {
          qc.invalidateQueries({
            queryKey: ["session-config", data.session_id],
          });
        }
      } catch {
        // malformed payload — fall back to broad invalidation
        qc.invalidateQueries({ queryKey: ["session-config"] });
      }
    };
    const onMasterChanged = () => {
      qc.invalidateQueries({ queryKey: ["master-enabled"] });
      qc.invalidateQueries({ queryKey: ["daemon-health"] });
    };
    const onLifecycleChanged = (e: MessageEvent) => {
      // Lifecycle drives row-level animation; refresh the list and
      // the per-session config if a session_id is present.
      qc.invalidateQueries({ queryKey: ["sessions"] });
      try {
        const data = JSON.parse(e.data) as { session_id?: string };
        if (data.session_id) {
          qc.invalidateQueries({
            queryKey: ["session-config", data.session_id],
          });
        }
      } catch {
        // ignore malformed payload
      }
    };
    const onOverflow = () => {
      // We dropped events — re-fetch everything we depend on.
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session-config"] });
      qc.invalidateQueries({ queryKey: ["master-enabled"] });
      qc.invalidateQueries({ queryKey: ["daemon-health"] });
    };

    es.addEventListener("SessionChanged", onSessionChanged);
    es.addEventListener("MasterConfigChanged", onMasterChanged);
    es.addEventListener("LifecycleChanged", onLifecycleChanged);
    es.addEventListener("__overflow__", onOverflow);

    es.onerror = () => {
      // EventSource auto-reconnects on transport errors; nothing to do
      // here. The auto-reconnect window is typically <5s, which is the
      // same horizon as our existing polling fallback, so any
      // transient drop is invisible to the user.
    };

    return () => {
      es.removeEventListener("SessionChanged", onSessionChanged);
      es.removeEventListener("MasterConfigChanged", onMasterChanged);
      es.removeEventListener("LifecycleChanged", onLifecycleChanged);
      es.removeEventListener("__overflow__", onOverflow);
      es.close();
    };
  }, [qc, topics?.join(",")]);
}
