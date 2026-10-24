"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/config";

type State = "checking" | "up" | "down";

const LABELS: Record<State, string> = {
  checking: "Checking backend…",
  up: "Backend is reachable",
  down: "Backend is not reachable",
};

export default function HealthStatus() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/health`, { signal: controller.signal })
      .then((res) => setState(res.ok ? "up" : "down"))
      .catch((err) => {
        if (err.name !== "AbortError") setState("down");
      });
    return () => controller.abort();
  }, []);

  return (
    <p role="status" className="text-sm text-muted">
      {LABELS[state]}
    </p>
  );
}
