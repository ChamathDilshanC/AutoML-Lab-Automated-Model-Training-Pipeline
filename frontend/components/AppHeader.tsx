"use client";

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

export default function AppHeader() {
  const { auth, signOut } = useAuth();
  const link = "underline-offset-4 hover:underline";

  return (
    <header className="sticky top-0 z-20 border-b border-border/80 bg-bg/85 shadow-sm backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <nav aria-label="Main" className="flex flex-wrap items-center gap-4">
          <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-sm font-bold text-on-accent shadow-lg shadow-accent/20">
              AI
            </span>
            <span>AutoML Lab</span>
          </Link>
          <Link href="/datasets/new" className={link}>
            Upload dataset
          </Link>
          <Link href="/models" className={link}>
            Models
          </Link>
        </nav>
        {auth.status === "authenticated" && (
          <div className="flex items-center gap-3 text-sm">
            <span>
              Signed in as               <strong data-testid="username">{auth.email ?? auth.username}</strong>
            </span>
            <button
              type="button"
              onClick={signOut}
              className="rounded-xl border border-border bg-bg px-3 py-1.5 font-medium transition hover:border-accent hover:text-accent"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
