import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * CCT-29: Per-session quick markup controls.
 *
 * Surfaces six high-impact markup forms grouped into three categories so a
 * listener can rapidly reshape what they're hearing from a specific session
 * without leaving the SessionCard. The remaining four forms (audible_block,
 * system_reminder, subagent_dispatch, long_numeral) live in the full
 * legacy /ui/#markup panel — kept linked at the bottom.
 *
 * Categorization is intentionally short-lived and refinable: edit
 * QUICK_GROUPS to retitle, regroup, or add/remove rows. The per-form
 * dropdown options come from the backend's FORM_KINDS contract via
 * MARKUP_KINDS below.
 */

type FormKey =
  | "code_fence"
  | "tool_output"
  | "inline_code"
  | "file_path"
  | "todo_update"
  | "plan_block";

const MARKUP_KINDS: Record<FormKey, string[]> = {
  code_fence: ["skip", "describe", "read"],
  tool_output: ["skip", "describe", "read"],
  inline_code: ["skip", "identifier_only", "read"],
  file_path: ["skip", "filename", "describe", "read"],
  todo_update: ["skip", "count_only", "itemize", "read"],
  plan_block: ["skip", "summarize", "read"],
};

const FORM_LABELS: Record<FormKey, string> = {
  code_fence: "Code blocks",
  tool_output: "Tool output",
  inline_code: "Inline `code`",
  file_path: "File paths",
  todo_update: "Todo updates",
  plan_block: "Plan blocks",
};

interface QuickGroup {
  title: string;
  hint: string;
  forms: FormKey[];
}

const QUICK_GROUPS: QuickGroup[] = [
  {
    title: "Listen density",
    hint: "Biggest verbosity dials — flip to skip when you want a quiet pass.",
    forms: ["code_fence", "tool_output"],
  },
  {
    title: "Inline detail",
    hint: "How aggressively short references get read aloud.",
    forms: ["inline_code", "file_path"],
  },
  {
    title: "Structural pauses",
    hint: "How multi-line structures get summarized or skipped.",
    forms: ["todo_update", "plan_block"],
  },
];

interface Treatment {
  kind: string;
  params?: Record<string, unknown>;
}

type MarkupConfig = Record<string, Treatment>;

interface Props {
  sessionId: string;
}

export function SessionMarkupQuick({ sessionId }: Props) {
  const qc = useQueryClient();

  // Global resolved markup config = per-session baseline (mode preset + any
  // global overrides). Per-session overrides layer on top via overlay PUT.
  const { data: globalCfg } = useQuery<MarkupConfig>({
    queryKey: ["markup-config"],
    queryFn: async () => {
      const r = await fetch("/api/markup/config");
      if (!r.ok) throw new Error("markup config fetch failed");
      return r.json();
    },
    staleTime: 30_000,
  });

  const setForm = useMutation({
    mutationFn: (input: { form: FormKey; kind: string }) =>
      api.putOverlay(sessionId, {
        markup: { [input.form]: { kind: input.kind } },
      } as never),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["session-config", sessionId] });
    },
  });

  return (
    <details className="text-sm border border-slate-800 rounded bg-slate-950/40">
      <summary className="cursor-pointer px-3 py-1.5 select-none flex items-center justify-between hover:bg-slate-900/50 rounded">
        <span className="font-medium text-slate-200">Markup</span>
        <span className="text-xs text-slate-500">quick toggles ⌄</span>
      </summary>
      <div className="p-3 space-y-4">
        {QUICK_GROUPS.map((group) => (
          <fieldset key={group.title}>
            <legend className="text-xs uppercase tracking-wide text-slate-400 font-semibold mb-1">
              {group.title}
            </legend>
            <p className="text-xs text-slate-500 mb-2">{group.hint}</p>
            <div className="space-y-1">
              {group.forms.map((form) => (
                <MarkupRow
                  key={form}
                  form={form}
                  current={globalCfg?.[form]?.kind ?? "—"}
                  onChange={(kind) => setForm.mutate({ form, kind })}
                  saving={setForm.isPending}
                />
              ))}
            </div>
          </fieldset>
        ))}
        <div className="pt-2 border-t border-slate-800 text-right">
          <a
            href="/ui/#markup"
            target="_blank"
            rel="noopener"
            className="text-xs text-cyan-400 hover:underline"
          >
            Full markup panel (all 10 forms) →
          </a>
        </div>
      </div>
    </details>
  );
}

interface RowProps {
  form: FormKey;
  current: string;
  onChange: (kind: string) => void;
  saving: boolean;
}

function MarkupRow({ form, current, onChange, saving }: RowProps) {
  const allowed = MARKUP_KINDS[form];
  return (
    <label className="flex items-center justify-between gap-2">
      <span className="text-slate-300">{FORM_LABELS[form]}</span>
      <select
        className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-xs text-slate-200"
        value={allowed.includes(current) ? current : allowed[0]}
        onChange={(e) => onChange(e.target.value)}
        disabled={saving}
        aria-label={`${FORM_LABELS[form]} treatment`}
      >
        {allowed.map((k) => (
          <option key={k} value={k}>
            {k.replace(/_/g, " ")}
          </option>
        ))}
      </select>
    </label>
  );
}
