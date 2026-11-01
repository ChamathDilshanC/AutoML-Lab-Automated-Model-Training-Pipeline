"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { errorMessage } from "@/lib/api";
import { safeNextPath } from "@/lib/auth";
import { notifyError } from "@/lib/notifications";

export default function LoginForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const { auth, signInWithGoogle } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const handledRedirect = useRef(false);

  // Once signed in (here or in another visit), go where the user was headed.
  useEffect(() => {
    if (auth.status === "authenticated") router.replace(next);
  }, [auth.status, next, router]);

  useEffect(() => {
    if (handledRedirect.current) return;
    handledRedirect.current = true;
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const accessToken = fragment.get("access_token");
    const providerError = fragment.get("error_description") ?? fragment.get("error");
    if (!accessToken && !providerError) return;
    window.history.replaceState(null, "", `/login${next === "/" ? "" : `?next=${encodeURIComponent(next)}`}`);
    if (providerError) {
      queueMicrotask(() => {
        const message = "Google sign-in was cancelled or failed. Please try again.";
        setError(message);
        notifyError("Google sign-in failed", message);
      });
      return;
    }
    if (!accessToken) return;
    queueMicrotask(() => {
      setSubmitting(true);
      signInWithGoogle(accessToken)
        .catch((err) => {
          const message = errorMessage(err);
          setError(message);
          notifyError("Unable to sign in with Google", message);
        })
        .finally(() => setSubmitting(false));
    });
  }, [next, signInWithGoogle]);

  function startGoogleSignIn() {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    if (!url) {
      const message = "Google sign-in is not configured.";
      setError(message);
      notifyError("Google sign-in unavailable", message);
      return;
    }
    const redirect = new URL("/login", window.location.origin);
    if (next !== "/") redirect.searchParams.set("next", next);
    window.open(
      `${url.replace(/\/$/, "")}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirect.toString())}`,
      "_self",
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={startGoogleSignIn}
        disabled={submitting}
        className="rounded-md bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-60"
      >
        {submitting ? "Signing in…" : "Sign in with Google"}
      </button>
    </div>
  );
}
