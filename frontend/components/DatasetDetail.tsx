"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataQualityReport from "@/components/DataQualityReport";
import { deleteDataset, errorMessage, getDataset, validateDataset } from "@/lib/api";
import { notifyError, notifySuccess } from "@/lib/notifications";
import type { Dataset } from "@/lib/types";

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
      await deleteDataset(datasetId);
      notifySuccess("Dataset deleted");
      router.push("/datasets/new");
    } catch (err) {
      const message = errorMessage(err);
      setDeleteError(message);
      notifyError("Dataset deletion failed", message);
      setDeleting(false);
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
      {(view.dataset.status === "UPLOADED" || view.dataset.status === "PENDING_UPLOAD") && (
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
      <div className="border-t border-border pt-4">
        <button
          type="button"
          onClick={() => {
            setDeleteError(null);
            setConfirmingDelete(true);
          }}
          className="rounded-md border border-danger px-4 py-2 font-medium text-danger"
        >
          Delete dataset
        </button>
      </div>
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
          This permanently deletes <strong className="break-all">{view.dataset.original_filename}</strong>{" "}
          and everything made from it: its experiments, their results, and its models (including
          approved ones), together with all stored files.
        </p>
        <p className="font-medium">This cannot be undone.</p>
      </ConfirmDialog>
    </div>
  );
}
