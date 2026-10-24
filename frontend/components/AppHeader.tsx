"use client";

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

export default function AppHeader() {
  const { auth, signOut } = useAuth();
  const link = "underline-offset-4 hover:underline";

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <nav aria-label="Main" className="flex flex-wrap items-center gap-4">
          <Link href="/" className="font-semibold">
            AutoML Lab
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
              Signed in as <strong data-testid="username">{auth.username}</strong>
            </span>
            <button
              type="button"
              onClick={signOut}
              className="rounded-md border border-border px-3 py-1 font-medium"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
