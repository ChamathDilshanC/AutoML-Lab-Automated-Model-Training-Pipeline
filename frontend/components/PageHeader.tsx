import Link from "next/link";
import type { IconType } from "react-icons";
import { LuChevronRight, LuHouse } from "react-icons/lu";
import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  href?: string;
}

/** "Home › …" trail. The last crumb is the current page and is not a link. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
        <li>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-md transition-colors hover:text-text"
          >
            <LuHouse aria-hidden="true" className="size-3.5" />
            Home
          </Link>
        </li>
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li key={item.label} className="inline-flex items-center gap-1.5">
              <LuChevronRight aria-hidden="true" className="size-3.5 text-muted/60" />
              {item.href && !last ? (
                <Link href={item.href} className="rounded-md transition-colors hover:text-text">
                  {item.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className={last ? "text-text" : ""}>
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** A small pill above a page title, such as "Step 1 of 4". */
export function Eyebrow({ icon: Icon, children }: { icon?: IconType; children: React.ReactNode }) {
  return (
    <p className="inline-flex w-fit items-center gap-2 rounded-full border border-border/70 bg-bg/80 px-3 py-1 text-xs font-semibold tracking-wide text-muted shadow-xs">
      {Icon && <Icon aria-hidden="true" className="size-3.5 text-accent" />}
      {children}
    </p>
  );
}

interface Props {
  title: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  eyebrowIcon?: IconType;
  actions?: React.ReactNode;
  className?: string;
}

/** Title block at the top of a page, with optional actions on the right. */
export default function PageHeader({
  title,
  description,
  eyebrow,
  eyebrowIcon,
  actions,
  className,
}: Props) {
  return (
    <div
      className={cn("flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between", className)}
    >
      <div className="flex max-w-3xl flex-col gap-3">
        {eyebrow && <Eyebrow icon={eyebrowIcon}>{eyebrow}</Eyebrow>}
        <h1 className="text-3xl font-semibold tracking-tight break-words sm:text-4xl">{title}</h1>
        {description && <div className="text-base leading-7 text-muted">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}

/** The `<main>` landmark every page uses, at the shared width. */
export function PageMain({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <main
      id="main"
      className={cn(
        "mx-auto flex w-full max-w-7xl flex-1 flex-col gap-10 px-4 py-10 sm:px-6 lg:px-8 lg:py-14",
        className,
      )}
    >
      {children}
    </main>
  );
}
