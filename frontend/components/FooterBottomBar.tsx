"use client";

import { Suspense } from "react";
import { LuArrowUp } from "react-icons/lu";

// Read at request time inside <Suspense>: Next.js refuses the current time in a prerender.
function CurrentYear() {
  return <>{new Date().getFullYear()}</>;
}

export default function FooterBottomBar() {
  function backToTop() {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
  }

  return (
    <div className="mt-8 flex flex-col-reverse gap-4 border-t border-border/60 pt-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
      <p>
        ©{" "}
        <Suspense fallback="2026">
          <CurrentYear />
        </Suspense>{" "}
        AutoML Lab · Maintained by{" "}
        <a
          href="https://github.com/ChamathDilshanC"
          target="_blank"
          rel="noreferrer"
          className="font-medium text-text underline-offset-4 hover:underline"
        >
          ChamathDilshanC
        </a>
      </p>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <p className="text-xs">Scores come from a held-out test set and are not a guarantee.</p>
        <button
          type="button"
          onClick={backToTop}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg font-medium text-text transition-colors hover:text-accent"
        >
          Back to top
          <LuArrowUp aria-hidden="true" className="size-4" />
        </button>
      </div>
    </div>
  );
}
