"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { LuArrowUpRight, LuBoxes, LuCloudUpload, LuSearch, LuSearchX } from "react-icons/lu";
import StatusBadge from "@/components/StatusBadge";
import Alert from "@/components/ui/Alert";
import { EmptyState, LoadingState } from "@/components/ui/States";
import { AnimateCount } from "@/components/unlumen-ui/animate-count";
import { CardsViewIcon } from "@/components/unlumen-ui/cards-view-icon";
import { ListViewIcon } from "@/components/unlumen-ui/list-view-icon";
import { errorMessage, listModels } from "@/lib/api";
import { algorithmLabel, formatNumber, metricLabel } from "@/lib/format";
import { notifyError } from "@/lib/notifications";
import type { ApprovalStatus, RegisteredModel } from "@/lib/types";
import { buttonClass, cardClass, fieldClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; models: RegisteredModel[] };

type Filter = "ALL" | ApprovalStatus;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "PENDING", label: "Pending" },
  { value: "APPROVED", label: "Approved" },
  { value: "REVOKED", label: "Revoked" },
];

function modelName(model: RegisteredModel): string {
  return `${model.dataset_filename ?? "Model"} → ${model.target_column}`;
}

function ModelCard({ model }: { model: RegisteredModel }) {
  return (
    <Link
      href={`/models/${model.model_id}`}
      className={cn(
        cardClass,
        "group flex h-full flex-col gap-5 rounded-2xl p-5 transition hover:-translate-y-0.5 hover:border-text/25 hover:shadow-lg",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span
          aria-hidden="true"
          className="flex size-10 items-center justify-center rounded-xl bg-surface text-text/70"
        >
          <LuBoxes className="size-5" />
        </span>
        <StatusBadge status={model.approval_status} />
      </div>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-semibold tracking-tight break-all">{modelName(model)}</p>
        <p className="text-sm text-muted">{algorithmLabel(model.algorithm)}</p>
      </div>
      <p className="text-2xl font-semibold tracking-tight tabular-nums">
        {formatNumber(model.metrics[model.metric])}{" "}
        <span className="text-sm font-medium text-muted">{metricLabel(model.metric)}</span>
      </p>
      <div className="mt-auto flex items-center justify-between border-t border-border/60 pt-4 text-xs text-muted">
        <span className="rounded-md bg-surface px-2 py-0.5 font-medium text-text tabular-nums">
          v{model.version}
        </span>
        <span>{new Date(model.created_at).toLocaleDateString()}</span>
        <LuArrowUpRight
          aria-hidden="true"
          className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
        />
      </div>
    </Link>
  );
}

export default function ModelList() {
  const [view, setView] = useState<View>({ phase: "loading" });
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");
  const [layout, setLayout] = useState<"table" | "cards">("table");

  useEffect(() => {
    const controller = new AbortController();
    listModels(controller.signal)
      .then((models) => setView({ phase: "ready", models }))
      .catch((err) => {
        if (controller.signal.aborted) return;
        const message = errorMessage(err);
        setView({ phase: "error", message });
        notifyError("Could not load models", message);
      });
    return () => controller.abort();
  }, []);

  if (view.phase === "loading") return <LoadingState label="Loading models…" />;
  if (view.phase === "error") return <Alert role="alert">{view.message}</Alert>;
  if (view.models.length === 0) {
    return (
      <EmptyState
        icon={LuBoxes}
        title="No models yet."
        action={
          <Link href="/datasets/new" className={buttonClass("primary")}>
            <LuCloudUpload aria-hidden="true" className="size-4" />
            Upload a dataset
          </Link>
        }
      >
        A model is registered when an experiment succeeds. Upload a dataset to start one.
      </EmptyState>
    );
  }

  const countOf = (value: Filter) =>
    view.models.filter((model) => value === "ALL" || model.approval_status === value).length;
  const needle = query.trim().toLowerCase();
  const shown = view.models.filter(
    (model) =>
      (filter === "ALL" || model.approval_status === filter) &&
      (needle === "" ||
        modelName(model).toLowerCase().includes(needle) ||
        algorithmLabel(model.algorithm).toLowerCase().includes(needle)),
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div
          role="group"
          aria-label="Filter by approval status"
          className="flex w-fit flex-wrap items-center gap-1 rounded-2xl border border-border/60 bg-surface/70 p-1"
        >
          {FILTERS.map(({ value, label }) => {
            const active = filter === value;
            return (
              <button
                key={value}
                type="button"
                aria-pressed={active}
                onClick={() => setFilter(value)}
                className={cn(
                  "relative flex cursor-pointer items-center gap-2 rounded-xl px-3.5 py-1.5 text-sm font-medium transition-colors",
                  active ? "text-text" : "text-muted hover:text-text",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="model-filter"
                    className="absolute inset-0 rounded-xl bg-bg shadow-sm ring-1 ring-border/60"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="relative">{label}</span>
                <span className="relative rounded-md bg-surface px-1.5 text-xs tabular-nums">
                  <AnimateCount>{countOf(value)}</AnimateCount>
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-full lg:w-72">
            <LuSearch
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search models"
              aria-label="Search by dataset, target or algorithm"
              className={cn(fieldClass, "pl-10")}
            />
          </div>
          <div
            role="group"
            aria-label="Layout"
            className="flex shrink-0 items-center gap-1 rounded-xl border border-border/60 bg-surface/70 p-1"
          >
            {(
              [
                ["table", "Table", ListViewIcon],
                ["cards", "Cards", CardsViewIcon],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                aria-pressed={layout === value}
                onClick={() => setLayout(value)}
                className={cn(
                  "flex size-9 cursor-pointer items-center justify-center rounded-lg transition-colors",
                  layout === value ? "bg-bg text-text shadow-sm" : "text-muted hover:text-text",
                )}
              >
                <Icon isActive={layout === value} />
                <span className="sr-only">{label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {shown.length === 0 ? (
        <EmptyState icon={LuSearchX} title="No models match.">
          Try another search or status filter.
        </EmptyState>
      ) : layout === "cards" ? (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence mode="popLayout" initial={false}>
            {shown.map((model) => (
              <motion.li
                key={model.model_id}
                layout
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ type: "spring", stiffness: 350, damping: 28 }}
              >
                <ModelCard model={model} />
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      ) : (
        <div className={cn(cardClass, "overflow-hidden rounded-2xl")}>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">Registered models, newest first</caption>
              <thead className="bg-surface/60 text-xs tracking-wide text-muted uppercase">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">Model</th>
                  <th scope="col" className="px-5 py-3 font-medium">Version</th>
                  <th scope="col" className="px-5 py-3 font-medium">Algorithm</th>
                  <th scope="col" className="px-5 py-3 font-medium">Ranking metric</th>
                  <th scope="col" className="px-5 py-3 font-medium">Status</th>
                  <th scope="col" className="px-5 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((model) => (
                  <tr
                    key={model.model_id}
                    className="border-t border-border/50 transition-colors hover:bg-surface/40"
                  >
                    <th scope="row" className="px-5 py-3.5 font-medium">
                      <Link
                        href={`/models/${model.model_id}`}
                        className="group inline-flex items-center gap-3 break-all"
                      >
                        <span
                          aria-hidden="true"
                          className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface text-text/70"
                        >
                          <LuBoxes className="size-4" />
                        </span>
                        <span className="underline-offset-4 group-hover:underline">
                          {modelName(model)}
                        </span>
                      </Link>
                    </th>
                    <td className="px-5 py-3.5 tabular-nums">
                      <span className="rounded-md bg-surface px-2 py-0.5 text-xs font-medium">
                        v{model.version}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap">{algorithmLabel(model.algorithm)}</td>
                    <td className="px-5 py-3.5 whitespace-nowrap tabular-nums">
                      <span className="text-muted">{metricLabel(model.metric)}</span>{" "}
                      <span className="font-semibold">{formatNumber(model.metrics[model.metric])}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={model.approval_status} />
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-muted">
                      {new Date(model.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
