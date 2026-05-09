// Phase 27 — SessionCard 4-zone layout: identity / chips / live ticker / controls.
// Keeps backwards-compat with project/profile badges so existing telemetry doesn't disappear.
import { motion } from "framer-motion";
import type { Session } from "../types";
import { useSessionConfig } from "../hooks/useSessionConfig";
import { cardEntry } from "../theme/motion";
import { CharacterAvatar } from "./CharacterAvatar";
import { LiveTicker } from "./LiveTicker";
import { SpeakingDot } from "./SpeakingDot";
import { ProjectBadge } from "./ProjectBadge";
import { ProfileBadge } from "./ProfileBadge";
import { SessionControls } from "./SessionControls";

type Props = { session: Session };

export function SessionCard({ session }: Props) {
  const { data: config } = useSessionConfig(session.session_id);
  const muted = config?.enabled === false || session.enabled === false || !!session.is_muted;
  const char = session.attached_character;
  const events = session.events ?? [];
  // CCT-28 fix: trust the backend's display_name (already resolves
  // custom_title > vscode_label > slug > c.title > project_slug). Reading
  // session.title first overrode `/title` renames whenever Claude Code
  // emitted an ai-title, causing visible flicker as catalog scans landed.
  const headline = session.display_name || session.session_id.slice(0, 8);

  return (
    <motion.article
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

      {/* Subtitle: show display_name only when distinct from the headline. */}
      {session.display_name && session.display_name !== headline && (
        <div className="text-sm text-[var(--color-text-2)] line-clamp-2">
          {session.display_name}
        </div>
      )}

      {/* Zone 3: live ticker (only when events known) */}
      {events.length > 0 && (
        <div className="h-32 bg-[var(--color-surface-2)] rounded">
          <LiveTicker events={events} maxEvents={20} />
        </div>
      )}

      {/* Zone 4: controls */}
      <SessionControls sessionId={session.session_id} config={config} />
    </motion.article>
  );
}
