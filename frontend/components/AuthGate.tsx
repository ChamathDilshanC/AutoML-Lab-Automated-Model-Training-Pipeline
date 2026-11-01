"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LuLoaderCircle, LuRefreshCw } from "react-icons/lu";
import { useAuth } from "@/components/AuthProvider";
import Logo from "@/components/Logo";
import { PageMain } from "@/components/PageHeader";
import Alert from "@/components/ui/Alert";
import { buttonClass, cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

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

  return (
    <PageMain className="items-center justify-center">
      <div className={cn(cardClass, "flex w-full max-w-md flex-col items-center gap-5 p-8 text-center")}>
        <Logo variant="mark" className="h-12" />
        {auth.status === "error" ? (
          <>
            <Alert role="alert" className="w-full text-left">
              {auth.message}
            </Alert>
            <button type="button" onClick={retry} className={buttonClass("primary")}>
              <LuRefreshCw aria-hidden="true" className="size-4" />
              Try again
            </button>
          </>
        ) : (
          <p role="status" className="inline-flex items-center gap-2 text-muted">
            <LuLoaderCircle aria-hidden="true" className="size-4 animate-spin text-accent" />
            {auth.status === "anonymous" ? "Redirecting to sign in…" : "Checking sign-in…"}
          </p>
        )}
      </div>
    </PageMain>
  );
}
