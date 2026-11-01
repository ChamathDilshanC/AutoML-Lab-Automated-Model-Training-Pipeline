"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LuFileSpreadsheet, LuFlaskConical, LuListChecks, LuRefreshCw, LuTrash2 } from "react-icons/lu";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataQualityReport, { formatBytes } from "@/components/DataQualityReport";
import StatusBadge from "@/components/StatusBadge";
import Alert from "@/components/ui/Alert";
import { LoadingState } from "@/components/ui/States";
import { deleteDataset, errorMessage, getDataset, validateDataset } from "@/lib/api";
import { notifyError, notifyPromise, notifySuccess, notifyWarning } from "@/lib/notifications";
import type { Dataset } from "@/lib/types";
import { buttonClass } from "@/lib/ui";

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; dataset: Dataset };

export default function DatasetDetail({ datasetId }: { datasetId: string }) {
  const router = useRouter();
  const [view, setView] = useState<View>({ phase: "loading" });
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [validating, setValidating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDataset(datasetId, controller.signal)
      .then((dataset) => setView({ phase: "ready", dataset }))
      .catch((err) => {
        if (controller.signal.aborted) return;
        const message = errorMessage(err);
        setView({ phase: "error", message });
        notifyError("Could not load the dataset", message);
      });
    return () => controller.abort();
  }, [datasetId, reloadKey]);

  async function runValidation() {
    setValidating(true);
    setActionError(null);
    try {
      const report = await validateDataset(datasetId);
      if (report.status === "READY") {
        notifySuccess("Dataset validated", "It is ready for an experiment.");
      } else {
        notifyWarning("Dataset rejected", report.message ?? "See the report for the reason.");
      }
      setReloadKey((key) => key + 1);
    } catch (err) {
      const message = errorMessage(err);
      setActionError(message);
      notifyError("Validation failed", message);
    } finally {
      setValidating(false);
    }
  }

  async function remove() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await notifyPromise(deleteDataset(datasetId), {
        loading: "Deleting the dataset",
        success: "Dataset deleted",
        successDescription: "Its experiments and models were removed too.",
        error: "Dataset deletion failed",
      });
      router.push("/datasets/new");
    } catch (err) {
      setDeleteError(errorMessage(err));
      setDeleting(false);
    }
  }

  if (view.phase === "loading") return <LoadingState label="Loading dataset…" />;
  if (view.phase === "error") {
    return (
      <div className="flex flex-col items-start gap-4">
        <Alert role="alert" title="Could not load the dataset" className="w-full">
          {view.message}
        </Alert>
        <button
          type="button"
          onClick={() => {
            setView({ phase: "loading" });
            setReloadKey((key) => key + 1);
          }}
          className={buttonClass("secondary")}
        >
          <LuRefreshCw aria-hidden="true" className="size-4" />
          Try again
        </button>
      </div>
    );
  }

  const { dataset } = view;
  const needsValidation = dataset.status === "UPLOADED" || dataset.status === "PENDING_UPLOAD";

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex min-w-0 gap-4">
          <span
            aria-hidden="true"
            className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-bg text-text shadow-sm"
          >
            <LuFileSpreadsheet className="size-6" />
          </span>
          <div className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight break-all">
                {dataset.original_filename}
              </h1>
              <StatusBadge status={dataset.status} />
            </div>
            <p className="text-sm text-muted">
              Uploaded {new Date(dataset.created_at).toLocaleString()} ·{" "}
              {formatBytes(dataset.size_bytes)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          {dataset.status === "READY" && (
            <Link
              href={`/experiments/new?dataset=${dataset.dataset_id}`}
              className={buttonClass("primary")}
            >
              <LuFlaskConical aria-hidden="true" className="size-4" />
              Create an experiment
            </Link>
          )}
          {needsValidation && (
            <button
              type="button"
              onClick={runValidation}
              disabled={validating}
              className={buttonClass("primary")}
            >
              <LuListChecks aria-hidden="true" className="size-4" />
              {validating ? "Validating…" : "Validate now"}
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setDeleteError(null);
              setConfirmingDelete(true);
            }}
            className={buttonClass("danger-outline")}
          >
            <LuTrash2 aria-hidden="true" className="size-4" />
            Delete dataset
          </button>
        </div>
      </header>

      {actionError && <Alert role="alert">{actionError}</Alert>}

      <DataQualityReport dataset={dataset} />

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this dataset?"
        confirmLabel="Delete dataset"
        busyLabel="Deleting…"
        destructive
        busy={deleting}
        error={deleteError}
        onConfirm={remove}
        onCancel={() => setConfirmingDelete(false)}
      >
        <p>
          This permanently deletes{" "}
          <strong className="break-all text-text">{dataset.original_filename}</strong> and
          everything made from it: its experiments, their results, and its models (including
          approved ones), together with all stored files.
        </p>
        <p className="font-medium text-text">This cannot be undone.</p>
      </ConfirmDialog>
    </div>
  );
}
