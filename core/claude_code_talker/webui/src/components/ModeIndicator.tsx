type Props = { mode: string | undefined };

export function ModeIndicator({ mode }: Props) {
  return (
    <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-200 font-mono">
      {mode ?? "unknown"}
    </span>
  );
}
