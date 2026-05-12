// v0.1.0 unification — shared optimistic-mutation pattern for any
// PUT /api/sessions/{sid}/overlay write. Used by SessionRow's mute /
// mode / pin mutations and SessionDetailPanel's name / workspace_group /
// audio_outputs / auto_mode / etc. mutations.
//
// Without optimistic updates, every toggle waits for PUT (~50ms) +
// refetch (~150ms) + re-render before reflecting the new value, which
// feels laggy ("did my click register?"). This hook updates the
// react-query caches before the round-trip; rolls back on failure;
// invalidates on settle to re-sync with server truth.
//
// Two caches get patched: ["sessions"] (the list view) AND
// ["session-config", sid] (the per-session config view, which the
// mode picker / mute / cadence read from). Both are invalidated on
// settle so the next refetch grabs server truth.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Session, SessionOverlayPatch } from "../types";

type OptimisticContext = {
  prevSessions: Session[] | undefined;
  prevConfig: unknown;
};

export type OptimisticPatchInput =
  | SessionOverlayPatch
  | { active_mode: string }
  | { enabled: boolean }
  | { pinned: boolean };

/** Returns a configured useMutation hook bound to a specific session.
 *  Pass the partial overlay shape to `mutate()`; the hook will patch
 *  both the sessions list cache and the session-config cache before
 *  the server round-trip. */
export function useOptimisticSessionPatch(sessionId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (overlay: OptimisticPatchInput) =>
      api.putOverlay(sessionId, overlay as SessionOverlayPatch),
    onMutate: async (overlay): Promise<OptimisticContext> => {
      // Cancel any in-flight refetch so it doesn't clobber our optimistic
      // write between the cache update and the server response.
      await qc.cancelQueries({ queryKey: ["sessions"] });
      await qc.cancelQueries({ queryKey: ["session-config", sessionId] });

      const prevSessions = qc.getQueryData<Session[]>(["sessions"]);
      const prevConfig = qc.getQueryData(["session-config", sessionId]);

      // Patch the sessions list cache. The overlay may include both
      // session-level fields (display_name, workspace_group, audio_outputs,
      // auto_mode_enabled, pinned) AND config-level fields (active_mode,
      // enabled). For session-level we patch directly. For config-level
      // we mirror to a synthetic top-level key so the row's quick-pick
      // (which reads session.mode || config.active_mode) updates too.
      if (prevSessions) {
        const patch = overlay as Partial<Session> & {
          active_mode?: string;
        };
        // Keep the SessionRow's mode quick-pick in sync by also writing
        // to the synthetic `mode` field when active_mode is set.
        const sessionPatch: Partial<Session> = {
          ...patch,
          ...(patch.active_mode ? { mode: patch.active_mode } : {}),
        };
        qc.setQueryData<Session[]>(
          ["sessions"],
          prevSessions.map((s) =>
            s.session_id === sessionId ? ({ ...s, ...sessionPatch } as Session) : s
          )
        );
      }
      if (prevConfig && typeof prevConfig === "object") {
        qc.setQueryData(["session-config", sessionId], {
          ...prevConfig,
          ...overlay,
        });
      }

      return { prevSessions, prevConfig };
    },
    onError: (_err, _vars, context) => {
      // Roll back the optimistic patch on failure.
      if (context?.prevSessions !== undefined) {
        qc.setQueryData(["sessions"], context.prevSessions);
      }
      if (context?.prevConfig !== undefined) {
        qc.setQueryData(["session-config", sessionId], context.prevConfig);
      }
    },
    onSettled: () => {
      // Re-validate against the server in the background.
      qc.invalidateQueries({ queryKey: ["session-config", sessionId] });
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}
