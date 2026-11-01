"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { IconType } from "react-icons";
import {
  LuBoxes,
  LuCircleCheck,
  LuCircleDashed,
  LuCircleX,
  LuClock,
  LuCpu,
  LuDatabase,
  LuFlaskConical,
  LuGauge,
  LuLoaderCircle,
  LuRefreshCw,
  LuTarget,
  LuTimer,
} from "react-icons/lu";
import Leaderboard from "@/components/Leaderboard";
import StatusBadge from "@/components/StatusBadge";
import Alert from "@/components/ui/Alert";
import StatCard from "@/components/ui/StatCard";
import { LoadingState } from "@/components/ui/States";
import { AnimateDigits } from "@/components/unlumen-ui/animate-digits";
import { errorMessage, getExperiment, getLeaderboard } from "@/lib/api";
import { algorithmLabel, metricLabel } from "@/lib/format";
import { notifyError, notifyInfo, notifySuccess } from "@/lib/notifications";
import {
  TERMINAL_EXPERIMENT_STATUSES,
  type Experiment,
  type ExperimentStatus,
  type Leaderboard as LeaderboardData,
} from "@/lib/types";
import { buttonClass, cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

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

const STEPS: { label: string; icon: IconType }[] = [
  { label: "Created", icon: LuCircleDashed },
  { label: "Queued", icon: LuClock },
  { label: "Training", icon: LuCpu },
  { label: "Finished", icon: LuCircleCheck },
];

const STEP_INDEX: Record<ExperimentStatus, number> = {
  CREATED: 0,
  QUEUED: 1,
  RUNNING: 2,
  SUCCEEDED: 3,
  FAILED: 3,
};

/** `75` seconds becomes `1:15`; an hour or more becomes `1:02:05`. */
function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** The current time, refreshed every second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function Stepper({ status }: { status: ExperimentStatus }) {
  const current = STEP_INDEX[status];
  const failed = status === "FAILED";
  return (
    <ol className={cn(cardClass, "grid grid-cols-2 gap-3 rounded-2xl p-4 sm:grid-cols-4 sm:p-5")}>
      {STEPS.map(({ label, icon: Icon }, index) => {
        const done = index < current || (index === current && status === "SUCCEEDED");
        const active = index === current && !done;
        const StateIcon = failed && index === 3 ? LuCircleX : done ? LuCircleCheck : active ? LuLoaderCircle : Icon;
        return (
          <li
            key={label}
            aria-current={index === current ? "step" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-xl border px-3 py-2.5",
              failed && index === 3
                ? "border-danger/25 bg-danger/[0.04] text-danger"
                : done
                  ? "border-success/20 bg-success/[0.04] text-success"
                  : active
                    ? "border-accent/25 bg-accent/[0.05] text-accent"
                    : "border-border/60 text-muted",
            )}
          >
            <StateIcon aria-hidden="true" className={cn("size-4 shrink-0", active && "animate-spin")} />
            <span className="text-sm font-medium">
              {failed && index === 3 ? "Failed" : label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export default function ExperimentDetail({ experimentId }: { experimentId: string }) {
  const router = useRouter();
  const [view, setView] = useState<View>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);
  const lastStatus = useRef<ExperimentStatus | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const experiment = await getExperiment(experimentId, controller.signal);
        const finished = TERMINAL_EXPERIMENT_STATUSES.includes(experiment.status);
        const board = finished ? await getLeaderboard(experimentId, controller.signal) : null;
        if (controller.signal.aborted) return;
        announceChange(lastStatus.current, experiment, board);
        lastStatus.current = experiment.status;
        setView({ phase: "ready", experiment, board });
        if (!finished) timer = setTimeout(poll, POLL_MS);
      } catch (err) {
        if (controller.signal.aborted) return;
        const message = errorMessage(err);
        setView({ phase: "error", message });
        notifyError("Could not load the experiment", message);
      }
    }

    // Toasts only for changes seen while this page is open, not for the state it opened in.
    function announceChange(
      previous: ExperimentStatus | null,
      experiment: Experiment,
      board: LeaderboardData | null,
    ) {
      if (previous === null || previous === experiment.status) return;
      if (experiment.status === "RUNNING") {
        notifyInfo("Training started", "The worker picked up this experiment.");
      } else if (experiment.status === "SUCCEEDED") {
        const modelId = board?.model_id;
        notifySuccess(
          "Experiment finished",
          modelId ? "The best model was registered and is waiting for approval." : "See the leaderboard.",
          modelId ? { label: "View model", onClick: () => router.push(`/models/${modelId}`) } : undefined,
        );
      } else if (experiment.status === "FAILED") {
        notifyError("Experiment failed", experiment.error_summary ?? "See the experiment page.");
      }
    }

    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [experimentId, attempt, router]);

  const running = view.phase === "ready" && view.experiment.status === "RUNNING";
  const now = useNow(running);

  if (view.phase === "loading") return <LoadingState label="Loading experiment…" />;
  if (view.phase === "error") {
    return (
      <div className="flex flex-col items-start gap-4">
        <Alert role="alert" title="Could not load the experiment" className="w-full">
          {view.message}
        </Alert>
        <button
          type="button"
          onClick={() => {
            setView({ phase: "loading" });
            setAttempt((n) => n + 1);
          }}
          className={buttonClass("secondary")}
        >
          <LuRefreshCw aria-hidden="true" className="size-4" />
          Try again
        </button>
      </div>
    );
  }

  const { experiment, board } = view;
  const started = experiment.started_at ? Date.parse(experiment.started_at) : null;
  const ended = experiment.finished_at ? Date.parse(experiment.finished_at) : null;
  const elapsed = started === null ? null : ((ended ?? now) - started) / 1000;

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex min-w-0 gap-4">
          <span
            aria-hidden="true"
            className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-bg text-text shadow-sm"
          >
            <LuFlaskConical className="size-6" />
          </span>
          <div className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight">Experiment</h1>
              <StatusBadge status={experiment.status} />
            </div>
            <p className="text-sm text-muted">
              Predicting <strong className="font-medium text-text">{experiment.target_column}</strong>{" "}
              · created {new Date(experiment.created_at).toLocaleString()}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href={`/datasets/${experiment.dataset_id}`} className={buttonClass("secondary")}>
            <LuDatabase aria-hidden="true" className="size-4" />
            View dataset
          </Link>
          {board?.model_id && (
            <Link href={`/models/${board.model_id}`} className={buttonClass("primary")}>
              <LuBoxes aria-hidden="true" className="size-4" />
              View the registered model
            </Link>
          )}
        </div>
      </header>

      <Stepper status={experiment.status} />

      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Task"
          value={experiment.task === "classification" ? "Classification" : "Regression"}
          icon={LuTarget}
        />
        <StatCard label="Ranking metric" value={metricLabel(experiment.metric)} icon={LuGauge} />
        <StatCard
          label="Test set"
          value={`${Math.round(experiment.test_size * 100)}%`}
          hint={`Random seed ${experiment.random_seed}`}
          icon={LuDatabase}
        />
        <StatCard
          label={ended ? "Duration" : "Elapsed"}
          value={elapsed === null ? "–" : <AnimateDigits value={formatDuration(elapsed)} />}
          hint={experiment.started_at ? undefined : "Not started yet"}
          icon={LuTimer}
        />
      </dl>

      <section aria-labelledby="algorithms-title" className="flex flex-col gap-3">
        <h2 id="algorithms-title" className="text-sm font-semibold text-muted">
          Algorithms compared
        </h2>
        <ul className="flex flex-wrap gap-2">
          {experiment.algorithms.map((name) => (
            <li
              key={name}
              className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-bg/80 px-3 py-1.5 text-sm font-medium shadow-xs"
            >
              <LuCpu aria-hidden="true" className="size-3.5 text-muted" />
              {algorithmLabel(name)}
            </li>
          ))}
        </ul>
      </section>

      <div role="status" aria-live="polite">
        {PROGRESS_TEXT[experiment.status] && (
          <Alert tone="info">{PROGRESS_TEXT[experiment.status]}</Alert>
        )}
      </div>

      {experiment.status === "FAILED" && (
        <Alert role="alert" title="This experiment failed">
          {experiment.error_summary ?? "unknown error."}
        </Alert>
      )}

      {board && board.runs.length > 0 && <Leaderboard board={board} />}
    </div>
  );
}
