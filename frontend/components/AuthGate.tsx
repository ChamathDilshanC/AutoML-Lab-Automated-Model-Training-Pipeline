"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";

/** Shows its children only to a signed-in user; everyone else is sent to the sign-in page. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { auth, retry } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "anonymous") {
      const here = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(here)}`);
    }
  }, [auth.status, router]);

  if (auth.status === "authenticated") return <>{children}</>;

  if (auth.status === "error") {
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-start gap-3 px-4 py-12">
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {auth.message}
        </p>
        <button
          type="button"
          onClick={retry}
          className="rounded-md border border-border px-4 py-2 font-medium"
        >
          Try again
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 px-4 py-12">
      <p role="status" className="text-muted">
        {auth.status === "anonymous" ? "Redirecting to sign in…" : "Checking sign-in…"}
      </p>
    </main>
  );
}
