"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/config";
import { notifyWarning } from "@/lib/notifications";
import { cn } from "@/lib/utils";

type State = "checking" | "up" | "down";

const LABELS: Record<State, string> = {
  checking: "Checking backend…",
  up: "Backend is reachable",
  down: "Backend is not reachable",
};

const DOT: Record<State, string> = {
  checking: "bg-muted",
  up: "bg-success",
  down: "bg-danger",
};

interface Props {
  /** Also raise a toast when the backend cannot be reached. Set on one instance per page. */
  announce?: boolean;
  className?: string;
}

export default function HealthStatus({ announce = false, className }: Props) {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const controller = new AbortController();
    const down = () => {
      setState("down");
      if (announce) {
        notifyWarning("Backend is not reachable", "Uploads, training and predictions are unavailable.");
      }
    };
    fetch(`${API_BASE_URL}/health`, { signal: controller.signal })
      .then((res) => (res.ok ? setState("up") : down()))
      .catch((err) => {
        if (err.name !== "AbortError") down();
      });
    return () => controller.abort();
  }, [announce]);

  return (
    <p
      role="status"
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border/70 bg-bg/80 px-3 py-1 text-xs font-medium text-muted",
        className,
      )}
    >
      <span className="relative flex size-2" aria-hidden="true">
        {state === "up" && (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-50" />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", DOT[state])} />
      </span>
      {LABELS[state]}
    </p>
  );
}
