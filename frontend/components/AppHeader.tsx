"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import type { IconType } from "react-icons";
import { LuBoxes, LuCloudUpload, LuLayoutDashboard, LuLogOut } from "react-icons/lu";
import { useAuth } from "@/components/AuthProvider";
import Logo from "@/components/Logo";
import { SidebarToggleIcon } from "@/components/unlumen-ui/sidebar-toggle-icon";
import { buttonClass, containerClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: IconType;
  isActive: (pathname: string) => boolean;
}

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LuLayoutDashboard, isActive: (p) => p === "/" },
  {
    href: "/datasets/new",
    label: "Upload dataset",
    icon: LuCloudUpload,
    isActive: (p) => p.startsWith("/datasets"),
  },
  { href: "/models", label: "Models", icon: LuBoxes, isActive: (p) => p.startsWith("/models") },
];

function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || "?";
}

export default function AppHeader() {
  const { auth, signOut } = useAuth();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const signedIn = auth.status === "authenticated";
  const who = signedIn ? (auth.email ?? auth.username) : "";

  return (
    <header className="sticky top-0 z-30 border-b border-border/60 bg-bg/75 backdrop-blur-xl">
      <div className={cn(containerClass, "flex h-16 items-center justify-between gap-4")}>
        <div className="flex items-center gap-8">
          <Link href="/" aria-label="AutoML Lab home" className="rounded-lg">
            <Logo eager className="h-8 sm:h-9" />
          </Link>

          <nav aria-label="Main" className="hidden md:block">
            <ul className="flex items-center gap-1 rounded-full border border-border/60 bg-surface/70 p-1">
              {NAV.map(({ href, label, icon: Icon, isActive }) => {
                const active = isActive(pathname);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "relative flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                        active ? "text-text" : "text-muted hover:text-text",
                      )}
                    >
                      {active && (
                        <motion.span
                          layoutId="nav-active"
                          className="absolute inset-0 rounded-full bg-bg shadow-sm ring-1 ring-border/60"
                          transition={{ type: "spring", stiffness: 420, damping: 34 }}
                        />
                      )}
                      <Icon aria-hidden="true" className="relative size-4" />
                      <span className="relative">{label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          {signedIn && (
            <div className="hidden items-center gap-3 md:flex">
              <div className="flex items-center gap-2.5 rounded-full border border-border/60 bg-bg/80 py-1 pr-3.5 pl-1">
                <span
                  aria-hidden="true"
                  className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-on-primary"
                >
                  {initial(who)}
                </span>
                <span className="max-w-56 truncate text-sm">
                  <span className="sr-only">Signed in as </span>
                  <strong data-testid="username" className="font-medium">
                    {who}
                  </strong>
                </span>
              </div>
              <button type="button" onClick={signOut} className={buttonClass("secondary", "sm")}>
                <LuLogOut aria-hidden="true" className="size-4" />
                Sign out
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            className="inline-flex size-10 cursor-pointer items-center justify-center rounded-xl border border-border/70 bg-bg text-text md:hidden"
          >
            <SidebarToggleIcon isOpen={menuOpen} className="size-5" />
            <span className="sr-only">{menuOpen ? "Close menu" : "Open menu"}</span>
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {menuOpen && (
          <motion.div
            id="mobile-menu"
            key="mobile-menu"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 36 }}
            className="overflow-hidden border-t border-border/60 md:hidden"
          >
            <nav aria-label="Main" className={cn(containerClass, "flex flex-col gap-1 py-3")}>
              {NAV.map(({ href, label, icon: Icon, isActive }) => {
                const active = isActive(pathname);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMenuOpen(false)}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium",
                      active ? "bg-surface text-text" : "text-muted hover:bg-surface hover:text-text",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-4" />
                    {label}
                  </Link>
                );
              })}
              {signedIn && (
                <div className="mt-2 flex items-center justify-between gap-3 border-t border-border/60 pt-3">
                  <span className="min-w-0 truncate text-sm text-muted">
                    Signed in as <strong className="font-medium text-text">{who}</strong>
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      signOut();
                    }}
                    className={buttonClass("secondary", "sm")}
                  >
                    <LuLogOut aria-hidden="true" className="size-4" />
                    Sign out
                  </button>
                </div>
              )}
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
