"use client";

import { MotionConfig } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Motion configuration.
 *
 * `reducedMotion="user"` makes framer-motion skip transform and layout
 * animations entirely when the OS reports `prefers-reduced-motion: reduce`,
 * while leaving opacity transitions intact. That matters because the CSS layer
 * in `globals.css` cannot intercept values framer-motion writes inline on every
 * frame.
 *
 * `useReducedMotion` elsewhere should still be used when a component needs to
 * branch on the preference rather than just have it honoured automatically.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

export default MotionProvider;