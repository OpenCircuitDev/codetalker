// Editable preview of an LLM-generated character draft.
//
// Workflow:
//   1. User clicks "Auto-generate character" in SessionDetailPanel
//   2. Daemon's POST /api/sessions/{id}/generate-character?preview=true
//      returns the draft (display_name + persona + mesh_prompt +
//      voice_ref + all 10 emotive_states) WITHOUT saving
//   3. This modal opens with every field pre-filled and editable
//   4. User can:
//      - Edit any field directly
//      - Regenerate to call the LLM again (replaces all fields with
//        a fresh draft — local edits are lost; user is warned)
//      - Cancel to discard
//      - Save & attach to commit
//   5. On save: POST /api/characters then POST attach-character
//
// The modal is shown via a portal-less inline fixed overlay, similar
// to CreateCharacterWizard's existing pattern in this codebase.
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

const PERSONAS = ["methodical", "warm", "technical", "plain", "sarcastic", "energetic"] as const;
const STATE_ORDER = [
  "idle", "listening", "speaking", "researching", "working",
  "questioning", "thinking", "confirming", "concluding", "alerted",
] as const;

export type CharacterDraft = {
  id: string;
  display_name: string;
  voice_ref: string;
  persona: string;
  mesh_prompt: string | null;
  emotive_states: Record<string, string>;
};

type Props = {
  draft: CharacterDraft;
  sessionId: string;
  sessionLabel: string;
  onClose: () => void;
  /** Called with the new character record after successful save+attach. */
  onSaved?: (character: CharacterDraft) => void;
  /** Re-generate via the LLM. Receives nothing; resolves with a fresh
   *  draft. Hits the same daemon endpoint with preview=true. */
  onRegenerate: () => Promise<CharacterDraft>;
};

function slugFromName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "") || "agent";
}

export function CharacterDraftModal({
  draft, sessionId, sessionLabel, onClose, onSaved, onRegenerate,
}: Props) {
  const qc = useQueryClient();
  // Local copy of the draft so user edits don't fight react-query.
  // The id auto-derives from display_name unless the user has manually
  // edited it (tracked by `idTouched`).
  const [d, setD] = useState<CharacterDraft>(draft);
  const [idTouched, setIdTouched] = useState(false);
  const [voicesList, setVoicesList] = useState<string[]>([]);

  // Refresh local state when parent passes a new draft (e.g. after
  // regenerate).
  useEffect(() => {
    setD(draft);
    setIdTouched(false);
  }, [draft]);

  // Load piper voices for the voice_ref dropdown.
  useEffect(() => {
    fetch("/api/voices?engine=piper")
      .then((r) => (r.ok ? r.json() : []))
      .then((v) => setVoicesList(Array.isArray(v) ? v : []))
      .catch(() => setVoicesList([]));
  }, []);

  const setField = <K extends keyof CharacterDraft>(k: K, v: CharacterDraft[K]) => {
    setD((cur) => ({ ...cur, [k]: v }));
  };
  const setState = (k: string, v: string) => {
    setD((cur) => ({
      ...cur,
      emotive_states: { ...cur.emotive_states, [k]: v },
    }));
  };

  // Auto-derive id from display_name until the user manually edits id.
  const effectiveId = idTouched ? d.id : slugFromName(d.display_name);

  const regenMut = useMutation({
    mutationFn: onRegenerate,
    onSuccess: (next) => {
      // Replace draft wholesale; clear idTouched so id re-derives.
      setD(next);
      setIdTouched(false);
    },
  });

  const saveMut = useMutation({
    mutationFn: async () => {
      // 1. Create the character (POST /api/characters)
      const body = {
        id: effectiveId,
        display_name: d.display_name.trim(),
        voice_ref: d.voice_ref.trim() || voicesList[0] || "en_GB-jenny_dioco-medium",
        persona: d.persona,
        mesh_prompt: d.mesh_prompt?.trim() || null,
        emotive_states: d.emotive_states,
      };
      const cr = await fetch("/api/characters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!cr.ok) {
        const t = await cr.text().catch(() => "");
        throw new Error(`create failed (${cr.status}): ${t}`);
      }
      const created = await cr.json();
      // 2. Attach to session
      const ar = await fetch(
        `/api/sessions/${encodeURIComponent(sessionId)}/attach-character`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ character_id: effectiveId }),
        }
      );
      if (!ar.ok) {
        const t = await ar.text().catch(() => "");
        throw new Error(`attach failed (${ar.status}): ${t}`);
      }
      return created as CharacterDraft;
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["characters"] });
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session-config", sessionId] });
      onSaved?.(created);
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="bg-zinc-950 border border-zinc-700 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        <header className="flex items-baseline justify-between gap-3 px-5 py-3 border-b border-zinc-800 shrink-0">
          <div className="min-w-0">
            <h2 className="text-base font-bold text-[var(--color-text-1)]">
              Generated character — review &amp; edit
            </h2>
            <p className="text-[11px] text-[var(--color-text-3)] mt-0.5 truncate">
              for session: <span className="text-cyan-300">{sessionLabel}</span>
              {" · "}LLM-generated. Every field below is editable. Save when ready.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saveMut.isPending}
            className="text-zinc-400 hover:text-white text-lg px-1"
            title="Cancel without saving"
          >
            ×
          </button>
        </header>

        <div className="overflow-y-auto px-5 py-4 space-y-4 flex-1">
          {/* Identity row */}
          <section>
            <h3 className="text-[10px] uppercase tracking-wider text-[var(--color-text-2)] font-semibold mb-1.5">
              Identity
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs">
                <span className="text-[var(--color-text-3)]">Display name</span>
                <input
                  className="mt-0.5 w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm"
                  value={d.display_name}
                  onChange={(e) => setField("display_name", e.target.value)}
                />
              </label>
              <label className="block text-xs">
                <span className="text-[var(--color-text-3)]">
                  ID <span className="text-[var(--color-text-3)] italic">(kebab-case)</span>
                </span>
                <input
                  className="mt-0.5 w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm font-mono"
                  value={effectiveId}
                  onChange={(e) => {
                    setIdTouched(true);
                    setField("id", e.target.value.toLowerCase().replace(/[^a-z0-9-]+/g, "-"));
                  }}
                  placeholder={slugFromName(d.display_name)}
                />
              </label>
              <label className="block text-xs">
                <span className="text-[var(--color-text-3)]">Persona</span>
                <select
                  className="mt-0.5 w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm"
                  value={d.persona}
                  onChange={(e) => setField("persona", e.target.value)}
                >
                  {PERSONAS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label className="block text-xs">
                <span className="text-[var(--color-text-3)]">Voice (piper)</span>
                <select
                  className="mt-0.5 w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm font-mono"
                  value={d.voice_ref}
                  onChange={(e) => setField("voice_ref", e.target.value)}
                >
                  {!voicesList.includes(d.voice_ref) && (
                    <option value={d.voice_ref}>{d.voice_ref || "(default)"}</option>
                  )}
                  {voicesList.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </label>
            </div>
          </section>

          {/* Mesh prompt */}
          <section>
            <h3 className="text-[10px] uppercase tracking-wider text-[var(--color-text-2)] font-semibold mb-1.5">
              Mesh prompt
              <span className="ml-2 text-[var(--color-text-3)] normal-case tracking-normal font-normal italic">
                visual description (waist-up portrait for talking-head format)
              </span>
            </h3>
            <textarea
              className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs resize-y focus:border-cyan-600 focus:outline-none"
              rows={3}
              value={d.mesh_prompt ?? ""}
              onChange={(e) => setField("mesh_prompt", e.target.value)}
              placeholder="Single sentence: attire, expression, era/style, arm position, framing as waist-up portrait"
            />
          </section>

          {/* Emotive states */}
          <section>
            <h3 className="text-[10px] uppercase tracking-wider text-[var(--color-text-2)] font-semibold mb-1.5">
              Emotive states
              <span className="ml-2 text-[var(--color-text-3)] normal-case tracking-normal font-normal italic">
                pose + expression + arm/hand gesture for each of the 10 states
              </span>
            </h3>
            <div className="space-y-1.5">
              {STATE_ORDER.map((s) => (
                <label key={s} className="block">
                  <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-3)] font-semibold">
                    {s}
                  </span>
                  <textarea
                    className="mt-0.5 w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs resize-y focus:border-cyan-600 focus:outline-none"
                    rows={2}
                    value={d.emotive_states[s] ?? ""}
                    onChange={(e) => setState(s, e.target.value)}
                  />
                </label>
              ))}
            </div>
          </section>
        </div>

        <footer className="border-t border-zinc-800 px-5 py-3 flex items-center justify-between gap-2 shrink-0">
          <div className="flex-1 min-w-0">
            {(regenMut.isError || saveMut.isError) && (
              <p className="text-rose-400 text-[11px] break-all">
                {((regenMut.error || saveMut.error) as Error)?.message}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saveMut.isPending}
            className="text-xs px-3 py-1.5 rounded border bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              if (
                Object.values(d.emotive_states).some((v) => v && v.trim()) &&
                !confirm("Regenerate will replace ALL fields with a fresh LLM draft and lose your edits. Continue?")
              ) {
                return;
              }
              regenMut.mutate();
            }}
            disabled={regenMut.isPending || saveMut.isPending}
            className="text-xs px-3 py-1.5 rounded border bg-violet-900/40 text-violet-200 border-violet-700 hover:bg-violet-900/70 disabled:opacity-40"
            title="Discard current edits and ask the LLM for a fresh draft"
          >
            {regenMut.isPending ? "Regenerating…" : "↻ Regenerate"}
          </button>
          <button
            type="button"
            onClick={() => saveMut.mutate()}
            disabled={
              saveMut.isPending ||
              regenMut.isPending ||
              !d.display_name.trim() ||
              !effectiveId
            }
            className="text-xs px-3 py-1.5 rounded border bg-cyan-700 text-white border-cyan-600 hover:bg-cyan-600 disabled:opacity-40"
          >
            {saveMut.isPending ? "Saving…" : "Save & attach"}
          </button>
        </footer>
      </div>
    </div>
  );
}
