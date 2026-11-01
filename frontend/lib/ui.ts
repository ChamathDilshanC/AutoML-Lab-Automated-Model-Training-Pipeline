import { cn } from "@/lib/utils";

// Shared class names, so a button or card looks the same on every page. Colours come from the
// tokens in app/globals.css.

type ButtonVariant = "primary" | "accent" | "secondary" | "ghost" | "danger" | "danger-outline";
type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary text-on-primary shadow-sm shadow-black/10 hover:bg-primary/90",
  accent: "bg-accent text-on-accent shadow-sm shadow-accent/25 hover:bg-accent/90",
  secondary: "border border-border bg-bg text-text shadow-xs hover:border-text/30 hover:bg-surface",
  ghost: "text-muted hover:bg-surface hover:text-text",
  danger: "bg-danger text-white shadow-sm shadow-danger/20 hover:bg-danger/90",
  "danger-outline": "border border-danger/40 bg-bg text-danger hover:bg-danger/5",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-9 px-3.5 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-12 px-6 text-base",
};

/** Classes for a `<button>` or a `<Link>` styled as a button. */
export function buttonClass(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cn(
    "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-xl font-medium whitespace-nowrap",
    "transition-[background-color,border-color,color,box-shadow,transform] duration-150 active:scale-[0.98]",
    "disabled:pointer-events-none disabled:opacity-60",
    VARIANTS[variant],
    SIZES[size],
    className,
  );
}

/** A raised panel on the page background. */
export const cardClass =
  "rounded-3xl border border-border/70 bg-bg/90 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_12px_32px_-12px_rgb(15_23_42/0.08)] backdrop-blur-sm";

/** Text inputs and selects. */
export const fieldClass =
  "h-11 w-full rounded-xl border border-border bg-bg px-3.5 text-base text-text shadow-xs transition-colors hover:border-text/30 focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm";

/** The horizontal container every page and the header and footer share. */
export const containerClass = "mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8";
