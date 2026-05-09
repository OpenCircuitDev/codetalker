// Phase 25b — MeshGenerator: pick a 3D provider, type a prompt, kick a job,
// poll until done. Surfaces job status inline; refreshes characters cache on
// completion so CharacterDetail picks up the new mesh_path.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface Provider {
  name: string;
  configured: boolean;
}

interface MeshJob {
  job_id: string;
  provider: string;
  character_id: string;
  prompt: string;
  status: string;
  provider_job_id: string | null;
  model_path: string | null;
  progress: number | null;
  error: string | null;
}

async function listProviders(): Promise<Provider[]> {
  const r = await fetch("/api/mesh-providers");
  if (!r.ok) return [];
  return r.json();
}

async function startMeshJob(input: {
  character_id: string;
  provider: string;
  prompt: string;
  image_url?: string;
}): Promise<{ job_id: string; status: string }> {
  const r = await fetch("/api/mesh-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `start failed: ${r.status}`);
  }
  return r.json();
}

async function pollMeshJob(jobId: string): Promise<MeshJob> {
  const r = await fetch(`/api/mesh-jobs/${jobId}/poll`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function MeshGenerator({ characterId }: { characterId: string }) {
  const [provider, setProvider] = useState("hyper3d");
  const [prompt, setPrompt] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<MeshJob | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qc = useQueryClient();
  const { data: providers = [] } = useQuery({
    queryKey: ["mesh-providers"],
    queryFn: listProviders,
  });

  // Cleanup interval on unmount
  useEffect(() => {
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, []);

  const start = useMutation({
    mutationFn: () =>
      startMeshJob({ character_id: characterId, provider, prompt }),
    onSuccess: (j) => {
      setJobId(j.job_id);
      setJob(null);
      if (tickRef.current) clearInterval(tickRef.current);
      tickRef.current = setInterval(async () => {
        try {
          const fresh = await pollMeshJob(j.job_id);
          setJob(fresh);
          if (fresh.status === "succeeded" || fresh.status === "failed") {
            if (tickRef.current) clearInterval(tickRef.current);
            tickRef.current = null;
            qc.invalidateQueries({ queryKey: ["characters"] });
          }
        } catch {
          if (tickRef.current) clearInterval(tickRef.current);
          tickRef.current = null;
        }
      }, 3000);
    },
  });

  const status = job?.status ?? (jobId ? "queued" : "");

  return (
    <section className="space-y-2 border-t border-zinc-800 pt-3">
      <h3 className="font-bold text-sm">Generate 3D model</h3>
      <select
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1"
      >
        {providers.length === 0 && (
          <option value="hyper3d">hyper3d</option>
        )}
        {providers.map((p) => (
          <option key={p.name} value={p.name} disabled={!p.configured}>
            {p.name}
            {p.configured ? "" : " (no key)"}
          </option>
        ))}
      </select>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="describe the model"
        className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 h-20"
      />
      <button
        onClick={() => start.mutate()}
        disabled={!prompt || start.isPending}
        className="px-3 py-1 bg-cyan-600 text-white rounded disabled:opacity-50"
      >
        {start.isPending ? "Starting..." : "Generate"}
      </button>
      {start.isError && (
        <p className="text-rose-400 text-xs">{(start.error as Error)?.message}</p>
      )}
      {jobId && (
        <p className="text-sm text-zinc-400">
          job {jobId}: <strong>{status}</strong>
          {job?.progress != null && status === "running" && (
            <span> ({Math.round(job.progress * 100)}%)</span>
          )}
          {job?.error && <span className="text-rose-400"> — {job.error}</span>}
        </p>
      )}
    </section>
  );
}
