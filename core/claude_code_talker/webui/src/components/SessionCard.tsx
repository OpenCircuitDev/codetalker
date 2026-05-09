// Phase 27 — SessionCard 4-zone layout: identity / chips / live ticker / controls.
// Keeps backwards-compat with project/profile badges so existing telemetry doesn't disappear.
import { memo } from "react";
import { motion } from "framer-motion";
import type { Session } from "../types";
import { useSessionConfig } from "../hooks/useSessionConfig";
import { cardEntry } from "../theme/motion";
import { CharacterAvatar } from "./CharacterAvatar";
import { SpeakingDot } from "./SpeakingDot";
import { ProjectBadge } from "./ProjectBadge";
import { ProfileBadge } from "./ProfileBadge";
import { SessionControls } from "./SessionControls";
import { SessionMarkupQuick } from "./SessionMarkupQuick";

type Props = { session: Session };

function SessionCardImpl({ session }: Props) {
  const { data: config } = useSessionConfig(session.session_id);
  // CCT-28 cat 3: muted is canonically derived from the post-overlay-resolved
  // config's `enabled` flag. session.enabled / session.is_muted are kept as
  // fallbacks only when config hasn't loaded yet (first paint), so the card
  // doesn't visibly flip muted-styling on initial config arrival.
  const muted =
    config !== undefined
      ? config.enabled === false
      : session.enabled === false || !!session.is_muted;
  const char = session.attached_character;
  // CCT-28 fix: trust the backend's display_name (already resolves
  // custom_title > vscode_label > slug > c.title > project_slug). Reading
  // session.title first overrode `/title` renames whenever Claude Code
  // emitted an ai-title, causing visible flicker as catalog scans landed.
  const headline = session.display_name || session.session_id.slice(0, 8);

  return (
    <motion.article
      layout
      variants={cardEntry}
      initial="initial"
      animate="animate"
      exit="exit"
      className={
        "rounded-lg border border-l-4 p-3 flex flex-col gap-2 transition-colors shadow-soft-1 " +
        (muted
          ? "border-zinc-800 border-l-rose-500 bg-rose-950/20"
          : "border-zinc-800 border-l-emerald-500 bg-[var(--color-surface-1)]")
      }
      title={muted ? "Muted — narration suppressed" : "Audible — narration playing"}
    >
      {/* Zone 1: identity */}
      <header className="flex items-center gap-3">
        {char ? (
          <CharacterAvatar
            name={char.display_name}
            meshUrl={char.mesh_path}
            persona={char.persona ?? null}
            size="md"
          />
        ) : null}
        <div className="flex-1 min-w-0">
          <h3 className="font-bold truncate text-[var(--color-text-1)]">{headline}</h3>
          <p className="text-xs text-[var(--color-text-3)] truncate">
            {session.cwd || "—"}
          </p>
        </div>
        <SpeakingDot active={!!session.is_speaking} />
      </header>

      {/* Zone 2: chips (project, profile, character, mode, muted) */}
      <div className="flex items-center gap-2 text-xs flex-wrap">
        <ProjectBadge slug={session.project_slug} lastModified={session.last_modified} />
        <ProfileBadge profile={session.attached_profile} />
        {char && (
          <span className="px-2 py-0.5 rounded bg-cyan-900 text-cyan-200">
            {char.display_name}
          </span>
        )}
        {session.mode && (
          <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-200">
            {session.mode}
          </span>
        )}
        {muted && (
          <span className="px-2 py-0.5 rounded bg-rose-900 text-rose-200">muted</span>
        )}
      </div>

      {/* Zone 4: controls (mute / mode / voice / cadence) + per-session markup quick toggles */}
      <SessionControls sessionId={session.session_id} config={config} />
      <SessionMarkupQuick sessionId={session.session_id} />
    </motion.article>
  );
}

// CCT-28: shallow comparator so refetched lists with reference-equal session
// objects (post keepPreviousData) skip rerendering each card. Compare only
// the fields we actually render.
function sessionEqual(prev: Props, next: Props): boolean {
  const a = prev.session;
  const b = next.session;
  if (a === b) return true;
  return (
    a.session_id === b.session_id &&
    a.display_name === b.display_name &&
    a.project_slug === b.project_slug &&
    a.cwd === b.cwd &&
    a.last_modified === b.last_modified &&
    a.is_live === b.is_live &&
    a.enabled === b.enabled &&
    a.attached_profile === b.attached_profile &&
    a.is_speaking === b.is_speaking &&
    a.is_muted === b.is_muted &&
    a.mode === b.mode &&
    a.attached_character === b.attached_character
  );
}

export const SessionCard = memo(SessionCardImpl, sessionEqual);
