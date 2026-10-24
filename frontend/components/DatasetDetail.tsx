"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import DataQualityReport from "@/components/DataQualityReport";
import { errorMessage, getDataset, validateDataset } from "@/lib/api";
import type { Dataset } from "@/lib/types";

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; dataset: Dataset };

export default function DatasetDetail({ datasetId }: { datasetId: string }) {
  const [view, setView] = useState<View>({ phase: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [validating, setValidating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDataset(datasetId, controller.signal)
      .then((dataset) => setView({ phase: "ready", dataset }))
      .catch((err) => {
        if (!controller.signal.aborted) setView({ phase: "error", message: errorMessage(err) });
      });
    return () => controller.abort();
  }, [datasetId, reloadKey]);

  async function runValidation() {
    setValidating(true);
    setActionError(null);
    try {
      await validateDataset(datasetId);
      setReloadKey((key) => key + 1);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setValidating(false);
    }
  }

  if (view.phase === "loading") {
    return (
      <p role="status" className="text-muted">
        Loading dataset…
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

  return (
    <div className="flex flex-col gap-4">
      <DataQualityReport dataset={view.dataset} />
      {view.dataset.status === "READY" && (
        <div>
          <Link
            href={`/experiments/new?dataset=${view.dataset.dataset_id}`}
            className="inline-block rounded-md bg-accent px-4 py-2 font-medium text-on-accent"
          >
            Create an experiment
          </Link>
        </div>
      )}
      {view.dataset.status === "UPLOADED" && (
        <div>
          <button
            type="button"
            onClick={runValidation}
            disabled={validating}
            className="rounded-md bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-60"
          >
            {validating ? "Validating…" : "Validate now"}
          </button>
        </div>
      )}
      {actionError && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {actionError}
        </p>
      )}
    </div>
  );
}
