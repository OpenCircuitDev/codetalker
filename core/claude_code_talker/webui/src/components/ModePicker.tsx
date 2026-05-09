type Mode = "direct" | "brief" | "live" | "trigger";
const MODES: Mode[] = ["direct", "brief", "live", "trigger"];

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
    >
      {!MODES.includes(value as Mode) && <option value="">(unknown)</option>}
      {MODES.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
    </select>
  );
}
