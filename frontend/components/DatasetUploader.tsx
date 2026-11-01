"use client";

import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { IconType } from "react-icons";
import {
  LuCircleCheck,
  LuCloudUpload,
  LuFileSpreadsheet,
  LuListChecks,
  LuLoaderCircle,
  LuUpload,
} from "react-icons/lu";
import Alert from "@/components/ui/Alert";
import { AnimateDigits } from "@/components/unlumen-ui/animate-digits";
import {
  deleteDataset,
  errorMessage,
  registerDataset,
  sendFile,
  validateDataset,
} from "@/lib/api";
import { notifyError, notifyPromise, notifySuccess, notifyWarning } from "@/lib/notifications";
import type { DatasetUpload } from "@/lib/types";
import { buttonClass, cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

type Phase = "idle" | "preparing" | "uploading" | "validating";

const PHASES: { phase: Exclude<Phase, "idle">; label: string; icon: IconType }[] = [
  { phase: "preparing", label: "Prepare", icon: LuFileSpreadsheet },
  { phase: "uploading", label: "Upload", icon: LuUpload },
  { phase: "validating", label: "Validate", icon: LuListChecks },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DatasetUploader() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  const busy = phase !== "idle";
  const percent = Math.round(progress * 100);

  async function handleFile(selected: File | undefined) {
    if (!selected || busy) return;
    setError(null);
    if (!selected.name.toLowerCase().endsWith(".csv")) {
      const message = "Only .csv files are supported.";
      setError(message);
      notifyError("Upload rejected", message);
      return;
    }
    if (selected.size === 0) {
      const message = "The file is empty.";
      setError(message);
      notifyError("Upload rejected", message);
      return;
    }
    setFile(selected);
    let registered: DatasetUpload | null = null;
    try {
      setPhase("preparing");
      setProgress(0);
      registered = await notifyPromise(upload(selected), {
        loading: "Uploading your dataset",
        loadingDescription: selected.name,
        success: "Upload complete",
        successDescription: "Checking the file now…",
        error: "Dataset upload failed",
      });
      setPhase("validating");
      const report = await validateDataset(registered.dataset_id);
      if (report.status === "READY") {
        notifySuccess(
          "Dataset ready",
          `${report.row_count?.toLocaleString() ?? "?"} rows and ${report.column_count?.toLocaleString() ?? "?"} columns validated.`,
        );
      } else {
        notifyWarning("Dataset rejected", report.message ?? "See the report for the reason.");
      }
      router.push(`/datasets/${registered.dataset_id}`);
    } catch (err) {
      const message = errorMessage(err);
      setError(message);
      setPhase("idle");
      // A failed upload has already said so in its own toast and cleaned up after itself.
      if (registered) {
        notifyError("Dataset validation failed", message);
        void deleteDataset(registered.dataset_id).catch(() => undefined);
      }
    }
  }

  /** Register the dataset and send its bytes. On failure, remove the half-made record. */
  async function upload(selected: File): Promise<DatasetUpload> {
    const created = await registerDataset(selected);
    try {
      setPhase("uploading");
      await sendFile(created.upload, selected, setProgress);
      return created;
    } catch (err) {
      // Do not leave a record that is waiting for a file that never arrived.
      void deleteDataset(created.dataset_id).catch(() => undefined);
      throw err;
    }
  }

  const activeIndex = PHASES.findIndex((step) => step.phase === phase);

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void handleFile(event.dataTransfer.files[0]);
        }}
        className={cn(
          cardClass,
          "relative flex flex-col items-center gap-5 overflow-hidden border-2 border-dashed px-6 py-14 text-center transition-colors sm:py-20",
          dragging ? "border-accent bg-accent/[0.03]" : "border-border/80",
        )}
      >
        <motion.span
          aria-hidden="true"
          animate={dragging ? { scale: 1.08, y: -4 } : { scale: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 400, damping: 22 }}
          className="relative flex size-20 items-center justify-center rounded-3xl border border-border/70 bg-bg text-text shadow-sm"
        >
          {dragging && (
            <span className="absolute inset-0 animate-ping rounded-3xl border-2 border-accent/40" />
          )}
          <LuCloudUpload className={cn("size-9", dragging && "text-accent")} />
        </motion.span>
        <div className="flex flex-col gap-1">
          <p className="text-xl font-semibold tracking-tight">
            {dragging ? "Drop it here" : "Drag a CSV file here, or choose one."}
          </p>
          <p className="text-sm text-muted">
            The file is checked after upload. Large files may be rejected by the server.
          </p>
        </div>
        <label
          className={cn(
            buttonClass("primary", "lg"),
            "focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent",
            busy ? "pointer-events-none opacity-60" : "cursor-pointer",
          )}
        >
          <LuFileSpreadsheet aria-hidden="true" className="size-5" />
          Choose CSV file
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            className="sr-only"
            onChange={(event) => {
              void handleFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      </div>

      <div role="status" aria-live="polite">
        {busy && file && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(cardClass, "flex flex-col gap-5 rounded-2xl p-5")}
          >
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface text-text/70"
              >
                <LuFileSpreadsheet className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{file.name}</p>
                <p className="text-xs text-muted">{formatBytes(file.size)}</p>
              </div>
              {phase === "uploading" && (
                <span className="flex items-baseline text-lg font-semibold">
                  <AnimateDigits value={String(percent)} />
                  <span className="text-sm text-muted">%</span>
                  <span className="sr-only">uploaded</span>
                </span>
              )}
            </div>

            <div className="h-2 overflow-hidden rounded-full bg-surface">
              <motion.div
                className="h-full rounded-full bg-accent"
                initial={false}
                animate={{
                  width: phase === "validating" ? "100%" : phase === "uploading" ? `${percent}%` : "4%",
                }}
                transition={{ type: "spring", stiffness: 120, damping: 24 }}
              />
            </div>

            <ol className="grid grid-cols-3 gap-2">
              {PHASES.map(({ phase: step, label, icon: Icon }, index) => {
                const done = index < activeIndex;
                const current = index === activeIndex;
                return (
                  <li
                    key={step}
                    aria-current={current ? "step" : undefined}
                    className={cn(
                      "flex items-center gap-2 rounded-xl border px-3 py-2 text-sm",
                      current
                        ? "border-accent/30 bg-accent/[0.05] text-text"
                        : done
                          ? "border-success/25 text-success"
                          : "border-border/60 text-muted",
                    )}
                  >
                    {current ? (
                      <LuLoaderCircle aria-hidden="true" className="size-4 animate-spin text-accent" />
                    ) : done ? (
                      <LuCircleCheck aria-hidden="true" className="size-4" />
                    ) : (
                      <Icon aria-hidden="true" className="size-4" />
                    )}
                    {label}
                  </li>
                );
              })}
            </ol>
            <span className="sr-only">
              {phase === "preparing" && "Preparing the upload…"}
              {phase === "uploading" && `Uploading… ${percent}%`}
              {phase === "validating" && "Validating the file…"}
            </span>
          </motion.div>
        )}
      </div>

      {error && (
        <Alert role="alert" title="The upload did not finish">
          {error}
        </Alert>
      )}
    </div>
  );
}
