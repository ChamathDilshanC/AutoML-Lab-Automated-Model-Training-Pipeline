"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { errorMessage, uploadDataset, validateDataset } from "@/lib/api";

type Phase = "idle" | "uploading" | "validating";

export default function DatasetUploader() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const busy = phase !== "idle";

  async function handleFile(file: File | undefined) {
    if (!file || busy) return;
    setError(null);
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Only .csv files are supported.");
      return;
    }
    try {
      setPhase("uploading");
      setProgress(0);
      const dataset = await uploadDataset(file, setProgress);
      setPhase("validating");
      await validateDataset(dataset.dataset_id);
      router.push(`/datasets/${dataset.dataset_id}`);
    } catch (err) {
      setError(errorMessage(err));
      setPhase("idle");
    }
  }

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
        className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-8 text-center ${
          dragging ? "border-accent bg-surface" : "border-border"
        }`}
      >
        <p className="text-base">Drag a CSV file here, or choose one.</p>
        <label
          className={`rounded-md bg-accent px-4 py-2 font-medium text-on-accent focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent ${
            busy ? "opacity-60" : "cursor-pointer"
          }`}
        >
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
        <p className="text-sm text-muted">
          The file is checked after upload. Large files may be rejected by the server.
        </p>
      </div>

      <div role="status" aria-live="polite">
        {phase === "uploading" && (
          <div className="flex flex-col gap-1">
            <progress
              value={Math.round(progress * 100)}
              max={100}
              aria-label="Upload progress"
              className="w-full"
            />
            <span className="text-sm text-muted">Uploading… {Math.round(progress * 100)}%</span>
          </div>
        )}
        {phase === "validating" && <span className="text-sm text-muted">Validating the file…</span>}
      </div>

      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
