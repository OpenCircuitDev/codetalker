// Piper voice manager — browse, preview, install, and remove local
// piper voices from the curated rhasspy/piper-voices catalog. Lives in
// the Preferences tab as a collapsible section; renders two lists side
// by side: installed (with preview + remove) and available (with
// preview-on-install + install).
//
// Daemon endpoints driving this:
//   GET    /api/piper/catalog           — list with `installed` flag
//   POST   /api/piper/install           — body {name}, downloads voice
//   DELETE /api/piper/voices/{name}     — removes voice from disk
//   POST   /api/piper/preview/{name}    — synth + play sample
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

type CatalogEntry = {
  name: string;
  lang: string;
  speaker: string;
  gender: string;
  quality: string;
  size_mb: number;
  installed: boolean;
  curated?: boolean;
};

async function fetchCatalog(): Promise<CatalogEntry[]> {
  const r = await fetch("/api/piper/catalog");
  if (!r.ok) throw new Error(`catalog fetch failed: ${r.status}`);
  return r.json();
}

async function installVoice(name: string): Promise<void> {
  const r = await fetch("/api/piper/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`install failed (${r.status}): ${t}`);
  }
}

async function uninstallVoice(name: string): Promise<void> {
  const r = await fetch(`/api/piper/voices/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`uninstall failed (${r.status}): ${t}`);
  }
}

async function previewVoice(name: string): Promise<void> {
  const r = await fetch(`/api/piper/preview/${encodeURIComponent(name)}`, {
    method: "POST",
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`preview failed (${r.status}): ${t}`);
  }
  // The endpoint plays on the desktop AND returns wav bytes; we ignore
  // the bytes here because Windows playback is already triggered by the
  // daemon side. (Future: pipe the bytes into an <audio> tag if browser
  // playback is preferred.)
}

export function VoiceManager() {
  const qc = useQueryClient();
  const catalog = useQuery({
    queryKey: ["piper-catalog"],
    queryFn: fetchCatalog,
    staleTime: 30_000,
  });

  // Surfaces per-row errors next to the action that failed. Cleared on
  // any successful action against the same row.
  const [errs, setErrs] = useState<Record<string, string>>({});
  const setErr = (name: string, msg: string | null) =>
    setErrs((e) => {
      const next = { ...e };
      if (msg) next[name] = msg;
      else delete next[name];
      return next;
    });

  // Track in-flight ops per row so we can show spinners + disable buttons
  // without blocking other rows.
  const [busy, setBusy] = useState<Record<string, "install" | "uninstall" | "preview">>({});

  const installMut = useMutation({
    mutationFn: installVoice,
    onMutate: (name) => {
      setBusy((b) => ({ ...b, [name]: "install" }));
      setErr(name, null);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["piper-catalog"] }),
    onError: (e: Error, name) => setErr(name, e.message),
    onSettled: (_d, _e, name) =>
      setBusy((b) => {
        const next = { ...b };
        delete next[name];
        return next;
      }),
  });
  const uninstallMut = useMutation({
    mutationFn: uninstallVoice,
    onMutate: (name) => {
      setBusy((b) => ({ ...b, [name]: "uninstall" }));
      setErr(name, null);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["piper-catalog"] }),
    onError: (e: Error, name) => setErr(name, e.message),
    onSettled: (_d, _e, name) =>
      setBusy((b) => {
        const next = { ...b };
        delete next[name];
        return next;
      }),
  });
  const previewMut = useMutation({
    mutationFn: previewVoice,
    onMutate: (name) => {
      setBusy((b) => ({ ...b, [name]: "preview" }));
      setErr(name, null);
    },
    onError: (e: Error, name) => setErr(name, e.message),
    onSettled: (_d, _e, name) =>
      setBusy((b) => {
        const next = { ...b };
        delete next[name];
        return next;
      }),
  });

  const entries = catalog.data ?? [];
  const installed = entries.filter((e) => e.installed);
  const available = entries.filter((e) => !e.installed);

  return (
    <section className="space-y-3">
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-bold text-[var(--color-text-1)]">
          Piper voices
        </h3>
        <span className="text-[10px] text-[var(--color-text-3)]">
          Local TTS · download from rhasspy/piper-voices on HuggingFace
        </span>
      </header>

      {catalog.isError && (
        <p className="text-rose-400 text-xs">
          Failed to load catalog: {(catalog.error as Error)?.message}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <VoiceList
          title={`Installed (${installed.length})`}
          empty="No piper voices installed yet."
          entries={installed}
          showRemove
          errs={errs}
          busy={busy}
          onPreview={(n) => previewMut.mutate(n)}
          onInstall={(n) => installMut.mutate(n)}
          onUninstall={(n) => uninstallMut.mutate(n)}
        />
        <VoiceList
          title={`Available (${available.length})`}
          empty="All curated voices are already installed."
          entries={available}
          errs={errs}
          busy={busy}
          onPreview={(n) => previewMut.mutate(n)}
          onInstall={(n) => installMut.mutate(n)}
          onUninstall={(n) => uninstallMut.mutate(n)}
        />
      </div>

      <p className="text-[10px] text-[var(--color-text-3)] italic">
        Preview plays a 2-second sample on this machine's desktop audio.
        Install downloads ~25-110 MB to <code>~/.claude/scripts/piper/voices/</code>.
      </p>
    </section>
  );
}

type VoiceListProps = {
  title: string;
  empty: string;
  entries: CatalogEntry[];
  showRemove?: boolean;
  errs: Record<string, string>;
  busy: Record<string, "install" | "uninstall" | "preview">;
  onPreview: (name: string) => void;
  onInstall: (name: string) => void;
  onUninstall: (name: string) => void;
};

function VoiceList({
  title, empty, entries, showRemove, errs, busy,
  onPreview, onInstall, onUninstall,
}: VoiceListProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-[10px] uppercase tracking-wider text-[var(--color-text-2)] font-semibold">
        {title}
      </h4>
      {entries.length === 0 ? (
        <p className="text-xs text-[var(--color-text-3)] italic">{empty}</p>
      ) : (
        <ul className="space-y-1">
          {entries.map((e) => {
            const action = busy[e.name];
            const isInstall = action === "install";
            const isPreview = action === "preview";
            const isUninstall = action === "uninstall";
            return (
              <li
                key={e.name}
                className="flex items-center gap-2 px-2 py-1.5 bg-zinc-900/70 border border-zinc-800 rounded text-xs"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-mono truncate text-[var(--color-text-1)]">
                    {e.name}
                  </div>
                  <div className="text-[10px] text-[var(--color-text-3)] flex gap-2 items-center mt-0.5">
                    {e.lang && <span>{e.lang}</span>}
                    {e.gender && <span>· {e.gender}</span>}
                    {e.quality && <span>· {e.quality}</span>}
                    {e.size_mb > 0 && <span>· {e.size_mb} MB</span>}
                    {e.curated === false && (
                      <span className="text-amber-400">· custom</span>
                    )}
                  </div>
                  {errs[e.name] && (
                    <div className="text-[10px] text-rose-400 mt-0.5 break-all">
                      {errs[e.name]}
                    </div>
                  )}
                </div>
                <div className="flex gap-1 shrink-0">
                  {e.installed && (
                    <button
                      type="button"
                      onClick={() => onPreview(e.name)}
                      disabled={!!action}
                      className="px-2 py-0.5 rounded border bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-[10px] disabled:opacity-40 disabled:cursor-not-allowed"
                      title="Play a short sample on desktop"
                    >
                      {isPreview ? "…" : "▶ test"}
                    </button>
                  )}
                  {!e.installed && (
                    <button
                      type="button"
                      onClick={() => onInstall(e.name)}
                      disabled={!!action}
                      className="px-2 py-0.5 rounded border bg-cyan-800/80 border-cyan-700 hover:bg-cyan-700 text-[10px] text-white disabled:opacity-40 disabled:cursor-not-allowed"
                      title={`Download ${e.size_mb} MB from HuggingFace`}
                    >
                      {isInstall ? "downloading…" : "⬇ install"}
                    </button>
                  )}
                  {showRemove && e.installed && (
                    <button
                      type="button"
                      onClick={() => onUninstall(e.name)}
                      disabled={!!action}
                      className="px-2 py-0.5 rounded border bg-zinc-900 border-rose-900/40 text-rose-300 hover:bg-rose-900/40 hover:border-rose-700 text-[10px] disabled:opacity-40 disabled:cursor-not-allowed"
                      title="Delete voice files from disk"
                    >
                      {isUninstall ? "removing…" : "remove"}
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
