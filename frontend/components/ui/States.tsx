import type { IconType } from "react-icons";
import { LuLoaderCircle } from "react-icons/lu";
import { cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

/** A spinner with text; the text alone carries the meaning when motion is reduced. */
export function LoadingState({ label, className }: { label: string; className?: string }) {
  return (
    <div
      role="status"
      className={cn(cardClass, "flex items-center gap-3 rounded-2xl p-6 text-muted", className)}
    >
      <LuLoaderCircle aria-hidden="true" className="size-5 animate-spin text-accent" />
      <span>{label}</span>
    </div>
  );
}

/** A placeholder for an empty collection, with what to do next. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon: IconType;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        cardClass,
        "flex flex-col items-center gap-4 border-dashed px-6 py-14 text-center",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="flex size-14 items-center justify-center rounded-2xl border border-border/70 bg-surface text-text/70"
      >
        <Icon className="size-6" />
      </span>
      <div className="flex max-w-md flex-col gap-1">
        <p className="text-lg font-semibold tracking-tight">{title}</p>
        {children && <div className="text-sm leading-6 text-muted">{children}</div>}
      </div>
      {action}
    </div>
  );
}
