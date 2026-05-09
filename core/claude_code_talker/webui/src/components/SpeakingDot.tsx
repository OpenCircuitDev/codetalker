// Phase 27 — breathing dot indicator. Active = "speaking" (emerald, pulsing).
import { motion } from "framer-motion";
import { breathing } from "../theme/motion";

export function SpeakingDot({ active }: { active: boolean }) {
  return (
    <motion.span
      aria-hidden
      variants={breathing}
      animate={active ? "speaking" : "idle"}
      className={
        "inline-block w-2.5 h-2.5 rounded-full " +
        (active
          ? "bg-[var(--color-accent-live)] shadow-[0_0_8px_var(--color-accent-live)]"
          : "bg-zinc-600")
      }
    />
  );
}
