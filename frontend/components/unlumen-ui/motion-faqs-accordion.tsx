"use client";

import * as React from "react";
import { motion } from "motion/react";

import { cn } from "@/lib/utils";

// Adapted from the Unlumen UI registry: answers may hold any content (lists, form fields), closed
// panels are `inert` so their controls cannot be focused, and a compact size suits detail pages.

export interface MotionAccordionItem {
  question: React.ReactNode;
  answer: React.ReactNode;
}

export interface MotionAccordionProps {
  items: MotionAccordionItem[];
  /** @default 10 */
  gap?: number;
  /** @default "lg" */
  size?: "sm" | "lg";
  /** Index of the item open on first render. */
  defaultOpenIndex?: number | null;
  className?: string;
  itemClassName?: string;
}

function AccordionItem({
  item,
  isOpen,
  onToggle,
  itemId,
  panelId,
  size,
  className,
}: {
  item: MotionAccordionItem;
  isOpen: boolean;
  onToggle: () => void;
  itemId: string;
  panelId: string;
  size: "sm" | "lg";
  className?: string;
}) {
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [contentH, setContentH] = React.useState(0);
  const compact = size === "sm";

  React.useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setContentH(el.scrollHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <motion.div
      layout
      className={cn(
        "overflow-hidden bg-surface text-foreground shadow-xs",
        compact ? "rounded-2xl" : "rounded-[30px]",
        className,
      )}
      transition={{ type: "spring", stiffness: 280, damping: 28, mass: 0.9 }}
      animate={{ scale: isOpen ? 1 : 0.985 }}
      initial={false}
      style={{ originX: 0.5, originY: 0 }}
    >
      <button
        id={itemId}
        type="button"
        aria-controls={panelId}
        aria-expanded={isOpen}
        onClick={onToggle}
        className={cn(
          "flex w-full cursor-pointer select-none items-center justify-between gap-4 text-left",
          compact ? "px-5 py-3" : "px-7 py-5",
        )}
      >
        <span
          className={cn(
            "font-medium tracking-tight leading-snug",
            compact ? "text-base" : "text-[clamp(1.05rem,1.6vw,1.2rem)]",
          )}
        >
          {item.question}
        </span>

        <motion.span
          aria-hidden="true"
          initial={false}
          animate={{
            rotate: isOpen ? 180 : 0,
            scale: isOpen ? 1.05 : 1,
          }}
          transition={{ type: "spring", stiffness: 480, damping: 28 }}
          className={cn(
            "inline-flex shrink-0 items-center justify-center text-foreground",
            compact ? "size-8" : "size-12",
          )}
        >
          {isOpen ? (
            <svg width="14" height="14" viewBox="0 0 14 2" fill="none" aria-hidden>
              <path d="M1 1h12" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path
                d="M7 1v12M1 7h12"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          )}
        </motion.span>
      </button>

      <motion.div
        id={panelId}
        role="region"
        aria-labelledby={itemId}
        inert={!isOpen}
        animate={{
          height: isOpen ? contentH : 0,
          opacity: isOpen ? 1 : 0,
        }}
        initial={false}
        transition={{
          height: { type: "spring", stiffness: 340, damping: 34, mass: 0.9 },
          opacity: { duration: 0.2, ease: "easeOut" },
        }}
        style={{ overflow: "hidden" }}
      >
        <motion.div
          ref={contentRef}
          animate={{ y: isOpen ? 0 : -8 }}
          transition={{
            type: "spring",
            stiffness: 360,
            damping: 30,
            mass: 0.8,
          }}
          className={compact ? "px-5 pb-5" : "px-7 pb-7"}
        >
          <div
            className={cn(
              "tracking-normal text-foreground/75",
              compact ? "text-sm leading-6" : "text-base leading-7",
            )}
          >
            {item.answer}
          </div>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}

export function MotionAccordion({
  items,
  gap = 10,
  size = "lg",
  defaultOpenIndex = null,
  className,
  itemClassName,
}: MotionAccordionProps) {
  const rawId = React.useId();
  const baseId = `accordion-${rawId.replace(/:/g, "")}`;

  const [openIndex, setOpenIndex] = React.useState<number | null>(defaultOpenIndex);

  const toggle = (i: number) => setOpenIndex((prev) => (prev === i ? null : i));

  return (
    <div className={cn("w-full", className)}>
      <div className="flex flex-col" style={{ gap }}>
        {items.map((item, i) => (
          <AccordionItem
            key={i}
            item={item}
            isOpen={openIndex === i}
            onToggle={() => toggle(i)}
            itemId={`${baseId}-trigger-${i}`}
            panelId={`${baseId}-panel-${i}`}
            size={size}
            className={itemClassName}
          />
        ))}
      </div>
    </div>
  );
}
