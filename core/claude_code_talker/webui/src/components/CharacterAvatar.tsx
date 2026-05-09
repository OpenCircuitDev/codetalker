// Phase 27 — animated character avatar. Spring entry on attach.
import { motion } from "framer-motion";
import { avatarEmerge } from "../theme/motion";

interface Props {
  name: string;
  meshUrl?: string | null;
  persona?: string | null;
  size?: "sm" | "md" | "lg";
}

const PERSONA_GRADIENTS: Record<string, string> = {
  methodical: "from-slate-700 to-slate-900",
  warm: "from-amber-600 to-rose-800",
  technical: "from-cyan-600 to-blue-900",
  plain: "from-zinc-600 to-zinc-800",
  sarcastic: "from-fuchsia-600 to-purple-900",
  energetic: "from-rose-500 to-orange-700",
};

const SIZES: Record<NonNullable<Props["size"]>, string> = {
  sm: "w-8 h-8 text-xs",
  md: "w-12 h-12 text-base",
  lg: "w-20 h-20 text-2xl",
};

export function CharacterAvatar({ name, meshUrl, persona, size = "md" }: Props) {
  const initial = name.trim()[0]?.toUpperCase() || "?";
  const gradient = PERSONA_GRADIENTS[persona || ""] || "from-zinc-600 to-zinc-800";
  return (
    <motion.div
      variants={avatarEmerge}
      initial="initial"
      animate="animate"
      className={
        SIZES[size] +
        " rounded-full bg-gradient-to-br " +
        gradient +
        " flex items-center justify-center font-bold text-white shadow-md flex-shrink-0"
      }
      title={name}
    >
      {meshUrl ? (
        <img
          src={meshUrl}
          alt={name}
          className="rounded-full w-full h-full object-cover"
        />
      ) : (
        initial
      )}
    </motion.div>
  );
}
