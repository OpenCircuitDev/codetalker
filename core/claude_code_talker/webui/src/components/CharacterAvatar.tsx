// Phase 27 — animated character avatar. Spring entry on attach.
import { motion } from "framer-motion";
import { avatarEmerge } from "../theme/motion";

interface Props {
  name: string;
  /** Filesystem path to a .glb mesh — daemon serves these at
   *  `/api/characters/{id}/mesh-file`. CharacterStage passes
   *  `characterId` so we can build the URL; older callers pass
   *  `meshUrl` (deprecated string-path). When both are absent we
   *  fall back to a persona-tinted gradient circle with the
   *  character's initial. */
  meshUrl?: string | null;
  characterId?: string | null;
  persona?: string | null;
  size?: "sm" | "md" | "lg" | "xl";
}

const PERSONA_GRADIENTS: Record<string, string> = {
  methodical: "from-slate-600 to-slate-900",
  warm: "from-amber-500 to-rose-700",
  technical: "from-cyan-500 to-blue-800",
  plain: "from-zinc-500 to-zinc-800",
  sarcastic: "from-fuchsia-500 to-purple-800",
  energetic: "from-rose-500 to-orange-600",
};

const SIZES: Record<NonNullable<Props["size"]>, string> = {
  sm: "w-8 h-8 text-xs",
  md: "w-12 h-12 text-base",
  lg: "w-20 h-20 text-2xl",
  // v0.1.0 unification — `xl` for the bottom-right CharacterStage.
  // Big enough to read the full name centered inside.
  xl: "w-36 h-36 text-xl",
};

export function CharacterAvatar({
  name,
  meshUrl,
  characterId,
  persona,
  size = "md",
}: Props) {
  const initial = name.trim()[0]?.toUpperCase() || "?";
  const gradient = PERSONA_GRADIENTS[persona || ""] || "from-zinc-600 to-zinc-800";
  // Mesh URL: the daemon's served route at `/api/characters/{id}/mesh-file`.
  // Not used yet — kept on the element's `title` so users can see the mesh
  // is available even before the 3D viewer lands.
  const servedUrl = characterId
    ? `/api/characters/${encodeURIComponent(characterId)}/mesh-file`
    : meshUrl || null;
  // For xl (the marquee CharacterStage avatar) show the FULL name so the
  // user can read the character's identity at a glance. For sm/md/lg
  // show just the initial — less crowded for chips and row indicators.
  // The full name is still in the parent's text below the avatar for
  // non-xl uses.
  const showFullName = size === "xl";
  return (
    <motion.div
      variants={avatarEmerge}
      initial="initial"
      animate="animate"
      className={
        SIZES[size] +
        " rounded-full bg-gradient-to-br " +
        gradient +
        " flex items-center justify-center font-bold text-white shadow-lg flex-shrink-0 ring-2 ring-white/10 text-center"
      }
      title={name + (servedUrl ? " · 3D mesh available" : "")}
    >
      <span aria-hidden className="px-3 leading-tight">
        {showFullName ? name : initial}
      </span>
    </motion.div>
  );
}
