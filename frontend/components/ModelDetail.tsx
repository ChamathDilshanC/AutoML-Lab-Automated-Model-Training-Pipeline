"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PredictionForm from "@/components/PredictionForm";
import StatusBadge from "@/components/StatusBadge";
import { approveModel, errorMessage, getModel } from "@/lib/api";
import { algorithmLabel, formatNumber, metricLabel } from "@/lib/format";
import type { FeatureSpec, RegisteredModel } from "@/lib/types";

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; model: RegisteredModel };

function featureType(spec: FeatureSpec): string {
  return spec.value_type === "number" ? "number" : spec.value_type === "boolean" ? "true/false" : "text";
}

function formatBytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function ModelDetail({ modelId }: { modelId: string }) {
  const [view, setView] = useState<View>({ phase: "loading" });
  const [confirming, setConfirming] = useState(false);
  const [approving, setApproving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getModel(modelId, controller.signal)
      .then((model) => setView({ phase: "ready", model }))
      .catch((err) => {
        if (!controller.signal.aborted) setView({ phase: "error", message: errorMessage(err) });
      });
    return () => controller.abort();
  }, [modelId]);

  async function approve() {
    setApproving(true);
    setActionError(null);
    try {
      const model = await approveModel(modelId);
      setView({ phase: "ready", model });
      setConfirming(false);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setApproving(false);
    }
  }

  if (view.phase === "loading") {
    return (
      <p role="status" className="text-muted">
        Loading model…
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

  const { model } = view;
  const metricNames = [model.metric, ...Object.keys(model.metrics).filter((n) => n !== model.metric)];
  const hyperparameters = Object.entries(model.hyperparameters);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold break-all">
            {model.dataset_filename ?? "Model"} → {model.target_column}
          </h1>
          <span className="rounded-full border border-border px-3 py-0.5 text-sm">
            Version {model.version}
          </span>
          <StatusBadge status={model.approval_status} />
        </div>
        <p className="text-muted">
          {algorithmLabel(model.algorithm)} ·{" "}
          {model.task === "classification" ? "Classification" : "Regression"} · from{" "}
          <Link href={`/experiments/${model.experiment_id}`} className="underline">
            the experiment
          </Link>{" "}
          on{" "}
          <Link href={`/datasets/${model.dataset_id}`} className="underline">
            this dataset
          </Link>
        </p>
      </header>

      {model.approval_status === "PENDING" && (
        <section aria-labelledby="approve-title" className="flex flex-col gap-3 rounded-md border border-warning p-4">
          <h2 id="approve-title" className="font-semibold">
            Approval
          </h2>
          <p>This model cannot make predictions until it is approved.</p>
          {!confirming ? (
            <div>
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="rounded-md bg-accent px-4 py-2 font-medium text-on-accent"
              >
                Approve model
              </button>
            </div>
          ) : (
            <div role="group" aria-label="Confirm approval" className="flex flex-col gap-2">
              <p className="font-medium">
                Approve version {model.version} for predictions? It cannot be un-approved from this
                page.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={approve}
                  disabled={approving}
                  className="rounded-md bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-60"
                >
                  {approving ? "Approving…" : "Yes, approve"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  disabled={approving}
                  className="rounded-md border border-border px-4 py-2 font-medium"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {actionError && (
            <p role="alert" className="rounded-md border border-danger p-3 text-danger">
              {actionError}
            </p>
          )}
        </section>
      )}

      <section aria-labelledby="metrics-title" className="flex flex-col gap-3">
        <h2 id="metrics-title" className="text-xl font-semibold">
          Test-set metrics
        </h2>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {metricNames.map((name) => (
            <div key={name} className="rounded-md border border-border bg-surface p-3">
              <dt className="text-sm text-muted">
                {metricLabel(name)}
                {name === model.metric ? " (ranking metric)" : ""}
              </dt>
              <dd className="text-xl font-semibold tabular-nums">{formatNumber(model.metrics[name])}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted">
          Measured on one held-out test set. The model was trained on the training rows only. These
          scores are not a guarantee of real-world performance.
        </p>
      </section>

      <section aria-labelledby="inputs-title" className="flex flex-col gap-3">
        <h2 id="inputs-title" className="text-xl font-semibold">
          Inputs
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <caption className="sr-only">Features the model expects</caption>
            <thead className="bg-surface">
              <tr>
                <th scope="col" className="p-2">Feature</th>
                <th scope="col" className="p-2">Type</th>
                <th scope="col" className="p-2">Values seen in training</th>
              </tr>
            </thead>
            <tbody>
              {model.feature_schema.map((spec) => (
                <tr key={spec.name} className="border-t border-border">
                  <th scope="row" className="p-2 font-medium break-all">{spec.name}</th>
                  <td className="p-2">{featureType(spec)}</td>
                  <td className="p-2 text-muted">
                    {spec.categories ? spec.categories.join(", ") : "any"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <PredictionForm model={model} />

      <details className="text-sm text-muted">
        <summary className="cursor-pointer">Technical details</summary>
        <ul className="mt-2 list-disc pl-6">
          <li>Model ID: {model.model_id}</li>
          <li>
            Tuned parameters:{" "}
            {hyperparameters.length === 0
              ? "none"
              : hyperparameters.map(([k, v]) => `${k}=${v === null ? "None" : String(v)}`).join(", ")}
          </li>
          <li>Artifact size: {formatBytes(model.artifact_bytes)}</li>
          <li>
            Libraries:{" "}
            {Object.entries(model.library_versions)
              .map(([name, version]) => `${name} ${version}`)
              .join(", ")}
          </li>
        </ul>
      </details>
    </div>
  );
}
