import type { Session } from "../types";
import { useSessionConfig } from "../hooks/useSessionConfig";
import { ProjectBadge } from "./ProjectBadge";
import { ProfileBadge } from "./ProfileBadge";
import { SessionControls } from "./SessionControls";

type Props = { session: Session };

export function SessionCard({ session }: Props) {
  const { data: config } = useSessionConfig(session.session_id);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <ProjectBadge slug={session.project_slug} lastModified={session.last_modified} />
        <ProfileBadge profile={session.attached_profile} />
      </div>
      <div className="text-sm text-slate-200 line-clamp-2">{session.display_name}</div>
      <SessionControls sessionId={session.session_id} config={config} />
    </div>
  );
}
