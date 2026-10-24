import { algorithmLabel, directionText, formatNumber, metricLabel } from "@/lib/format";
import type { ExperimentRun, Leaderboard as LeaderboardData } from "@/lib/types";

function hyperparameterText(run: ExperimentRun): string {
  const entries = Object.entries(run.hyperparameters);
  return entries.length === 0
    ? "none tuned"
    : entries.map(([name, value]) => `${name}=${value === null ? "None" : String(value)}`).join(", ");
}

export default function Leaderboard({ board }: { board: LeaderboardData }) {
  const primary = board.metric;
  const secondary = Array.from(
    new Set(board.runs.flatMap((run) => Object.keys(run.metrics))),
  ).filter((name) => name !== primary);
  const metricColumns = [primary, ...secondary];
  const arrow = board.higher_is_better ? "↑" : "↓";
  const winner = board.runs.find((run) => run.run_id === board.selected_run_id);
  const failed = board.runs.filter((run) => run.status === "FAILED");

  return (
    <section aria-labelledby="leaderboard-title" className="flex flex-col gap-4">
      <h2 id="leaderboard-title" className="text-xl font-semibold">
        Leaderboard
      </h2>

      {winner && board.selection_reason && (
        <p className="rounded-md border border-success p-3">
          <span className="font-medium text-success">
            <span aria-hidden="true">✓ </span>Best: {algorithmLabel(winner.algorithm)}.
          </span>{" "}
          It has the best {metricLabel(board.selection_reason.metric)} (
          {directionText(board.higher_is_better)}) on the held-out test set. Ties are broken by
          algorithm name.
        </p>
      )}
      {!winner && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          No algorithm produced a rankable result.
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">
            Algorithms ranked by {metricLabel(primary)} ({directionText(board.higher_is_better)})
          </caption>
          <thead className="bg-surface">
            <tr>
              <th scope="col" className="p-2">Rank</th>
              <th scope="col" className="p-2">Algorithm</th>
              {metricColumns.map((name) => (
                <th
                  key={name}
                  scope="col"
                  className={`p-2 text-right ${name === primary ? "font-bold" : ""}`}
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
              <th scope="col" className="p-2 text-right">CV score</th>
              <th scope="col" className="p-2 text-right">Time (s)</th>
              <th scope="col" className="p-2">Tuned parameters</th>
            </tr>
          </thead>
          <tbody>
            {board.runs
              .filter((run) => run.status === "SUCCEEDED")
              .map((run) => {
                const isWinner = run.run_id === board.selected_run_id;
                return (
                  <tr
                    key={run.run_id}
                    className={`border-t border-border ${isWinner ? "bg-surface" : ""}`}
                  >
                    <td className="p-2 whitespace-nowrap tabular-nums">
                      {run.rank ?? "–"}
                      {isWinner && (
                        <span className="ml-2 inline-block rounded-full border border-success px-2 py-0.5 text-xs font-medium whitespace-nowrap text-success">
                          <span aria-hidden="true">✓ </span>Best
                        </span>
                      )}
                    </td>
                    <th scope="row" className="p-2 font-medium">
                      {algorithmLabel(run.algorithm)}
                    </th>
                    {metricColumns.map((name) => (
                      <td
                        key={name}
                        className={`p-2 text-right tabular-nums ${name === primary ? "font-bold" : ""}`}
                        title={run.metrics[name] == null ? "Could not be computed" : undefined}
                      >
                        {formatNumber(run.metrics[name])}
                      </td>
                    ))}
                    <td className="p-2 text-right tabular-nums">{formatNumber(run.cv_score)}</td>
                    <td className="p-2 text-right tabular-nums">
                      {formatNumber(run.duration_seconds, 2)}
                    </td>
                    <td className="p-2 text-muted">{hyperparameterText(run)}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>

      {failed.length > 0 && (
        <div className="rounded-md border border-danger p-3">
          <p className="font-medium text-danger">
            <span aria-hidden="true">✕ </span>
            {failed.length} algorithm{failed.length > 1 ? "s" : ""} failed and{" "}
            {failed.length > 1 ? "are" : "is"} not ranked:
          </p>
          <ul className="list-disc pl-6">
            {failed.map((run) => (
              <li key={run.run_id}>
                {algorithmLabel(run.algorithm)}: {run.error_summary}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-sm text-muted">
        Scores come from one held-out test set. The best score among the tested candidates is not a
        guarantee of real-world performance.
      </p>

      {board.split && (
        <details className="text-sm text-muted">
          <summary className="cursor-pointer">How this was evaluated</summary>
          <ul className="mt-2 list-disc pl-6">
            <li>
              Split: {board.split.strategy.replace("_", " ")}, {board.split.n_train} training rows
              and {board.split.n_test} test rows (seed {board.split.random_state}).
            </li>
            <li>
              CV score is the cross-validated {metricLabel(primary)} on the training rows, used to
              choose each algorithm&apos;s parameters.
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
        </details>
      )}
    </section>
  );
}
