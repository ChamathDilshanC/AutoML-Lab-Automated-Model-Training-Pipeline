import Link from "next/link";
import type { IconType } from "react-icons";
import { FaAws } from "react-icons/fa";
import { LuArrowUpRight, LuBookOpen } from "react-icons/lu";
import { SiFastapi, SiGithub, SiNextdotjs, SiPython, SiScikitlearn } from "react-icons/si";
import FooterBottomBar from "@/components/FooterBottomBar";
import HealthStatus from "@/components/HealthStatus";
import Logo from "@/components/Logo";
import { containerClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

const REPO = "https://github.com/ChamathDilshanC/AutoML-Lab-Automated-Model-Training-Pipeline";

interface FooterLink {
  label: string;
  href: string;
}

const COLUMNS: { title: string; links: FooterLink[] }[] = [
  {
    title: "Workspace",
    links: [
      { label: "Dashboard", href: "/" },
      { label: "Upload a dataset", href: "/datasets/new" },
      { label: "Models", href: "/models" },
    ],
  },
  {
    title: "Documentation",
    links: [
      { label: "Overview", href: `${REPO}/blob/main/docs/README.md` },
      { label: "Architecture", href: `${REPO}/blob/main/docs/ARCHITECTURE.md` },
      { label: "API reference", href: `${REPO}/blob/main/docs/API_SPEC.md` },
      { label: "Security", href: `${REPO}/blob/main/docs/SECURITY.md` },
    ],
  },
  {
    title: "Project",
    links: [
      { label: "Source code", href: REPO },
      { label: "Roadmap", href: `${REPO}/blob/main/docs/ROADMAP.md` },
      { label: "Contributing", href: `${REPO}/blob/main/CONTRIBUTING.md` },
    ],
  },
];

const STACK: { name: string; icon: IconType }[] = [
  { name: "Next.js", icon: SiNextdotjs },
  { name: "FastAPI", icon: SiFastapi },
  { name: "scikit-learn", icon: SiScikitlearn },
  { name: "Python", icon: SiPython },
  { name: "AWS", icon: FaAws },
];

const linkClass =
  "group inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-text";

function FooterLinkItem({ link }: { link: FooterLink }) {
  if (link.href.startsWith("/")) {
    return (
      <Link href={link.href} className={linkClass}>
        {link.label}
      </Link>
    );
  }
  return (
    <a href={link.href} target="_blank" rel="noreferrer" className={linkClass}>
      {link.label}
      <LuArrowUpRight
        aria-hidden="true"
        className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100"
      />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

const iconButton =
  "inline-flex size-10 items-center justify-center rounded-xl border border-border/70 bg-bg text-muted shadow-xs transition hover:-translate-y-0.5 hover:border-text/30 hover:text-text";

export default function SiteFooter() {
  return (
    <footer className="relative z-10 mt-auto overflow-hidden border-t border-border/60 bg-bg/75 backdrop-blur-md">
      <div className={cn(containerClass, "pt-14 pb-8 lg:pt-16")}>
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12">
          <div className="flex flex-col items-start gap-5 lg:col-span-5">
            <Link href="/" aria-label="AutoML Lab home" className="rounded-lg">
              <Logo className="h-11" />
            </Link>
            <p className="max-w-sm text-sm leading-6 text-muted">
              Upload a tabular CSV, compare allowlisted scikit-learn models on a held-out test set,
              and serve predictions from a versioned registry that needs your approval first.
            </p>
            <HealthStatus announce />
            <div className="flex gap-2">
              <a href={REPO} target="_blank" rel="noreferrer" className={iconButton}>
                <SiGithub aria-hidden="true" className="size-4" />
                <span className="sr-only">Source code on GitHub (opens in a new tab)</span>
              </a>
              <a
                href={`${REPO}/blob/main/docs/README.md`}
                target="_blank"
                rel="noreferrer"
                className={iconButton}
              >
                <LuBookOpen aria-hidden="true" className="size-4" />
                <span className="sr-only">Documentation (opens in a new tab)</span>
              </a>
            </div>
          </div>

          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:col-span-7">
            {COLUMNS.map((column) => (
              <div key={column.title}>
                <h2 className="text-xs font-semibold tracking-[0.16em] text-text uppercase">
                  {column.title}
                </h2>
                <ul className="mt-4 flex flex-col gap-3">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <FooterLinkItem link={link} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="mt-12 flex flex-col gap-4 rounded-2xl border border-border/60 bg-surface/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs font-semibold tracking-[0.16em] text-muted uppercase">Built with</p>
          <ul className="flex flex-wrap items-center gap-x-6 gap-y-3">
            {STACK.map(({ name, icon: Icon }) => (
              <li key={name} className="inline-flex items-center gap-2 text-sm font-medium text-text/80">
                <Icon aria-hidden="true" className="size-4" />
                {name}
              </li>
            ))}
          </ul>
        </div>

        <FooterBottomBar />
      </div>

      <p
        aria-hidden="true"
        className="pointer-events-none -mb-[2.5vw] bg-gradient-to-b from-text/[0.08] to-transparent bg-clip-text text-center text-[15vw] leading-none font-semibold tracking-tighter text-transparent select-none"
      >
        AutoML Lab
      </p>
    </footer>
  );
}
