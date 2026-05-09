// Phase 27 — shared framer-motion variants for entry/exit + breathing animations.
import type { Variants } from "framer-motion";

export const cardEntry: Variants = {
  initial: { opacity: 0, y: 8, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.22, ease: "easeOut" } },
  exit: { opacity: 0, y: -4, scale: 0.97, transition: { duration: 0.16 } },
};

export const breathing: Variants = {
  idle: { scale: 1 },
  speaking: {
    scale: [1, 1.06, 1],
    transition: { duration: 1.6, repeat: Infinity, ease: "easeInOut" },
  },
};

export const tickerEntry: Variants = {
  initial: { opacity: 0, x: -8 },
  animate: { opacity: 1, x: 0, transition: { duration: 0.18 } },
  exit: { opacity: 0, x: 4, transition: { duration: 0.12 } },
};

export const avatarEmerge: Variants = {
  initial: { scale: 0.4, opacity: 0, rotate: -8 },
  animate: {
    scale: 1,
    opacity: 1,
    rotate: 0,
    transition: { type: "spring", stiffness: 300, damping: 22 },
  },
};
