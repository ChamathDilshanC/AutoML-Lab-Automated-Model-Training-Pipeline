import type { IconType } from "react-icons";
import { cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

interface Props {
  label: React.ReactNode;
  value: React.ReactNode;
  icon?: IconType;
  hint?: React.ReactNode;
  highlight?: boolean;
  className?: string;
}

/** One labelled figure. Render inside a `<dl>`. */
export default function StatCard({ label, value, icon: Icon, hint, highlight, className }: Props) {
  return (
    <div
      className={cn(
        cardClass,
        "flex flex-col gap-3 rounded-2xl p-5",
        highlight && "border-accent/40 ring-4 ring-accent/10",
        className,
      )}
    >
      <dt className="flex items-center justify-between gap-2 text-sm text-muted">
        <span>{label}</span>
        {Icon && (
          <span
            aria-hidden="true"
            className={cn(
              "flex size-8 items-center justify-center rounded-xl",
              highlight ? "bg-accent/10 text-accent" : "bg-surface text-text/70",
            )}
          >
            <Icon className="size-4" />
          </span>
        )}
      </dt>
      <dd className="flex flex-col gap-1">
        <span className="text-2xl font-semibold tracking-tight break-words tabular-nums">{value}</span>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </dd>
    </div>
  );
}
