"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import StatusBadge from "@/components/StatusBadge";
import { errorMessage, listModels } from "@/lib/api";
import { algorithmLabel, formatNumber, metricLabel } from "@/lib/format";
import type { RegisteredModel } from "@/lib/types";

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; models: RegisteredModel[] };

export default function ModelList() {
  const [view, setView] = useState<View>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    listModels(controller.signal)
      .then((models) => setView({ phase: "ready", models }))
      .catch((err) => {
        if (!controller.signal.aborted) setView({ phase: "error", message: errorMessage(err) });
      });
    return () => controller.abort();
  }, []);

  if (view.phase === "loading") {
    return (
      <p role="status" className="text-muted">
        Loading models…
      </p>
    );
  }
  if (view.phase === "error") {
    return (
      <p role="alert" className="rounded-md border border-danger p-3 text-danger">
        {view.message}
      </p>
    );
  }
  if (view.models.length === 0) {
    return (
      <div className="rounded-md border border-border bg-surface p-6">
        <p className="font-medium">No models yet.</p>
        <p className="text-muted">
          A model is registered when an experiment succeeds.{" "}
          <Link href="/datasets/new" className="underline">
            Upload a dataset
          </Link>{" "}
          to start one.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">Registered models, newest first</caption>
        <thead className="bg-surface">
          <tr>
            <th scope="col" className="p-2">Model</th>
            <th scope="col" className="p-2">Version</th>
            <th scope="col" className="p-2">Algorithm</th>
            <th scope="col" className="p-2">Ranking metric</th>
            <th scope="col" className="p-2">Status</th>
            <th scope="col" className="p-2">Created</th>
          </tr>
        </thead>
        <tbody>
          {view.models.map((model) => (
            <tr key={model.model_id} className="border-t border-border">
              <th scope="row" className="p-2 font-medium break-all">
                <Link href={`/models/${model.model_id}`} className="underline">
                  {model.dataset_filename ?? "Model"} → {model.target_column}
                </Link>
              </th>
              <td className="p-2 tabular-nums">v{model.version}</td>
              <td className="p-2">{algorithmLabel(model.algorithm)}</td>
              <td className="p-2 tabular-nums">
                {metricLabel(model.metric)} {formatNumber(model.metrics[model.metric])}
              </td>
              <td className="p-2">
                <StatusBadge status={model.approval_status} />
              </td>
              <td className="p-2 whitespace-nowrap text-muted">
                {new Date(model.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
