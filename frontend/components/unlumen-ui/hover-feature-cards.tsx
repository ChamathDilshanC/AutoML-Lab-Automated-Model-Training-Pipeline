"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";

// Adapted from the Unlumen UI registry: the screenshot `img` slots are replaced by a `visual`
// node so the cards can show icon art, `eyebrow` labels each card (for example a step number),
// and on touch screens, which cannot hover, the description is always shown.

const HOVER_QUERY = "(hover: hover)";

function subscribeToHover(onChange: () => void) {
  const query = window.matchMedia(HOVER_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function useCanHover(): boolean {
  return React.useSyncExternalStore(
    subscribeToHover,
    () => window.matchMedia(HOVER_QUERY).matches,
    () => true,
  );
}

export interface HoverFeatureCard {
  name: string;
  description: string;
  eyebrow?: string;
  href?: string;
  visual?: React.ReactNode;
  containerClassName?: string;
  fadeBottom?: boolean;
  soon?: boolean;
}

export interface HoverFeatureCardsProps {
  items: HoverFeatureCard[];
  className?: string;
  renderLink?: (href: string, children: React.ReactNode) => React.ReactNode;
}

function HoverFeatureCard({
  item,
  renderLink,
}: {
  item: HoverFeatureCard;
  renderLink?: HoverFeatureCardsProps["renderLink"];
}) {
  const canHover = useCanHover();
  const inner = (
    <motion.div
      initial="rest"
      whileHover="hover"
      animate={canHover ? "rest" : "hover"}
      whileTap={{ scale: item.href && !item.soon ? 0.97 : 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
      variants={{ rest: { scale: 1, y: 0 } }}
      className={cn(
        "group flex flex-col w-full relative",
        item.soon ? "opacity-80 cursor-not-allowed" : item.href ? "cursor-pointer" : "",
      )}
    >
      <div
        className={cn(
          "flex flex-col rounded-3xl border h-64 z-5 bg-surface transition-colors w-full overflow-hidden",
          !item.soon && item.href ? "hover:border-border/80" : "",
          item.soon ? "border-dashed border-border" : "border-border/70",
        )}
      >
        {item.soon && (
          <span className="absolute top-3 right-3 z-10 text-xs text-muted-foreground border rounded-full px-2 py-1 bg-card">
            Coming soon
          </span>
        )}

        <div
          className={cn(
            "relative w-full h-full overflow-hidden px-5 pt-6 pb-4 flex flex-col gap-3",
            item.containerClassName,
          )}
        >
          {item.eyebrow && (
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {item.eyebrow}
            </span>
          )}
          <span
            className={cn(
              "font-medium text-xl tracking-tight",
              item.soon ? "text-muted-foreground/80" : "text-foreground",
            )}
          >
            {item.name}
          </span>

          {item.visual && <div className="flex flex-1 items-center justify-center">{item.visual}</div>}

          {item.fadeBottom && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-22 bg-gradient-to-t from-surface to-transparent" />
          )}
        </div>
      </div>

      <motion.div
        variants={{
          rest: { opacity: 0, y: -30 },
          hover: { opacity: 1, y: 0 },
        }}
        transition={{ type: "spring", stiffness: 200, damping: 15 }}
        className="overflow-hidden z-1 w-11/12 self-center"
      >
        <div className="py-3 px-5 relative border-t-0 rounded-b-3xl border border-border/70 bg-background">
          <div className="pointer-events-none w-[103%] bg-gradient-to-b from-background to-transparent h-12 absolute -top-1 -left-1" />
          <p className="relative text-sm font-base text-muted-foreground">{item.description}</p>
        </div>
      </motion.div>
    </motion.div>
  );

  if (item.href && renderLink) {
    return renderLink(item.href, inner);
  }

  return inner;
}

function HoverFeatureCards({ items, className, renderLink }: HoverFeatureCardsProps) {
  return (
    <div className={cn("grid grid-cols-1 sm:grid-cols-2 gap-4 w-full", className)}>
      {items.map((item) => (
        <HoverFeatureCard key={item.name} item={item} renderLink={renderLink} />
      ))}
    </div>
  );
}

export { HoverFeatureCards, HoverFeatureCard };
