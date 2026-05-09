type Props = { slug: string; lastModified: number };

function relativeTime(epochSec: number): string {
  const sec = Math.max(0, Date.now() / 1000 - epochSec);
  if (sec < 60) return `${Math.floor(sec)} second${sec < 1.5 ? "" : "s"} ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)} minutes ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} hours ago`;
  return `${Math.floor(sec / 86400)} days ago`;
}

export function ProjectBadge({ slug, lastModified }: Props) {
  return (
    <div className="flex flex-col text-xs">
      <span className="font-mono text-slate-300">{slug}</span>
      <span className="text-slate-500">{relativeTime(lastModified)}</span>
    </div>
  );
}
