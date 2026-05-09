// CCT-28 cat 4 — Per-session cadence picker. Cadence applies only to live
// mode but is exposed alongside mute / mode / voice for parity with the
// legacy /ui#sessions panel and the new SessionMarkupQuick controls.
//
// Backend-canonical values (server.tts_set_cadence): periodic |
// per_tool_call | per_cluster | significant_only | hybrid. Cadence is
// nested under cfg.live.cadence in the resolved config and therefore in
// the overlay payload.
type Cadence =
  | "periodic"
  | "per_tool_call"
  | "per_cluster"
  | "significant_only"
  | "hybrid";

const CADENCES: Cadence[] = [
  "periodic",
  "per_tool_call",
  "per_cluster",
  "significant_only",
  "hybrid",
];

const LABELS: Record<Cadence, string> = {
  periodic: "periodic",
  per_tool_call: "per tool",
  per_cluster: "per cluster",
  significant_only: "significant",
  hybrid: "hybrid",
};

type Props = {
  value: Cadence | string | undefined;
  onChange: (cadence: Cadence) => void;
};

export function CadencePicker({ value, onChange }: Props) {
  return (
    <select
      aria-label="Cadence"
      title="Live-mode cadence"
      className="bg-slate-900 border border-slate-700 rounded text-xs px-2 py-1 font-mono"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value as Cadence)}
    >
      {!CADENCES.includes(value as Cadence) && (
        <option value="">(unknown)</option>
      )}
      {CADENCES.map((c) => (
        <option key={c} value={c}>
          {LABELS[c]}
        </option>
      ))}
    </select>
  );
}
