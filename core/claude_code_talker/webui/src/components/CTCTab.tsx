// CodeTalkerChat (CTC) mode — Zoom-grid view of all session characters.
//
// Each session renders as a tile with its attached character's avatar,
// a speaking-state pulse, and quick controls (mute + base mode). The
// selected tile drives a live-narration panel on the right.
//
// Design priorities, in order:
//   1. Quickly see WHO is talking right now (speaking pulse + glow)
//   2. Quickly switch the spotlight to any session (single click)
//   3. Mute / change mode without leaving the grid
//
// Future v1.x — when ported to Android this layout collapses to a
// vertical scroller with bigger cards. The grid CSS uses auto-fit so it
// already reflows to a single column on narrow viewports.
import { useMemo, useState } from "react";
import { useSessions } from "../hooks/useSessions";
import { useOptimisticSessionPatch } from "../hooks/useOptimisticSessionPatch";
import { useSessionConfig } from "../hooks/useSessionConfig";
import type { Session } from "../types";
import {
  resolveAttachedCharacter,
  characterDisplayName,
  getSessionHeadline,
} from "../types";
import { CharacterAvatar } from "./CharacterAvatar";
import { NarrationFeed } from "./NarrationFeed";
import { ModePicker } from "./ModePicker";

export function CTCTab() {
  const { data: sessions } = useSessions();
  const live = useMemo(
    () =>
      (sessions ?? [])
        .filter((s) => s.is_live)
        // Pinned + most-recently-touched first
        .sort((a, b) => {
          if ((b.pinned ? 1 : 0) !== (a.pinned ? 1 : 0))
            return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
          return (b.last_modified || 0) - (a.last_modified || 0);
        }),
    [sessions]
  );

  // Auto-select the first live session on load; sticky thereafter so the
  // spotlight doesn't jump if the user is mid-read.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const effectiveSelected =
    selectedId && live.some((s) => s.session_id === selectedId)
      ? selectedId
      : live[0]?.session_id ?? null;
  const selected =
    live.find((s) => s.session_id === effectiveSelected) ?? null;

  return (
    <div className="h-full flex flex-col bg-[var(--color-surface-0)]">
      <header className="px-4 py-2 border-b border-zinc-800 flex items-baseline gap-3">
        <h2 className="text-sm font-bold text-[var(--color-text-1)]">
          CodeTalkerChat
        </h2>
        <span className="text-[10px] uppercase tracking-widest text-cyan-400">
          CTC mode
        </span>
        <span className="text-[10px] text-[var(--color-text-3)]">
          {live.length} live · spotlight shows the selected session's narration
        </span>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Card grid — auto-fit gives a single column on narrow screens
            (mobile-friendly) and 3-4 cols on a 14"+ monitor. */}
        <section className="flex-1 overflow-y-auto p-3">
          {live.length === 0 ? (
            <p className="text-xs text-[var(--color-text-3)] italic p-4">
              No live sessions. Start a Claude Code conversation in any project
              to see it appear here.
            </p>
          ) : (
            <div
              className="grid gap-3"
              style={{
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              }}
            >
              {live.map((s) => (
                <CTCCard
                  key={s.session_id}
                  session={s}
                  selected={s.session_id === effectiveSelected}
                  onSelect={() => setSelectedId(s.session_id)}
                />
              ))}
            </div>
          )}
        </section>

        {/* Spotlight pane: live narration of the selected session +
            quick controls. Constant width so the grid layout stays
            stable when switching selections. */}
        <aside className="w-[360px] border-l border-zinc-800 flex flex-col bg-[var(--color-surface-1)]">
          {selected ? (
            <SpotlightPane session={selected} />
          ) : (
            <div className="p-4 text-xs text-[var(--color-text-3)]">
              Select a session card to focus its narration here.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

// ─── Card ────────────────────────────────────────────────────────────────

type CardProps = {
  session: Session;
  selected: boolean;
  onSelect: () => void;
};

function CTCCard({ session, selected, onSelect }: CardProps) {
  const char = resolveAttachedCharacter(session.attached_character);
  const config = useSessionConfig(session.session_id);
  const muted = config.data?.enabled === false;
  const speaking = !!session.is_speaking;
  const mutation = useOptimisticSessionPatch(session.session_id);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={
        "relative text-left rounded-lg overflow-hidden border transition-all " +
        // Selected gets a cyan ring; speaking gets the strong pulse glow
        // that's also used on CharacterStage for cross-surface consistency.
        (selected
          ? "border-cyan-600 ring-2 ring-cyan-700/40"
          : "border-zinc-800 hover:border-zinc-700") +
        " " +
        // Quiet breathing only on the selected card so eight idle cards
        // don't compete with the speaking-pulse for attention (UX B4).
        // Non-selected non-speaking cards stay still.
        (speaking
          ? "character-speak-pulse"
          : selected
          ? "character-breathe"
          : "")
      }
      style={
        speaking
          ? {
              boxShadow:
                "0 0 0 1px rgba(34, 211, 238, 0.5), 0 0 18px rgba(34, 211, 238, 0.4)",
            }
          : undefined
      }
    >
      {/* Speaking ribbon — keeps the visual signal even when the user
          mutes their own monitor (e.g. headphones-off). Gated to NON-
          selected cards: when the card is already the spotlight, the
          ring + spotlight pane already communicate focus, so a fourth
          signal (ribbon + glow + pulse + ring) is redundant noise. */}
      {speaking && !selected && (
        <div className="absolute top-1 left-1 z-10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest bg-cyan-700/90 text-white rounded">
          speaking
        </div>
      )}

      {/* Mute toggle — top-right corner. stopPropagation so clicking the
          mute icon doesn't ALSO select the card (clicks should be
          independent). */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          mutation.mutate({ enabled: muted });
        }}
        title={muted ? "Unmute this session" : "Mute this session"}
        className={
          "absolute top-1 right-1 z-10 px-1.5 py-0.5 text-[10px] rounded border " +
          (muted
            ? "bg-rose-900/80 border-rose-700 text-rose-100"
            : "bg-black/60 border-zinc-700 text-zinc-200 hover:bg-zinc-800")
        }
      >
        {muted ? "muted" : "mute"}
      </button>

      <div className="flex flex-col items-center justify-center p-4 gap-2 min-h-[180px] bg-gradient-to-br from-zinc-900 via-zinc-950 to-black">
        <CharacterAvatar
          name={char ? characterDisplayName(char) : "—"}
          characterId={char?.id ?? null}
          persona={char?.persona ?? null}
          size="lg"
        />
        <div className="text-center min-w-0 w-full">
          <div className="text-xs font-bold text-[var(--color-text-1)] truncate">
            {char ? characterDisplayName(char) : "(no character)"}
          </div>
          <div className="text-[10px] text-[var(--color-text-3)] truncate">
            {getSessionHeadline(session)}
          </div>
        </div>
      </div>
    </button>
  );
}

// ─── Spotlight (right pane) ───────────────────────────────────────────────

function SpotlightPane({ session }: { session: Session }) {
  const char = resolveAttachedCharacter(session.attached_character);
  const config = useSessionConfig(session.session_id);
  const mutation = useOptimisticSessionPatch(session.session_id);
  const muted = config.data?.enabled === false;
  const headline = getSessionHeadline(session);

  return (
    <div className="flex flex-col h-full">
      <header className="px-3 py-2 border-b border-zinc-800 space-y-1">
        <div className="flex items-center justify-between gap-2 min-w-0">
          <div className="min-w-0">
            <div className="text-sm font-bold text-[var(--color-text-1)] truncate">
              {char ? characterDisplayName(char) : "(no character)"}
            </div>
            <div className="text-[10px] text-[var(--color-text-3)] truncate">
              for {headline}
            </div>
          </div>
          <button
            type="button"
            onClick={() => mutation.mutate({ enabled: muted })}
            className={
              "text-[10px] px-2 py-0.5 rounded border shrink-0 " +
              (muted
                ? "bg-rose-900/40 text-rose-200 border-rose-700"
                : "bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800")
            }
          >
            {muted ? "unmute" : "mute"}
          </button>
        </div>
        {/* Speaking-mode quick toggle (Brief / Live). Pre-fills with
            session's current active_mode once the daemon exposes it on
            /api/sessions — until then it shows the resolved config value
            from useSessionConfig (also "unknown" if absent). */}
        <ModePicker
          value={config.data?.active_mode}
          onChange={(mode) => mutation.mutate({ active_mode: mode })}
        />
      </header>

      <div className="flex-1 overflow-y-auto">
        <NarrationFeed sessionId={session.session_id} />
      </div>
    </div>
  );
}
