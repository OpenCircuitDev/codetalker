// v0.1.0 unification — side-panel detail view replacing the inline
// SessionControls in card mode. Mirrors the 8-section layout in
// Pro Android SessionDetailScreen.kt:
//   1. Name & workspace
//   2. Speaking mode (+ auto-switch toggle)
//   3. Audio destination (3-chip multi-select)
//   4. Voice
//   5. Cadence (live mode)
//   6. Muted
//   7. Character (read-only display)
//   8. Markup treatments
import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Session } from "../types";
import {
  resolveAttachedCharacter,
  characterDisplayName,
  getSessionHeadline,
} from "../types";
import { api } from "../api/client";
import { useSessionConfig } from "../hooks/useSessionConfig";
import { useOptimisticSessionPatch } from "../hooks/useOptimisticSessionPatch";
import { AudioOutputPicker } from "./AudioOutputPicker";
import { ModePicker } from "./ModePicker";
import { VoicePicker } from "./VoicePicker";
import { CadencePicker } from "./CadencePicker";
import { CharacterAvatar } from "./CharacterAvatar";
import { SessionMarkupQuick } from "./SessionMarkupQuick";
import { GenerateCharacterButton } from "./GenerateCharacterButton";

type Props = {
  session: Session;
  /** Existing workspace_group labels used elsewhere in the catalog,
   *  for the Name & workspace autocomplete datalist. Empty array is
   *  fine — the field falls back to a couple of sane defaults. */
  existingGroups?: string[];
  onClose: () => void;
};

export function SessionDetailPanel({
  session,
  existingGroups = [],
  onClose,
}: Props) {
  const { data: config } = useSessionConfig(session.session_id);
  const mutation = useOptimisticSessionPatch(session.session_id);

  const muted = config?.enabled === false;
  const char = resolveAttachedCharacter(session.attached_character);

  return (
    <aside className="h-full w-full overflow-y-auto bg-[var(--color-surface-1)] border-l border-zinc-800 p-5 space-y-5">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-bold text-lg truncate text-[var(--color-text-1)]">
            {getSessionHeadline(session)}
          </h2>
          <code className="text-[11px] text-[var(--color-text-3)] font-mono break-all">
            {session.session_id}
          </code>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-[var(--color-text-3)] hover:text-[var(--color-text-1)] text-lg leading-none px-2 py-1"
          aria-label="Close detail panel"
        >
          ✕
        </button>
      </header>

      <Section title="Name & workspace">
        <NameAndWorkspaceFields
          displayName={session.display_name}
          workspaceGroup={session.workspace_group ?? null}
          existingGroups={existingGroups}
          onSaveName={(name) => mutation.mutate({ display_name: name })}
          onSaveGroup={(group) => mutation.mutate({ workspace_group: group })}
          onClearNameOverride={() =>
            mutation.mutate({ display_name: null })
          }
        />
      </Section>

      <Section title="Speaking mode">
        <div className="space-y-2">
          <ModePicker
            value={config?.active_mode}
            onChange={(active_mode) => mutation.mutate({ active_mode })}
          />
          <AutoModeSwitch
            enabled={!!session.auto_mode_enabled}
            onChange={(auto_mode_enabled) =>
              mutation.mutate({ auto_mode_enabled })
            }
          />
        </div>
      </Section>

      <Section title="Audio destination">
        <AudioOutputPicker
          value={session.audio_outputs}
          onChange={(outputs) => mutation.mutate({ audio_outputs: outputs })}
        />
      </Section>

      <Section title="Voice">
        <VoicePicker
          value={config?.voice?.model}
          onChange={(model) =>
            mutation.mutate({ voice: { ...config?.voice, model } })
          }
        />
        <button
          type="button"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("cct:navigate", { detail: { tab: "voices" } })
            )
          }
          className="text-[10px] text-cyan-400 hover:underline mt-1 self-start"
          title="Open the Voices tab"
        >
          Manage voices →
        </button>
      </Section>

      {/* Cadence applies only when this session is in Live speaking
          mode. Dim + disable when in Brief / Direct so users don't tweak
          a setting that has no effect on their current narration. */}
      <Section title="Cadence (live mode)">
        <div
          className={
            (config?.active_mode === "live" ? "" : "opacity-50 pointer-events-none ") +
            "transition-opacity"
          }
          aria-disabled={config?.active_mode !== "live"}
        >
          <CadencePicker
            value={config?.live?.cadence}
            onChange={(cadence) =>
              mutation.mutate({ live: { ...config?.live, cadence } })
            }
          />
        </div>
        {config?.active_mode !== "live" && (
          <p className="text-[10px] text-[var(--color-text-3)] italic mt-1">
            Applies only when this session is in Live mode.
          </p>
        )}
      </Section>

      <Section title="Muted">
        <button
          type="button"
          onClick={() => mutation.mutate({ enabled: muted })}
          disabled={mutation.isPending}
          className={
            "text-xs px-3 py-1.5 rounded font-mono border " +
            (muted
              ? "bg-rose-900/40 text-rose-200 border-rose-700"
              : "bg-slate-900 text-slate-200 border-slate-700 hover:bg-slate-800")
          }
        >
          {muted ? "unmute" : "mute"}
        </button>
      </Section>

      <Section title="Character">
        <CharacterPicker
          sessionId={session.session_id}
          attached={char}
        />
        <GenerateCharacterButton
          sessionId={session.session_id}
          sessionLabel={getSessionHeadline(session)}
        />
      </Section>

      <Section title="Markup treatments">
        <SessionMarkupQuick sessionId={session.session_id} />
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-[11px] uppercase tracking-wider text-[var(--color-text-3)] font-semibold">
        {title}
      </h3>
      {children}
    </section>
  );
}

function NameAndWorkspaceFields({
  displayName,
  workspaceGroup,
  existingGroups,
  onSaveName,
  onSaveGroup,
  onClearNameOverride,
}: {
  displayName: string;
  workspaceGroup: string | null;
  /** Set of workspace_group labels already in use across the session
   *  catalog. Used to populate the autocomplete datalist so the user
   *  sees their own categorization, not a hardcoded suggestion list. */
  existingGroups: string[];
  onSaveName: (name: string) => void;
  onSaveGroup: (group: string) => void;
  /** Clears `persistent.display_name` so the row falls back to Claude
   *  Code's `/title` rename (or the slug-derived auto name). Without
   *  this affordance, once the user renames in the codetalker UI, future
   *  CC `/title` changes are silently ignored forever. */
  onClearNameOverride: () => void;
}) {
  const [name, setName] = useState(displayName);
  const [group, setGroup] = useState(workspaceGroup ?? "");
  // Saved-flash state: "name" or "group" key just hit, used to show a
  // brief checkmark next to the field so the user knows the write went
  // through. Critical UX feedback because the row also re-sorts into a
  // new group on workspace_group change, and the simultaneous re-shuffle
  // can otherwise look like the input "lost" the value rather than
  // committed it.
  const [savedFlash, setSavedFlash] = useState<"name" | "group" | null>(null);
  const flashSaved = (which: "name" | "group") => {
    setSavedFlash(which);
    setTimeout(() => setSavedFlash((cur) => (cur === which ? null : cur)), 1500);
  };

  // Re-sync local state if the upstream session changes (e.g. another
  // client edited it). Comparing against initial via useEffect dep list.
  useEffect(() => setName(displayName), [displayName]);
  useEffect(() => setGroup(workspaceGroup ?? ""), [workspaceGroup]);

  const handleNameBlur = () => {
    if (name !== displayName) {
      onSaveName(name);
      flashSaved("name");
    }
  };
  const handleGroupBlur = () => {
    if (group !== (workspaceGroup ?? "")) {
      onSaveGroup(group);
      flashSaved("group");
    }
  };
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.currentTarget.blur(); // triggers onBlur → save
    }
  };

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="text-[10px] text-[var(--color-text-3)] flex items-center gap-2 mb-0.5">
          Session name
          {savedFlash === "name" && (
            <span className="text-emerald-400 font-semibold">✓ saved</span>
          )}
        </span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={handleNameBlur}
          onKeyDown={handleKeyDown}
          className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm text-[var(--color-text-1)] focus:border-cyan-600 focus:outline-none"
        />
        <button
          type="button"
          onClick={onClearNameOverride}
          className="text-[10px] text-cyan-400 hover:text-cyan-300 mt-0.5 underline-offset-2 hover:underline"
          title="Clears the name you set here so the row falls back to Claude Code's /title rename or slug-derived auto name"
        >
          Reset to follow Claude Code
        </button>
      </label>
      <label className="block">
        <span className="text-[10px] text-[var(--color-text-3)] flex items-center gap-2 mb-0.5">
          Workspace group
          {savedFlash === "group" && (
            <span className="text-emerald-400 font-semibold">✓ saved · row moved to new group</span>
          )}
        </span>
        <input
          type="text"
          value={group}
          list="workspace-group-suggestions"
          placeholder="(ungrouped)"
          onChange={(e) => setGroup(e.target.value)}
          onBlur={handleGroupBlur}
          onKeyDown={handleKeyDown}
          className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm text-[var(--color-text-1)] focus:border-cyan-600 focus:outline-none"
        />
        <span className="text-[9px] text-[var(--color-text-3)] mt-0.5 block">
          Press Enter or click outside to save.
        </span>
        <datalist id="workspace-group-suggestions">
          {/* v0.1.0 unification — derive from existing workspace_groups
              the user has actually assigned across their session catalog,
              not a hardcoded list. Falls back to a few common defaults
              if the user has no assignments yet. */}
          {(existingGroups.length > 0
            ? existingGroups
            : ["OCR", "OCDev", "CodeTalker"]
          ).map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
      </label>
    </div>
  );
}

/** Character attach/detach widget. Lists every character in the daemon
 *  library (`/api/characters`), shows the currently-attached one with a
 *  detach button, and lets the user swap by clicking another card. The
 *  Pro Android equivalent is `ui/character/CharacterAttachRow.kt`.
 *
 *  "Other platforms" callout: each character carries a `mesh_provider`
 *  field (e.g. `meshy`). When non-local providers ship — Meshy library
 *  browser, ElevenLabs voice library, etc. — surface them as additional
 *  source rows above the local list. */
function CharacterPicker({
  sessionId,
  attached,
}: {
  sessionId: string;
  attached: ReturnType<typeof resolveAttachedCharacter>;
}) {
  const qc = useQueryClient();
  const { data: chars, isLoading } = useQuery({
    queryKey: ["characters"],
    queryFn: api.characters,
    staleTime: 30_000,
  });
  const attachMutation = useMutation({
    mutationFn: (characterId: string) =>
      api.attachCharacter(sessionId, characterId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const detachMutation = useMutation({
    mutationFn: () => api.detachCharacter(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });

  const attachedId = attached?.id;
  const sortedChars = (chars ?? []).slice().sort((a, b) => {
    if (a.id === attachedId) return -1;
    if (b.id === attachedId) return 1;
    return a.display_name.localeCompare(b.display_name);
  });

  return (
    <div className="space-y-2">
      {attached ? (
        <div className="flex items-center gap-3 p-2 rounded bg-cyan-950/40 border border-cyan-800/60">
          <CharacterAvatar
            name={characterDisplayName(attached)}
            meshUrl={attached.mesh_path}
            persona={attached.persona ?? null}
            size="sm"
          />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-[var(--color-text-1)] truncate">
              {characterDisplayName(attached)}
            </div>
            <div className="text-[11px] text-[var(--color-text-3)] truncate">
              {attached.persona || "no persona"} ·{" "}
              {attached.voice_ref || "default voice"}
              {attached.mesh_provider ? ` · ${attached.mesh_provider}` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={() => detachMutation.mutate()}
            disabled={detachMutation.isPending}
            className="text-[11px] px-2 py-1 rounded font-mono border bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800"
          >
            detach
          </button>
        </div>
      ) : (
        <div className="text-xs text-[var(--color-text-3)]">
          No character attached. Pick one below or create new in the
          Characters tab.
        </div>
      )}

      {isLoading ? (
        <div className="text-xs text-[var(--color-text-3)]">
          Loading characters…
        </div>
      ) : (chars?.length ?? 0) === 0 ? (
        <div className="text-xs text-[var(--color-text-3)]">
          No characters yet. Create one in the Characters tab.
        </div>
      ) : (
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-3)]">
            Library
          </div>
          {sortedChars.map((c) => {
            const isCurrent = c.id === attachedId;
            return (
              <button
                key={c.id}
                type="button"
                disabled={isCurrent || attachMutation.isPending}
                onClick={() => attachMutation.mutate(c.id)}
                className={
                  "w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-xs transition-colors border " +
                  (isCurrent
                    ? "bg-cyan-950/30 border-cyan-800/60 text-[var(--color-text-2)] cursor-default"
                    : "bg-zinc-900 border-zinc-800 hover:bg-zinc-800 hover:border-zinc-700 text-[var(--color-text-1)]")
                }
              >
                <span
                  className={
                    "inline-block w-1.5 h-1.5 rounded-full shrink-0 " +
                    (isCurrent ? "bg-cyan-400" : "bg-zinc-600")
                  }
                />
                <span className="flex-1 truncate">{c.display_name}</span>
                {c.mesh_provider && (
                  <span className="text-[10px] px-1 py-0.5 rounded bg-zinc-800 text-zinc-400">
                    {c.mesh_provider}
                  </span>
                )}
                {c.voice_ref && (
                  <code className="text-[10px] text-[var(--color-text-3)] font-mono truncate max-w-[100px]">
                    {c.voice_ref}
                  </code>
                )}
              </button>
            );
          })}
        </div>
      )}

      {attachMutation.isError && (
        <div className="text-[11px] text-rose-400">
          Attach failed: {(attachMutation.error as Error).message}
        </div>
      )}
      {detachMutation.isError && (
        <div className="text-[11px] text-rose-400">
          Detach failed: {(detachMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}

function AutoModeSwitch({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-zinc-600 bg-zinc-900 text-cyan-500 focus:ring-cyan-500"
      />
      <div>
        <div className="text-xs font-semibold text-[var(--color-text-1)]">
          Auto-switch by activity
        </div>
        <div className="text-[10px] text-[var(--color-text-3)]">
          Briefs background work, goes live when you interact.
        </div>
      </div>
    </label>
  );
}
