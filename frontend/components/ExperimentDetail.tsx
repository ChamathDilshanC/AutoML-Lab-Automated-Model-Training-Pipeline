"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Leaderboard from "@/components/Leaderboard";
import StatusBadge from "@/components/StatusBadge";
import { errorMessage, getExperiment, getLeaderboard } from "@/lib/api";
import { algorithmLabel, metricLabel } from "@/lib/format";
import {
  TERMINAL_EXPERIMENT_STATUSES,
  type Experiment,
  type Leaderboard as LeaderboardData,
} from "@/lib/types";

const POLL_MS = 2000;

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; experiment: Experiment; board: LeaderboardData | null };

const PROGRESS_TEXT: Record<string, string> = {
  CREATED: "The experiment has been created.",
  QUEUED: "Waiting for the worker to pick it up. Make sure the worker is running.",
  RUNNING: "The worker is training and evaluating the algorithms.",
};

export default function ExperimentDetail({ experimentId }: { experimentId: string }) {
  const [view, setView] = useState<View>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const experiment = await getExperiment(experimentId, controller.signal);
        const finished = TERMINAL_EXPERIMENT_STATUSES.includes(experiment.status);
        const board = finished ? await getLeaderboard(experimentId, controller.signal) : null;
        if (controller.signal.aborted) return;
        setView({ phase: "ready", experiment, board });
        if (!finished) timer = setTimeout(poll, POLL_MS);
      } catch (err) {
        if (!controller.signal.aborted) setView({ phase: "error", message: errorMessage(err) });
      }
    }

    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [experimentId, attempt]);

  if (view.phase === "loading") {
    return (
      <p role="status" className="text-muted">
        Loading experiment…
      </p>
    );
  }
  if (view.phase === "error") {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {view.message}
        </p>
        <button
          type="button"
          onClick={() => {
            setView({ phase: "loading" });
            setAttempt((n) => n + 1);
          }}
          className="rounded-md border border-border px-4 py-2 font-medium"
        >
          Try again
        </button>
      </div>
    );
  }

  const { experiment, board } = view;
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Experiment</h1>
        <StatusBadge status={experiment.status} />
      </header>

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          ["Task", experiment.task === "classification" ? "Classification" : "Regression"],
          ["Target column", experiment.target_column],
          ["Metric", metricLabel(experiment.metric)],
          ["Algorithms", experiment.algorithms.map(algorithmLabel).join(", ")],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-border bg-surface p-3">
            <dt className="text-sm text-muted">{label}</dt>
            <dd className="font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm">
        Dataset:{" "}
        <Link href={`/datasets/${experiment.dataset_id}`} className="underline">
          view dataset
        </Link>
      </p>

      <div role="status" aria-live="polite">
        {PROGRESS_TEXT[experiment.status] && (
          <p className="text-muted">{PROGRESS_TEXT[experiment.status]}</p>
        )}
      </div>

      {experiment.status === "FAILED" && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          This experiment failed: {experiment.error_summary ?? "unknown error."}
        </p>
      )}

      {board && board.runs.length > 0 && <Leaderboard board={board} />}
    </div>
  );
}
