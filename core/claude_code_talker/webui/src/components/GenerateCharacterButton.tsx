// Two-stage character generation: preview → edit → save.
//
// 1. Click button → daemon POST /api/sessions/{id}/generate-character?preview=true
//    returns the LLM draft without saving
// 2. CharacterDraftModal opens with every field pre-filled and editable
// 3. User reviews/edits/regenerates → "Save & attach" commits
//
// Previously this was a one-click flow that saved + attached immediately.
// User feedback: needs editability before send so users can refine the
// AI's suggestions for tone, persona, mesh prompt, and individual state
// poses before the character lands in the library.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { CharacterDraftModal, type CharacterDraft } from "./CharacterDraftModal";

type Props = {
  sessionId: string;
  sessionLabel: string;
};

type PreviewResponse = {
  preview: true;
  draft: CharacterDraft;
  session_id: string;
  session_label: string;
};

async function generateDraft(sessionId: string): Promise<CharacterDraft> {
  const r = await fetch(
    `/api/sessions/${encodeURIComponent(sessionId)}/generate-character?preview=true`,
    { method: "POST" }
  );
  if (!r.ok) {
    let detail = "";
    try {
      const body = await r.json();
      detail = body.error || JSON.stringify(body).slice(0, 200);
    } catch {
      detail = await r.text().catch(() => `HTTP ${r.status}`);
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  const body = (await r.json()) as PreviewResponse;
  return body.draft;
}

export function GenerateCharacterButton({ sessionId, sessionLabel }: Props) {
  const [draft, setDraft] = useState<CharacterDraft | null>(null);

  const mut = useMutation({
    mutationFn: () => generateDraft(sessionId),
    onSuccess: (d) => setDraft(d),
  });

  return (
    <div className="mt-2 space-y-1">
      <button
        type="button"
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        className="text-[11px] px-2 py-1 rounded border bg-violet-900/60 text-violet-100 border-violet-700 hover:bg-violet-800 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
        title={`Ask the LLM to design a character tailored to "${sessionLabel}", then review and edit before saving`}
      >
        <span>✨</span>
        <span>
          {mut.isPending
            ? `Designing character for "${sessionLabel}"…`
            : `Auto-generate character from "${sessionLabel}"`}
        </span>
      </button>
      <p className="text-[10px] text-[var(--color-text-3)] italic">
        Opens an editor so you can review, regenerate, or tweak the draft before saving.
      </p>
      {mut.isError && (
        <p className="text-rose-400 text-[10px] break-all">
          {(mut.error as Error)?.message}
        </p>
      )}
      {draft && (
        <CharacterDraftModal
          draft={draft}
          sessionId={sessionId}
          sessionLabel={sessionLabel}
          onClose={() => setDraft(null)}
          onRegenerate={() => generateDraft(sessionId)}
        />
      )}
    </div>
  );
}
