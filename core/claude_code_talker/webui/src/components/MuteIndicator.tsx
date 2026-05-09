type Props = { muted: boolean };

export function MuteIndicator({ muted }: Props) {
  return (
    <span
      className={
        "text-xs px-2 py-0.5 rounded font-mono " +
        (muted ? "bg-rose-900/40 text-rose-200" : "bg-slate-700/40 text-slate-300")
      }
    >
      {muted ? "muted" : "audible"}
    </span>
  );
}
