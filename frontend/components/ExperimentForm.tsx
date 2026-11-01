"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { IconType } from "react-icons";
import {
  LuCpu,
  LuFileSpreadsheet,
  LuGauge,
  LuPlay,
  LuShapes,
  LuTags,
  LuTarget,
  LuTrendingUp,
} from "react-icons/lu";
import Alert from "@/components/ui/Alert";
import Select from "@/components/ui/Select";
import { LoadingState } from "@/components/ui/States";
import { AnimateCount } from "@/components/unlumen-ui/animate-count";
import { AppleSwitch } from "@/components/unlumen-ui/apple-switch";
import { MotionAccordion } from "@/components/unlumen-ui/motion-faqs-accordion";
import { createExperiment, errorMessage, getDataset, getExperimentOptions } from "@/lib/api";
import { algorithmLabel, directionText, metricLabel } from "@/lib/format";
import { notifyError, notifyPromise } from "@/lib/notifications";
import type { Dataset, ExperimentOptions, Task } from "@/lib/types";
import { buttonClass, cardClass, fieldClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

type Loaded =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; dataset: Dataset; options: ExperimentOptions };

const TASKS: Record<Task, { title: string; text: string; icon: IconType }> = {
  classification: { title: "Classification", text: "Predict a category", icon: LuTags },
  regression: { title: "Regression", text: "Predict a number", icon: LuTrendingUp },
};

function Section({
  title,
  icon: Icon,
  aside,
  children,
}: {
  title: string;
  icon: IconType;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className={cn(cardClass, "flex flex-col gap-5 rounded-2xl p-6")}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span
            aria-hidden="true"
            className="flex size-8 items-center justify-center rounded-xl bg-surface text-text/70"
          >
            <Icon className="size-4" />
          </span>
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-right text-sm font-medium break-all">{children}</dd>
    </div>
  );
}

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
        if (controller.signal.aborted) return;
        const message = errorMessage(err);
        setLoaded({ phase: "error", message });
        notifyError("Could not load the dataset", message);
      });
    return () => controller.abort();
  }, [datasetId]);

  if (!datasetId) {
    return (
      <Alert role="alert" title="No dataset selected">
        Upload a dataset first, then create an experiment from its page.{" "}
        <Link href="/datasets/new" className="font-medium underline">
          Upload a dataset
        </Link>
      </Alert>
    );
  }
  if (loaded.phase === "loading") return <LoadingState label="Loading dataset…" />;
  if (loaded.phase === "error") return <Alert role="alert">{loaded.message}</Alert>;

  const { dataset, options } = loaded;
  const columns = dataset.validation?.columns ?? [];
  if (dataset.status !== "READY") {
    return (
      <Alert role="alert" title="This dataset is not ready">
        Validate it first on{" "}
        <Link href={`/datasets/${dataset.dataset_id}`} className="font-medium underline">
          its page
        </Link>
        .
      </Alert>
    );
  }

  const taskOptions = options[task];
  const effectiveMetric = metric || taskOptions.default_metric;
  const metricOption = taskOptions.metrics.find((option) => option.name === effectiveMetric);
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
      const experiment = await notifyPromise(
        createExperiment(
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
        ),
        {
          loading: "Starting the experiment",
          success: "Experiment queued",
          successDescription: `${algorithms.length} algorithm${algorithms.length === 1 ? "" : "s"} will be trained and compared.`,
          error: "Experiment creation failed",
        },
      );
      router.push(`/experiments/${experiment.experiment_id}`);
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
      <div className="flex flex-col gap-6 lg:col-span-8">
        <Section title="What to predict" icon={LuTarget}>
          <div className="flex flex-col gap-2">
            <label htmlFor="target" className="text-sm font-medium">
              Target column
            </label>
            <Select
              id="target"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              aria-describedby="target-help"
            >
              <option value="">Choose the column to predict…</option>
              {columns.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name} ({column.kind})
                </option>
              ))}
            </Select>
            <p id="target-help" className="text-sm text-muted">
              The target is never used as an input feature.
            </p>
          </div>

          <fieldset className="flex flex-col gap-3">
            <legend className="mb-2 text-sm font-medium">Task</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {(Object.keys(TASKS) as Task[]).map((value) => {
                const { title, text, icon: Icon } = TASKS[value];
                const selected = task === value;
                return (
                  <label
                    key={value}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-2xl border p-4 transition-all has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent",
                      selected
                        ? "border-text/80 bg-bg shadow-sm ring-1 ring-text/80"
                        : "border-border/70 bg-bg/60 hover:border-text/30",
                    )}
                  >
                    <input
                      type="radio"
                      name="task"
                      value={value}
                      checked={selected}
                      onChange={() => changeTask(value)}
                      className="sr-only"
                    />
                    <span
                      aria-hidden="true"
                      className={cn(
                        "flex size-10 shrink-0 items-center justify-center rounded-xl",
                        selected ? "bg-primary text-on-primary" : "bg-surface text-text/70",
                      )}
                    >
                      <Icon className="size-5" />
                    </span>
                    <span className="flex flex-col">
                      <span className="font-medium">{title}</span>
                      <span className="text-sm text-muted">{text}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        </Section>

        <Section title="Ranking metric" icon={LuGauge}>
          <div className="flex flex-col gap-2">
            <label htmlFor="metric" className="text-sm font-medium">
              Metric to rank by
            </label>
            <Select id="metric" value={effectiveMetric} onChange={(event) => setMetric(event.target.value)}>
              {taskOptions.metrics.map((option) => (
                <option key={option.name} value={option.name}>
                  {metricLabel(option.name)} ({directionText(option.higher_is_better)})
                </option>
              ))}
            </Select>
          </div>
        </Section>

        <Section
          title="Algorithms"
          icon={LuCpu}
          aside={
            <p className="flex items-center gap-1 text-sm text-muted" aria-live="polite">
              <AnimateCount className="font-semibold text-text">{algorithms.length}</AnimateCount>
              <span>of {taskOptions.algorithms.length} selected</span>
            </p>
          }
        >
          <fieldset className="flex flex-col gap-3">
            <legend className="sr-only">Algorithms</legend>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setChosen(null)}
                className={buttonClass("secondary", "sm")}
              >
                Select all
              </button>
              <button type="button" onClick={() => setChosen([])} className={buttonClass("ghost", "sm")}>
                Clear
              </button>
            </div>
            <ul className="grid gap-3 sm:grid-cols-2">
              {taskOptions.algorithms.map((name) => (
                <li
                  key={name}
                  className="flex items-center rounded-2xl border border-border/70 bg-bg/60 px-4 py-3"
                >
                  <AppleSwitch
                    size="sm"
                    tone="accent"
                    label={algorithmLabel(name)}
                    checked={algorithms.includes(name)}
                    onCheckedChange={(checked) => toggleAlgorithm(name, checked)}
                  />
                </li>
              ))}
            </ul>
          </fieldset>
        </Section>

        <MotionAccordion
          size="sm"
          itemClassName={cn(cardClass, "rounded-2xl bg-bg/90")}
          items={[
            {
              question: "Advanced settings",
              answer: (
                <div className="grid gap-4 pt-1 sm:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <label htmlFor="seed" className="font-medium text-text">
                      Random seed
                    </label>
                    <input
                      id="seed"
                      type="number"
                      min={0}
                      value={seed}
                      onChange={(event) => setSeed(Number(event.target.value))}
                      className={fieldClass}
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <label htmlFor="test-size" className="font-medium text-text">
                      Test set size (%)
                    </label>
                    <input
                      id="test-size"
                      type="number"
                      min={5}
                      max={50}
                      value={testPercent}
                      onChange={(event) => setTestPercent(Number(event.target.value))}
                      className={fieldClass}
                    />
                  </div>
                </div>
              ),
            },
          ]}
        />
      </div>

      <aside className="lg:sticky lg:top-24 lg:col-span-4">
        <div className={cn(cardClass, "flex flex-col gap-5 rounded-2xl p-6")}>
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface text-text/70"
            >
              <LuFileSpreadsheet className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium">{dataset.original_filename}</p>
              <p className="text-sm text-muted">
                {dataset.validation?.row_count?.toLocaleString()} rows ·{" "}
                {dataset.validation?.column_count?.toLocaleString()} columns
              </p>
            </div>
          </div>

          <dl className="divide-y divide-border/60 border-y border-border/60">
            <SummaryRow label="Target">{target || <span className="text-muted">Not chosen</span>}</SummaryRow>
            <SummaryRow label="Task">{TASKS[task].title}</SummaryRow>
            <SummaryRow label="Metric">
              {metricLabel(effectiveMetric)}
              {metricOption && (
                <span className="block text-xs font-normal text-muted">
                  {directionText(metricOption.higher_is_better)}
                </span>
              )}
            </SummaryRow>
            <SummaryRow label="Algorithms">{algorithms.length}</SummaryRow>
            <SummaryRow label="Test set">
              {testPercent}% · seed {seed}
            </SummaryRow>
          </dl>

          {error && <Alert role="alert">{error}</Alert>}

          <button type="submit" disabled={submitting} className={buttonClass("primary", "lg", "w-full")}>
            <LuPlay aria-hidden="true" className="size-4" />
            {submitting ? "Starting…" : "Run experiment"}
          </button>
          <p className="flex gap-2 text-xs leading-5 text-muted">
            <LuShapes aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />A separate worker
            trains each algorithm; results appear on the next page.
          </p>
        </div>
      </aside>
    </form>
  );
}
