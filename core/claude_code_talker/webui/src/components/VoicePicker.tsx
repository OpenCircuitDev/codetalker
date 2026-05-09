import { useQuery } from "@tanstack/react-query";

type Props = {
  value: string | undefined;
  onChange: (voice: string) => void;
};

export function VoicePicker({ value, onChange }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["voices"],
    queryFn: async () => {
      const r = await fetch("/api/voices");
      if (!r.ok) throw new Error("failed to load voices");
      return r.json() as Promise<{ name: string }[] | string[]>;
    },
    staleTime: 60_000,
  });

  const voices = (data ?? []).map((v: any) =>
    typeof v === "string" ? v : v.name
  );

  return (
    <select
      className="bg-slate-900 border border-slate-700 rounded text-xs px-2 py-1 font-mono max-w-[12rem]"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      disabled={isLoading}
    >
      {!voices.includes(value ?? "") && (
        <option value="">{value ?? "(default)"}</option>
      )}
      {voices.map((name) => (
        <option key={name} value={name}>
          {name}
        </option>
      ))}
    </select>
  );
}
