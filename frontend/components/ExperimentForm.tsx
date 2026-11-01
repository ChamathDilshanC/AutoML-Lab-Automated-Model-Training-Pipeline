"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { createExperiment, errorMessage, getDataset, getExperimentOptions } from "@/lib/api";
import { algorithmLabel, directionText, metricLabel } from "@/lib/format";
import { notifyError } from "@/lib/notifications";
import type { Dataset, ExperimentOptions, Task } from "@/lib/types";

type Loaded =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; dataset: Dataset; options: ExperimentOptions };

const TASK_LABELS: Record<Task, string> = {
  classification: "Classification (predict a category)",
  regression: "Regression (predict a number)",
};

export default function ExperimentForm() {
  const router = useRouter();
  const datasetId = useSearchParams().get("dataset");
  const [loaded, setLoaded] = useState<Loaded>({ phase: "loading" });

  const [target, setTarget] = useState("");
  const [task, setTask] = useState<Task>("classification");
  const [metric, setMetric] = useState(""); // empty means the task's default
  const [chosen, setChosen] = useState<string[] | null>(null); // null means all for the task
  const [seed, setSeed] = useState(42);
  const [testPercent, setTestPercent] = useState(20);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (!datasetId) return;
    const controller = new AbortController();
    Promise.all([getDataset(datasetId, controller.signal), getExperimentOptions(controller.signal)])
      .then(([dataset, options]) => setLoaded({ phase: "ready", dataset, options }))
      .catch((err) => {
        if (!controller.signal.aborted) setLoaded({ phase: "error", message: errorMessage(err) });
      });
    return () => controller.abort();
  }, [datasetId]);

  if (!datasetId) {
    return (
      <p role="alert" className="rounded-md border border-danger p-3 text-danger">
        No dataset selected. Upload a dataset first, then create an experiment from its page.
      </p>
    );
  }
  if (loaded.phase === "loading") {
    return (
      <p role="status" className="text-muted">
        Loading dataset…
      </p>
    );
  }
  if (loaded.phase === "error") {
    return (
      <p role="alert" className="rounded-md border border-danger p-3 text-danger">
        {loaded.message}
      </p>
    );
  }

  const { dataset, options } = loaded;
  const columns = dataset.validation?.columns ?? [];
  if (dataset.status !== "READY") {
    return (
      <p role="alert" className="rounded-md border border-danger p-3 text-danger">
        This dataset is not ready. Validate it first on{" "}
        <Link href={`/datasets/${dataset.dataset_id}`} className="underline">
          its page
        </Link>
        .
      </p>
    );
  }

  const taskOptions = options[task];
  const effectiveMetric = metric || taskOptions.default_metric;
  const algorithms = chosen ?? taskOptions.algorithms;

  function changeTask(next: Task) {
    setTask(next);
    setMetric("");
    setChosen(null);
  }

  function toggleAlgorithm(name: string, checked: boolean) {
    const next = checked ? [...algorithms, name] : algorithms.filter((item) => item !== name);
    setChosen(taskOptions.algorithms.filter((item) => next.includes(item)));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!target) {
      const message = "Choose a target column.";
      setError(message);
      notifyError("Experiment needs a target", message);
      return;
    }
    if (algorithms.length === 0) {
      const message = "Choose at least one algorithm.";
      setError(message);
      notifyError("Choose an algorithm", message);
      return;
    }
    setSubmitting(true);
    try {
      const experiment = await createExperiment(
        {
          dataset_id: dataset.dataset_id,
          task,
          target_column: target,
          metric: effectiveMetric,
          algorithms,
          random_seed: seed,
          test_size: testPercent / 100,
        },
        idempotencyKey,
      );
      router.push(`/experiments/${experiment.experiment_id}`);
    } catch (err) {
      const message = errorMessage(err);
      setError(message);
      notifyError("Experiment creation failed", message);
      setSubmitting(false);
    }
  }

  const field = "rounded-md border border-border bg-bg px-3 py-2";

  return (
    <form onSubmit={submit} className="flex flex-col gap-6">
      <p className="text-muted">
        Dataset: <span className="font-medium text-text">{dataset.original_filename}</span> (
        {dataset.validation?.row_count} rows)
      </p>

      <div className="flex flex-col gap-1">
        <label htmlFor="target" className="font-medium">
          Target column
        </label>
        <select
          id="target"
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          className={field}
        >
          <option value="">Choose the column to predict…</option>
          {columns.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name} ({column.kind})
            </option>
          ))}
        </select>
        <p className="text-sm text-muted">The target is never used as an input feature.</p>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-medium">Task</legend>
        {(Object.keys(TASK_LABELS) as Task[]).map((value) => (
          <label key={value} className="flex items-center gap-2">
            <input
              type="radio"
              name="task"
              value={value}
              checked={task === value}
              onChange={() => changeTask(value)}
            />
            {TASK_LABELS[value]}
          </label>
        ))}
      </fieldset>

      <div className="flex flex-col gap-1">
        <label htmlFor="metric" className="font-medium">
          Metric to rank by
        </label>
        <select
          id="metric"
          value={effectiveMetric}
          onChange={(event) => setMetric(event.target.value)}
          className={field}
        >
          {taskOptions.metrics.map((option) => (
            <option key={option.name} value={option.name}>
              {metricLabel(option.name)} ({directionText(option.higher_is_better)})
            </option>
          ))}
        </select>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-medium">Algorithms</legend>
        {taskOptions.algorithms.map((name) => (
          <label key={name} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={algorithms.includes(name)}
              onChange={(event) => toggleAlgorithm(name, event.target.checked)}
            />
            {algorithmLabel(name)}
          </label>
        ))}
      </fieldset>

      <details>
        <summary className="cursor-pointer font-medium">Advanced settings</summary>
        <div className="mt-3 flex flex-wrap gap-6">
          <div className="flex flex-col gap-1">
            <label htmlFor="seed">Random seed</label>
            <input
              id="seed"
              type="number"
              min={0}
              value={seed}
              onChange={(event) => setSeed(Number(event.target.value))}
              className={field}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="test-size">Test set size (%)</label>
            <input
              id="test-size"
              type="number"
              min={5}
              max={50}
              value={testPercent}
              onChange={(event) => setTestPercent(Number(event.target.value))}
              className={field}
            />
          </div>
        </div>
      </details>

      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}

      <div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-60"
        >
          {submitting ? "Starting…" : "Run experiment"}
        </button>
      </div>
    </form>
  );
}
