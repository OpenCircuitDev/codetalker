type Props = { profile: string | null };

export function ProfileBadge({ profile }: Props) {
  if (!profile) {
    return <span className="text-xs text-slate-500 italic">no profile</span>;
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded bg-indigo-900/40 text-indigo-200">
      {profile}
    </span>
  );
}
