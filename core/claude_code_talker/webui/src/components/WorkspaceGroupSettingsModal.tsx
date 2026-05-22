// v0.1.0 unification — group settings modal for rename and delete.
// Mirrors the approach of renaming via the session detail panel's
// workspace_group input field, but provides group-level bulk operations.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Session } from "../types";
import { api } from "../api/client";

type Props = {
  groupKey: string;
  sessions: Session[];
  onClose: () => void;
  onGroupUpdated?: () => void;
};

export function WorkspaceGroupSettingsModal({
  groupKey,
  sessions,
  onClose,
  onGroupUpdated,
}: Props) {
  const [newName, setNewName] = useState(groupKey);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const qc = useQueryClient();

  const renameGroupMutation = useMutation({
    mutationFn: async (renamedTo: string) => {
      // Iterate sessions in this group and PATCH each one's workspace_group.
      // Sequential to avoid thundering herd; small batch sizes shouldn't be
      // a bottleneck.
      for (const s of sessions) {
        await api.patchSession(s.session_id, {
          workspace_group: renamedTo,
        });
      }
    },
    onSuccess: () => {
      // Invalidate the sessions query so the new group label appears
      // and the old group disappears (if empty).
      qc.invalidateQueries({ queryKey: ["sessions"] });
      onGroupUpdated?.();
    },
    onError: (e) => {
      // eslint-disable-next-line no-console
      console.error("Failed to rename group:", e);
      alert(`Failed to rename group: ${(e as Error).message}`);
    },
  });

  const deleteGroupMutation = useMutation({
    mutationFn: async () => {
      // Clear workspace_group on all sessions in this group by setting
      // it to empty string. This triggers the auto-derive fallback
      // (project_dir, cwd, etc.).
      for (const s of sessions) {
        await api.patchSession(s.session_id, {
          workspace_group: "",
        });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      onGroupUpdated?.();
      onClose();
    },
    onError: (e) => {
      // eslint-disable-next-line no-console
      console.error("Failed to delete group:", e);
      alert(`Failed to delete group: ${(e as Error).message}`);
      setIsConfirmingDelete(false);
    },
  });

  const isRenaming = newName !== groupKey;
  const canDelete = sessions.length === 0;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-[var(--color-surface-1)] rounded-lg border border-zinc-700 shadow-lg max-w-sm w-full space-y-4 p-5">
        <h2 className="font-bold text-[var(--color-text-1)]">
          Group: {groupKey}
        </h2>

        {/* Rename section */}
        <fieldset className="space-y-2">
          <legend className="text-sm text-[var(--color-text-2)] font-semibold">
            Rename group
          </legend>
          <div className="flex gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              disabled={renameGroupMutation.isPending}
              className="flex-1 px-2 py-1.5 bg-[var(--color-surface-0)] border border-zinc-700 rounded text-xs text-[var(--color-text-1)] disabled:opacity-50"
              placeholder="New group name"
            />
            <button
              type="button"
              onClick={() => renameGroupMutation.mutate(newName)}
              disabled={
                !isRenaming ||
                renameGroupMutation.isPending ||
                deleteGroupMutation.isPending
              }
              className="px-3 py-1.5 bg-cyan-600 text-white text-xs rounded font-semibold disabled:opacity-50 hover:bg-cyan-500 transition-colors"
            >
              {renameGroupMutation.isPending ? "Saving..." : "Save"}
            </button>
          </div>
          {renameGroupMutation.isError && (
            <p className="text-[11px] text-rose-400">
              {(renameGroupMutation.error as Error).message}
            </p>
          )}
        </fieldset>

        {/* Delete section */}
        <fieldset className="space-y-2 pt-2 border-t border-zinc-800">
          <legend className="text-sm text-[var(--color-text-2)] font-semibold">
            Delete group
          </legend>
          <p className="text-[11px] text-[var(--color-text-3)]">
            {canDelete
              ? "This group is empty. Deleting it will clear its workspace_group label on any sessions that may reference it."
              : `This group has ${sessions.length} session(s). Delete to clear their workspace_group labels.`}
          </p>
          {!isConfirmingDelete ? (
            <button
              type="button"
              onClick={() => setIsConfirmingDelete(true)}
              disabled={deleteGroupMutation.isPending}
              className="w-full px-3 py-1.5 bg-rose-900/30 border border-rose-700/50 text-rose-300 text-xs rounded font-semibold hover:bg-rose-900/50 transition-colors disabled:opacity-50"
            >
              Delete group
            </button>
          ) : (
            <div className="space-y-2">
              <p className="text-[11px] text-amber-400 font-semibold">
                Are you sure? This will clear workspace_group on {sessions.length}{" "}
                session{sessions.length === 1 ? "" : "s"}.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setIsConfirmingDelete(false)}
                  disabled={deleteGroupMutation.isPending}
                  className="flex-1 px-3 py-1.5 bg-[var(--color-surface-2)] border border-zinc-700 text-xs rounded font-semibold hover:bg-[var(--color-surface-3)] transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => deleteGroupMutation.mutate()}
                  disabled={deleteGroupMutation.isPending}
                  className="flex-1 px-3 py-1.5 bg-rose-700 text-white text-xs rounded font-semibold hover:bg-rose-600 transition-colors disabled:opacity-50"
                >
                  {deleteGroupMutation.isPending ? "Deleting..." : "Confirm delete"}
                </button>
              </div>
            </div>
          )}
        </fieldset>

        {/* Close button */}
        <div className="flex gap-2 pt-2 border-t border-zinc-800">
          <button
            type="button"
            onClick={onClose}
            disabled={renameGroupMutation.isPending || deleteGroupMutation.isPending}
            className="flex-1 px-3 py-1.5 bg-[var(--color-surface-2)] border border-zinc-700 text-xs rounded font-semibold hover:bg-[var(--color-surface-3)] transition-colors disabled:opacity-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
