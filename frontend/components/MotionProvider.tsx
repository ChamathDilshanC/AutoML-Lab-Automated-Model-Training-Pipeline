"use client";

import { MotionConfig } from "motion/react";

/** Animations made with Motion follow the user's "reduce motion" setting. */
export default function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
