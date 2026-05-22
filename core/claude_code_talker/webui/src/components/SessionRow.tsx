// v0.1.0 unification — compact session row mirroring Pro Android
// SessionListScreen. Replaces SessionCard's 4-zone block when the
// SessionGrid is in the unified layout.
//
// Unified flash logic:
//   - Strong pulse when `is_speaking` (canonical TTS-in-flight signal)
//   - Ambient pulse when last hook event was within 10s (recency proxy)
//   - Steady green outline when this is the companion's currently-active session
import { motion } from "framer-motion";
import type { Session, AudioOutput, NarrationEvent } from "../types";
import {
  resolveAttachedCharacter,
  characterDisplayName,
  getSessionHeadline,
} from "../types";
import { useSessionConfig } from "../hooks/useSessionConfig";
import { useOptimisticSessionPatch } from "../hooks/useOptimisticSessionPatch";
import { useNarrationStream } from "../hooks/useNarrationStream";

type Props = {
  session: Session;
  isCompanionActive?: boolean;
  isOpen?: boolean;
  onOpen: () => void;
};

export function SessionRow({ session, isCompanionActive, isOpen, onOpen }: Props) {
  const { data: config } = useSessionConfig(session.session_id);
  // v0.1.0 unification — single shared optimistic-patch hook handles
  // all mutations on this row (mute, mode, pin) with cache rollback
  // semantics. Was 100+ lines of duplicated mutation config.
  const patchMutation = useOptimisticSessionPatch(session.session_id);
  const muteMutation = patchMutation;
  const modeMutation = patchMutation;
  const pinMutation = patchMutation;

  // "What just happened?" recap card — subscribe to narration stream
  // for this session only. Filter to entries within the last 5 minutes.
  const narrationEvents = useNarrationStream(session.session_id, 10);
  const latestNarration = getLatestNarrationWithin5min(narrationEvents);

  const muted = config?.enabled === false;
  const headline = getSessionHeadline(session);
  const mode = config?.active_mode || session.mode || "brief";
  const character = resolveAttachedCharacter(session.attached_character);
  const pinned = !!session.pinned;

  // Recency: animate ambient ring when something happened within ~10s.
  // session.last_modified is in epoch seconds (server) but we treat it
  // as a recency-only signal — drift is fine.
  const recencyMs = Date.now() - session.last_modified * 1000;
  const isRecent = recencyMs >= 0 && recencyMs < 10_000;
  const isSpeaking = !!session.is_speaking;
  const auto = !!session.auto_mode_enabled;
  const outputs = session.audio_outputs;

  // v0.1.0 unification (card-style restyle) — promotes from compact
  // 1-line row to a 2-section card. Top section is the identity (dot +
  // name + pin glyph), bottom section is always-visible controls
  // (mode picker, mute, destination pips, pin button). The hover-reveal
  // pattern crushed the name span on narrow viewports — explicit space
  // per element + always-visible controls is more readable for users
  // who are choosing between a small number of sessions per group.
  return (
    // role="button" + tabIndex + key handler instead of <button> because
    // a real <button> cannot legally wrap the inner mute/mode/destination
    // <button>s — that produces a hydration error and breaks click
    // propagation for nested controls.
    <motion.div
      role="button"
      tabIndex={0}
      layout
      onClick={onOpen}
      onKeyDown={(e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      title={session.cwd || undefined}
      className={
        "group w-full text-left px-3 py-2.5 rounded-md border transition-colors cursor-pointer flex flex-col gap-2 " +
        (isOpen
          ? "bg-cyan-950/30 border-cyan-700/60"
          : "bg-[var(--color-surface-1)] border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900/60") +
        (isCompanionActive ? " ring-1 ring-emerald-500/40" : "")
      }
    >
      {/* Identity row: dot + pin-glyph (when pinned) + name + chips.
          flex-wrap lets the chip cluster drop below the name on narrow
          viewports instead of crashing into the wrapped 2nd line of the
          name (UX B10). gap-y-1 gives a small breathing line in that
          wrapped state. */}
      <div className="flex items-center gap-x-2 gap-y-1 min-w-0 flex-wrap">
        <FlashDot speaking={isSpeaking} recent={isRecent} muted={muted} />
        {pinned && (
          <PinIcon
            className="w-3 h-3 text-amber-400 shrink-0"
            aria-hidden
            title="Pinned to top of group"
          />
        )}
        {/* Name: text-sm semibold, wraps to 2 lines if long. The tooltip
            shows the full name when hover. */}
        <span
          className="font-semibold text-sm text-[var(--color-text-1)] flex-1 min-w-0 basis-[60%] leading-snug break-words line-clamp-2 whitespace-normal"
          title={headline}
        >
          {headline}
        </span>
        {/* Character chip — placeholder for the future bottom-right
            character display area. Once that lands this can be removed
            from the row to free up more space. */}
        {character && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-900/60 text-cyan-100 font-semibold truncate max-w-[100px] shrink-0"
            title={
              character.persona
                ? `${characterDisplayName(character)} · ${character.persona}`
                : characterDisplayName(character)
            }
          >
            {characterDisplayName(character)}
          </span>
        )}
        {isCompanionActive && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-200 font-semibold uppercase tracking-wide shrink-0">
            active
          </span>
        )}
      </div>

      {/* "What just happened?" recap card — shows latest narration from
          the last 5 minutes. Renders live via SSE updates. */}
      {latestNarration && (
        <div className="text-xs text-ct-muted bg-ct-elevated/50 rounded p-2 border border-ct-border/40">
          <span className="font-mono text-ct-cyan/70 mr-2">{latestNarration.mode}</span>
          {latestNarration.confidence === "low" && (
            <span
              className="inline-block font-mono text-ct-amber mr-2 border border-ct-amber/50 rounded px-1"
              title="Hedge: low confidence"
            >
              ?
            </span>
          )}
          <span className="italic">"{truncateText(latestNarration.text, 120)}"</span>
          <span className="ml-2 opacity-60">{formatRelativeTime(latestNarration.timestamp)}</span>
        </div>
      )}

      {/* Controls row: ALWAYS visible (no more hover-reveal). Mode
          picker is on the left because it's the most-used control;
          mute is the destructive action so it sits on the right with
          extra padding. Pin/destination pips cluster in the middle. */}
      <div className="flex items-center gap-1.5">
        <ModeQuickPick
          mode={mode}
          auto={auto}
          onChange={(next) => modeMutation.mutate({ active_mode: next })}
          disabled={modeMutation.isPending}
        />
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            pinMutation.mutate({ pinned: !pinned });
          }}
          disabled={pinMutation.isPending}
          aria-pressed={pinned}
          title={pinned ? "Unpin from top of group" : "Pin to top of group"}
          className={
            "p-1 rounded border shrink-0 " +
            (pinned
              ? "bg-amber-900/40 text-amber-200 border-amber-700/60 hover:bg-amber-900/60"
              : "bg-zinc-900 text-zinc-400 border-zinc-700 hover:bg-zinc-800 hover:text-zinc-200")
          }
        >
          <PinIcon className="w-3 h-3" aria-hidden />
        </button>
        <DestinationPips outputs={outputs} />
        <div className="flex-1" />
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            muteMutation.mutate({ enabled: muted });
          }}
          disabled={muteMutation.isPending}
          // Pre-signal destructive intent: tint border rose even when
          // unmuted, so this never reads as just another mode toggle
          // sitting next to brief/live pills. UX review B3.
          className={
            "text-[10px] px-2 py-0.5 rounded font-mono border shrink-0 " +
            (muted
              ? "bg-rose-900/50 text-rose-100 border-rose-600"
              : "bg-zinc-900 text-rose-300 border-rose-900/50 hover:bg-rose-900/30 hover:border-rose-700")
          }
        >
          {muted ? "unmute" : "mute"}
        </button>
      </div>
    </motion.div>
  );
}

function FlashDot({
  speaking,
  recent,
  muted,
}: {
  speaking: boolean;
  recent: boolean;
  muted: boolean;
}) {
  const color = muted
    ? "bg-rose-500"
    : speaking
      ? "bg-emerald-400"
      : recent
        ? "bg-emerald-500"
        : "bg-zinc-600";
  const animate = speaking
    ? { scale: [1, 1.4, 1], opacity: [1, 0.6, 1] }
    : recent
      ? { scale: [1, 1.15, 1], opacity: [0.85, 1, 0.85] }
      : { scale: 1, opacity: 0.7 };
  const transition = speaking
    ? { duration: 0.9, repeat: Infinity, ease: "easeInOut" as const }
    : recent
      ? { duration: 2.2, repeat: Infinity, ease: "easeInOut" as const }
      : { duration: 0 };
  return (
    <motion.span
      aria-hidden
      animate={animate}
      transition={transition}
      className={
        "inline-block w-2.5 h-2.5 rounded-full shrink-0 " +
        color +
        (speaking ? " shadow-[0_0_10px_var(--color-accent-live,#34d399)]" : "")
      }
    />
  );
}

function DestinationPips({ outputs }: { outputs: AudioOutput[] | null | undefined }) {
  // null/undefined = inheriting fleet default. Render hollow pips.
  const inherit = outputs === null || outputs === undefined;
  const set = new Set<AudioOutput>(inherit ? [] : outputs!);
  const sinks: { key: AudioOutput; title: string }[] = [
    { key: "desktop", title: "Desktop" },
    { key: "phone", title: "Phone" },
    { key: "glasses", title: "Glasses" },
  ];
  return (
    <div
      className="flex items-center gap-0.5 shrink-0"
      title={
        inherit
          ? "Audio: inheriting fleet default"
          : set.size === 0
            ? "Audio: silenced everywhere"
            : `Audio: ${[...set].join(", ")}`
      }
    >
      {sinks.map(({ key, title }) => {
        const filled = set.has(key);
        return (
          <span
            key={key}
            aria-label={title}
            className={
              "inline-block w-1.5 h-1.5 rounded-full " +
              (inherit
                ? "bg-zinc-700 outline outline-1 outline-zinc-600"
                : filled
                  ? "bg-cyan-400"
                  : "bg-zinc-700")
            }
          />
        );
      })}
    </div>
  );
}

/** Filled pushpin glyph. Tilted 30deg right so it reads as "pinned" rather
 *  than ambiguous map-pin. Sized via className (w-3 h-3 default usage). */
function PinIcon({
  className,
  title,
  ...rest
}: React.SVGProps<SVGSVGElement> & { title?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      stroke="none"
      className={className}
      {...rest}
    >
      {title && <title>{title}</title>}
      <path d="M14.4 2.6l7 7-3.5 1.4-3 7-3-3-5 5-1.4-1.4 5-5-3-3 7-3z" />
    </svg>
  );
}

function ModeQuickPick({
  mode,
  auto,
  onChange,
  disabled,
}: {
  mode: string;
  auto: boolean;
  onChange: (m: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex items-center gap-1 shrink-0">
      {auto && (
        <span
          className="text-[10px] text-cyan-300 font-mono"
          title="Auto-switching based on activity"
        >
          ↻ auto
        </span>
      )}
      {(["brief", "live"] as const).map((m) => {
        const selected = mode === m;
        return (
          <button
            key={m}
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onChange(m);
            }}
            disabled={disabled}
            className={
              "text-[10px] px-2 py-0.5 rounded font-mono border " +
              (selected
                ? "bg-cyan-700 text-white border-cyan-600"
                : "bg-zinc-900 text-zinc-400 border-zinc-700 hover:bg-zinc-800")
            }
          >
            {m}
          </button>
        );
      })}
    </div>
  );
}

/** Get the most recent narration event within the last 5 minutes,
 *  or undefined if none exists. */
function getLatestNarrationWithin5min(
  events: NarrationEvent[]
): NarrationEvent | undefined {
  if (events.length === 0) return undefined;
  const fiveMinutesMs = 5 * 60 * 1000;
  const now = Date.now();
  // Events are chronologically ordered by useNarrationStream, so the last
  // one is the most recent. Walk backwards to find the first entry within
  // the 5-minute window.
  for (let i = events.length - 1; i >= 0; i--) {
    const evt = events[i];
    const ageMs = now - evt.timestamp * 1000;
    if (ageMs >= 0 && ageMs <= fiveMinutesMs) {
      return evt;
    }
  }
  return undefined;
}

/** Truncate text to maxLen characters, appending "…" if truncated. */
function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "…";
}

/** Format a timestamp (epoch seconds) as a relative time string.
 *  Examples: "just now", "5s ago", "2m ago", "1h ago" */
function formatRelativeTime(timestampSeconds: number): string {
  const ageMs = Date.now() - timestampSeconds * 1000;
  const ageSecs = Math.floor(ageMs / 1000);

  if (ageSecs < 1) return "just now";
  if (ageSecs < 60) return `${ageSecs}s ago`;

  const ageMins = Math.floor(ageSecs / 60);
  if (ageMins < 60) return `${ageMins}m ago`;

  const ageHours = Math.floor(ageMins / 60);
  if (ageHours < 24) return `${ageHours}h ago`;

  const ageDays = Math.floor(ageHours / 24);
  return `${ageDays}d ago`;
}
