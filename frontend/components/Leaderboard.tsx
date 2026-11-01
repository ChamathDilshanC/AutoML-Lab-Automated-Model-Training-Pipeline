import Link from "next/link";
import { LuArrowRight, LuCircleCheck, LuTrophy } from "react-icons/lu";
import Alert from "@/components/ui/Alert";
import { MotionAccordion } from "@/components/unlumen-ui/motion-faqs-accordion";
import { algorithmLabel, directionText, formatNumber, metricLabel } from "@/lib/format";
import type { ExperimentRun, Leaderboard as LeaderboardData } from "@/lib/types";
import { buttonClass, cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

function hyperparameterText(run: ExperimentRun): string {
  const entries = Object.entries(run.hyperparameters);
  return entries.length === 0
    ? "none tuned"
    : entries.map(([name, value]) => `${name}=${value === null ? "None" : String(value)}`).join(", ");
}

/** Where a score sits between the worst (0) and best (1) successful run. */
function relativeScore(value: number | null | undefined, scores: number[], higherIsBetter: boolean) {
  if (value === null || value === undefined || scores.length === 0) return 0;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  if (max === min) return 1;
  return higherIsBetter ? (value - min) / (max - min) : (max - value) / (max - min);
}

export default function Leaderboard({ board }: { board: LeaderboardData }) {
  const primary = board.metric;
  const secondary = Array.from(
    new Set(board.runs.flatMap((run) => Object.keys(run.metrics))),
  ).filter((name) => name !== primary);
  const metricColumns = [primary, ...secondary];
  const arrow = board.higher_is_better ? "↑" : "↓";
  const winner = board.runs.find((run) => run.run_id === board.selected_run_id);
  const succeeded = board.runs.filter((run) => run.status === "SUCCEEDED");
  const failed = board.runs.filter((run) => run.status === "FAILED");
  const primaryScores = succeeded
    .map((run) => run.metrics[primary])
    .filter((value): value is number => typeof value === "number");

  return (
    <section aria-labelledby="leaderboard-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 id="leaderboard-title" className="text-2xl font-semibold tracking-tight">
          Leaderboard
        </h2>
        <p className="text-sm text-muted">
          Ranked by {metricLabel(primary)} ({directionText(board.higher_is_better)}) on the held-out
          test set.
        </p>
      </div>

      {winner && board.selection_reason && (
        <div
          className={cn(
            cardClass,
            "flex flex-col gap-5 rounded-2xl border-success/30 p-6 sm:flex-row sm:items-center sm:justify-between",
          )}
        >
          <div className="flex gap-4">
            <span
              aria-hidden="true"
              className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-success/10 text-success"
            >
              <LuTrophy className="size-6" />
            </span>
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium text-success">
                <LuCircleCheck aria-hidden="true" className="mr-1 inline size-4 align-[-3px]" />
                Best: {algorithmLabel(winner.algorithm)}.
              </p>
              <p className="text-3xl font-semibold tracking-tight tabular-nums">
                {formatNumber(winner.metrics[board.selection_reason.metric])}{" "}
                <span className="text-base font-medium text-muted">
                  {metricLabel(board.selection_reason.metric)}
                </span>
              </p>
              <p className="max-w-2xl text-sm text-muted">
                It has the best {metricLabel(board.selection_reason.metric)} (
                {directionText(board.higher_is_better)}) on the held-out test set. Ties are broken
                by algorithm name.
              </p>
            </div>
          </div>
          {board.model_id && (
            <div className="flex flex-col items-start gap-2 sm:items-end">
              <Link href={`/models/${board.model_id}`} className={buttonClass("primary")}>
                View the registered model
                <LuArrowRight aria-hidden="true" className="size-4" />
              </Link>
              <span className="text-xs text-muted">
                It must be approved before it can make predictions.
              </span>
            </div>
          )}
        </div>
      )}
      {!winner && <Alert role="alert">No algorithm produced a rankable result.</Alert>}

      <div className={cn(cardClass, "overflow-hidden rounded-2xl")}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <caption className="sr-only">
              Algorithms ranked by {metricLabel(primary)} ({directionText(board.higher_is_better)})
            </caption>
            <thead className="bg-surface/60 text-xs tracking-wide text-muted uppercase">
              <tr>
                <th scope="col" className="px-5 py-3 font-medium">Rank</th>
                <th scope="col" className="px-5 py-3 font-medium">Algorithm</th>
                {metricColumns.map((name) => (
                  <th
                    key={name}
                    scope="col"
                    className={cn(
                      "px-5 py-3 text-right font-medium whitespace-nowrap",
                      name === primary && "font-bold text-text",
                    )}
                  >
                    {metricLabel(name)}
                    {name === primary && (
                      <>
                        {" "}
                        <span aria-hidden="true">{arrow}</span>
                        <span className="sr-only"> ({directionText(board.higher_is_better)})</span>
                      </>
                    )}
                  </th>
                ))}
                <th scope="col" className="px-5 py-3 text-right font-medium whitespace-nowrap">CV score</th>
                <th scope="col" className="px-5 py-3 text-right font-medium whitespace-nowrap">Time (s)</th>
                <th scope="col" className="px-5 py-3 font-medium whitespace-nowrap">Tuned parameters</th>
              </tr>
            </thead>
            <tbody>
              {succeeded.map((run) => {
                const isWinner = run.run_id === board.selected_run_id;
                const share = relativeScore(run.metrics[primary], primaryScores, board.higher_is_better);
                return (
                  <tr
                    key={run.run_id}
                    className={cn(
                      "border-t border-border/50 transition-colors hover:bg-surface/40",
                      isWinner && "bg-success/[0.04]",
                    )}
                  >
                    <td className="px-5 py-3.5 whitespace-nowrap tabular-nums">
                      <span className="inline-flex size-7 items-center justify-center rounded-lg bg-surface font-semibold">
                        {run.rank ?? "–"}
                      </span>
                      {isWinner && (
                        <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-semibold whitespace-nowrap text-success">
                          <LuCircleCheck aria-hidden="true" className="size-3" />
                          Best
                        </span>
                      )}
                    </td>
                    <th scope="row" className="px-5 py-3.5 font-medium whitespace-nowrap">
                      {algorithmLabel(run.algorithm)}
                    </th>
                    {metricColumns.map((name) => (
                      <td
                        key={name}
                        className={cn(
                          "px-5 py-3.5 text-right tabular-nums",
                          name === primary && "font-bold",
                        )}
                        title={run.metrics[name] == null ? "Could not be computed" : undefined}
                      >
                        {name === primary ? (
                          <span className="flex items-center justify-end gap-3">
                            <span
                              aria-hidden="true"
                              className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-surface md:block"
                            >
                              <span
                                className={cn("block h-full rounded-full", isWinner ? "bg-success" : "bg-accent/70")}
                                style={{ width: `${Math.max(share * 100, 6)}%` }}
                              />
                            </span>
                            {formatNumber(run.metrics[name])}
                          </span>
                        ) : (
                          formatNumber(run.metrics[name])
                        )}
                      </td>
                    ))}
                    <td className="px-5 py-3.5 text-right tabular-nums">{formatNumber(run.cv_score)}</td>
                    <td className="px-5 py-3.5 text-right tabular-nums">
                      {formatNumber(run.duration_seconds, 2)}
                    </td>
                    <td className="min-w-48 px-5 py-3.5 text-muted">{hyperparameterText(run)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {failed.length > 0 && (
        <Alert
          title={`${failed.length} algorithm${failed.length > 1 ? "s" : ""} failed and ${failed.length > 1 ? "are" : "is"} not ranked:`}
        >
          <ul className="mt-1 list-disc pl-5">
            {failed.map((run) => (
              <li key={run.run_id}>
                {algorithmLabel(run.algorithm)}: {run.error_summary}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      <p className="text-sm text-muted">
        Scores come from one held-out test set. The best score among the tested candidates is not a
        guarantee of real-world performance.
      </p>

      {board.split && (
        <MotionAccordion
          size="sm"
          itemClassName={cn(cardClass, "rounded-2xl bg-bg/90")}
          items={[
            {
              question: "How this was evaluated",
              answer: (
                <ul className="list-disc pl-5">
                  <li>
                    Split: {board.split.strategy.replace("_", " ")}, {board.split.n_train} training
                    rows and {board.split.n_test} test rows (seed {board.split.random_state}).
                  </li>
                  <li>
                    CV score is the cross-validated {metricLabel(primary)} on the training rows, used
                    to choose each algorithm&apos;s parameters.
                  </li>
                  {board.library_versions && (
                    <li>
                      Libraries:{" "}
                      {Object.entries(board.library_versions)
                        .map(([name, version]) => `${name} ${version}`)
                        .join(", ")}
                    </li>
                  )}
                </ul>
              ),
            },
          ]}
        />
      )}
    </section>
  );
}
