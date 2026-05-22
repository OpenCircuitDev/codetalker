type Mode = "direct" | "brief" | "live" | "trigger" | "critical_only";
const MODES: Mode[] = ["direct", "brief", "live", "trigger", "critical_only"];

const MODE_LABELS: Record<Mode, { label: string; help?: string }> = {
  direct: { label: "Direct" },
  brief: { label: "Brief" },
  live: { label: "Live" },
  trigger: { label: "Trigger" },
  critical_only: { label: "Critical only", help: "Silent unless something breaks, blocks, or needs your input." },
};

type Props = {
  value: Mode | string | undefined;
  onChange: (mode: Mode) => void;
};

export function ModePicker({ value, onChange }: Props) {
  return (
    <select
      className="bg-slate-900 border border-slate-700 rounded text-xs px-2 py-1 font-mono"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value as Mode)}
      title={value && MODE_LABELS[value as Mode]?.help}
    >
      {!MODES.includes(value as Mode) && <option value="">(unknown)</option>}
      {MODES.map((m) => (
        <option key={m} value={m} title={MODE_LABELS[m]?.help}>
          {MODE_LABELS[m]?.label || m}
        </option>
      ))}
    </select>
  );
}
