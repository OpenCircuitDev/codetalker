// Phase 27 — Preferences panel: sound effects, density, accent.
// CCT-31 — adds AR Companion pairing QR generator.
// v0.1.0 unification — adds "Audio defaults" section that flips the
// fleet-level companion_suppress_desktop flag (the third "obvious
// toggle" called out in the unification spec).
import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePreferences } from "../hooks/usePreferences";
import { api } from "../api/client";

export function PreferencesPanel() {
  const { prefs, setPref } = usePreferences();
  const [pairToken, setPairToken] = useState<string | null>(null);
  const [pairDaemonUrl, setPairDaemonUrl] = useState<string | null>(null);
  const [pairing, setPairing] = useState(false);
  const [pairError, setPairError] = useState<string | null>(null);

  const qc = useQueryClient();
  const audioDefaults = useQuery({
    queryKey: ["audio-defaults"],
    queryFn: api.audioDefaults,
    staleTime: 10_000,
  });
  const audioDefaultsMutation = useMutation({
    mutationFn: api.setAudioDefaults,
    onSuccess: (data) => qc.setQueryData(["audio-defaults"], data),
  });

  const issueToken = async () => {
    setPairing(true);
    setPairError(null);
    try {
      const r = await fetch("/api/companion/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: navigator.userAgent.slice(0, 40) }),
      });
      if (!r.ok) {
        setPairError(`HTTP ${r.status}`);
        return;
      }
      const data = await r.json();
      setPairToken(data.token);
      // CCT-31: prefer the server-resolved daemon_url. The server picked
      // a LAN/Tailscale-reachable address; window.location.host may be
      // 127.0.0.1, which would put loopback in the QR — phones can't
      // reach the PC's loopback, and pairing would silently fail.
      setPairDaemonUrl(data.daemon_url ?? `http://${window.location.host}`);
    } catch (e) {
      setPairError(String(e));
    } finally {
      setPairing(false);
    }
  };

  const pairPayload = pairToken && pairDaemonUrl
    ? JSON.stringify({
        daemon_url: pairDaemonUrl,
        pairing_token: pairToken,
      })
    : null;

  return (
    <section className="space-y-4 p-4 bg-[var(--color-surface-1)] rounded-lg border border-zinc-800">
      <h2 className="font-bold text-[var(--color-text-1)]">Preferences</h2>

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={prefs.soundEffects}
          onChange={(e) => setPref("soundEffects", e.target.checked)}
        />
        <span>Sound effects</span>
        <span className="text-xs text-[var(--color-text-3)]">(off by default)</span>
      </label>

      <fieldset className="space-y-1">
        <legend className="text-sm text-[var(--color-text-2)]">Density</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="density"
            checked={prefs.density === "comfortable"}
            onChange={() => setPref("density", "comfortable")}
          />
          <span>Comfortable</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="density"
            checked={prefs.density === "compact"}
            onChange={() => setPref("density", "compact")}
          />
          <span>Compact</span>
        </label>
      </fieldset>

      <fieldset className="space-y-1">
        <legend className="text-sm text-[var(--color-text-2)]">Accent</legend>
        {(["cyan", "emerald", "violet"] as const).map((a) => (
          <label key={a} className="flex items-center gap-2">
            <input
              type="radio"
              name="accent"
              checked={prefs.accent === a}
              onChange={() => setPref("accent", a)}
            />
            <span className="capitalize">{a}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className="space-y-2 pt-2 border-t border-zinc-800">
        <legend className="text-sm font-bold text-[var(--color-text-1)]">
          Audio defaults
        </legend>
        <p className="text-xs text-[var(--color-text-3)]">
          Fleet-level default for sessions without an explicit override.
          Per-session destinations on the Sessions tab take precedence.
        </p>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!audioDefaults.data?.companion_suppress_desktop}
            disabled={audioDefaultsMutation.isPending || audioDefaults.isLoading}
            onChange={(e) => audioDefaultsMutation.mutate(e.target.checked)}
            className="mt-0.5"
          />
          <div>
            <div className="text-sm">Companion takes over desktop</div>
            <div className="text-[11px] text-[var(--color-text-3)]">
              When on, default audio routes only to {`{phone, glasses}`}.
              When off, all three sinks play by default.
            </div>
          </div>
        </label>
        {audioDefaults.data && (
          <div className="text-[11px] text-[var(--color-text-3)] font-mono">
            current default outputs: [{audioDefaults.data.default_outputs.join(", ")}]
          </div>
        )}
        {audioDefaultsMutation.isError && (
          <div className="text-[11px] text-rose-400">
            Failed to save: {(audioDefaultsMutation.error as Error).message}
          </div>
        )}
      </fieldset>

      <fieldset className="space-y-2 pt-2 border-t border-zinc-800">
        <legend className="text-sm font-bold text-[var(--color-text-1)]">AR Companion</legend>
        <p className="text-xs text-[var(--color-text-3)]">
          Pair the codetalker Android app on your XREAL Beam Pro by scanning a QR token
          from this device.
        </p>
        <button
          type="button"
          onClick={issueToken}
          disabled={pairing}
          className="px-3 py-1 bg-cyan-600 text-white rounded disabled:opacity-50"
        >
          {pairing ? "Issuing..." : "Issue pairing token"}
        </button>
        {pairError && (
          <p className="text-xs text-red-400">Pairing failed: {pairError}</p>
        )}
        {pairPayload && (
          <div className="mt-2 space-y-2">
            <div className="inline-block bg-white p-3 rounded">
              <QRCodeSVG value={pairPayload} size={192} />
              <p className="text-zinc-700 text-xs mt-2 max-w-[192px]">
                Scan with the codetalker Android app
              </p>
            </div>
            <div className="text-xs space-y-0.5 max-w-md">
              <div className="flex gap-2">
                <span className="text-[var(--color-text-3)] w-20 shrink-0">URL:</span>
                <code className="text-cyan-300 break-all">{pairDaemonUrl}</code>
              </div>
              <div className="flex gap-2">
                <span className="text-[var(--color-text-3)] w-20 shrink-0">Token:</span>
                <code className="text-cyan-300 break-all">{pairToken}</code>
              </div>
              {pairDaemonUrl?.includes("127.0.0.1") && (
                <p className="text-xs text-amber-400 mt-1">
                  ⚠ daemon resolved to loopback — set CCT_DAEMON_HOST=0.0.0.0 and restart so phones on LAN can reach this URL.
                </p>
              )}
            </div>
          </div>
        )}
      </fieldset>

      {/* VoiceManager moved to its own top-level tab "Voices" for
          easier discovery. This Preferences section is now just a
          pointer so users who land here aren't confused. */}
      <fieldset className="border border-zinc-800 rounded p-4 mt-6">
        <legend className="text-xs uppercase tracking-wider text-[var(--color-text-2)] px-2">
          Voice library
        </legend>
        <p className="text-xs text-[var(--color-text-3)]">
          Voice install / preview / remove moved to the{" "}
          <button
            type="button"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("cct:navigate", { detail: { tab: "voices" } })
              )
            }
            className="text-cyan-400 hover:underline"
          >
            Voices tab
          </button>{" "}
          for easier discovery.
        </p>
      </fieldset>
    </section>
  );
}
