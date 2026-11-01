"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { IconType } from "react-icons";
import { LuBan, LuBoxes, LuClock, LuCopy, LuGauge, LuShieldCheck, LuShieldOff } from "react-icons/lu";
import ConfirmDialog from "@/components/ConfirmDialog";
import PredictionForm from "@/components/PredictionForm";
import StatusBadge from "@/components/StatusBadge";
import Alert from "@/components/ui/Alert";
import StatCard from "@/components/ui/StatCard";
import { LoadingState } from "@/components/ui/States";
import { MotionAccordion } from "@/components/unlumen-ui/motion-faqs-accordion";
import { approveModel, errorMessage, getModel, revokeModel } from "@/lib/api";
import { algorithmLabel, formatNumber, metricLabel } from "@/lib/format";
import { notifyError, notifyPromise, notifySuccess } from "@/lib/notifications";
import type { ApprovalStatus, FeatureSpec, RegisteredModel } from "@/lib/types";
import { buttonClass, cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

type View =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; model: RegisteredModel };

const APPROVAL: Record<ApprovalStatus, { icon: IconType; title: string; box: string; iconBox: string }> = {
  PENDING: {
    icon: LuClock,
    title: "Waiting for approval",
    box: "border-warning/30",
    iconBox: "bg-warning/10 text-warning",
  },
  APPROVED: {
    icon: LuShieldCheck,
    title: "Approved",
    box: "border-success/30",
    iconBox: "bg-success/10 text-success",
  },
  REVOKED: {
    icon: LuBan,
    title: "Approval revoked",
    box: "border-danger/30",
    iconBox: "bg-danger/10 text-danger",
  },
};

function featureType(spec: FeatureSpec): string {
  return spec.value_type === "number" ? "number" : spec.value_type === "boolean" ? "true/false" : "text";
}

function formatBytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function ModelDetail({ modelId }: { modelId: string }) {
  const [view, setView] = useState<View>({ phase: "loading" });
  const [dialog, setDialog] = useState<"approve" | "revoke" | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getModel(modelId, controller.signal)
      .then((model) => setView({ phase: "ready", model }))
      .catch((err) => {
        if (controller.signal.aborted) return;
        const message = errorMessage(err);
        setView({ phase: "error", message });
        notifyError("Could not load the model", message);
      });
    return () => controller.abort();
  }, [modelId]);

  function openDialog(kind: "approve" | "revoke") {
    setActionError(null);
    setDialog(kind);
  }

  async function perform(kind: "approve" | "revoke") {
    setBusy(true);
    setActionError(null);
    try {
      const model = await notifyPromise(kind === "approve" ? approveModel(modelId) : revokeModel(modelId), {
        loading: kind === "approve" ? "Approving the model" : "Revoking the model",
        success: kind === "approve" ? "Model approved" : "Model revoked",
        successDescription:
          kind === "approve"
            ? "It can now answer prediction requests."
            : "It no longer answers prediction requests.",
        error: "Model update failed",
      });
      setView({ phase: "ready", model });
      setDialog(null);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function copyId(id: string) {
    try {
      await navigator.clipboard.writeText(id);
      notifySuccess("Model ID copied");
    } catch {
      notifyError("Could not copy the model ID", "Select the ID and copy it by hand.");
    }
  }

  if (view.phase === "loading") return <LoadingState label="Loading model…" />;
  if (view.phase === "error") {
    return (
      <Alert role="alert" title="Could not load the model">
        {view.message}
      </Alert>
    );
  }

  const { model } = view;
  const metricNames = [model.metric, ...Object.keys(model.metrics).filter((n) => n !== model.metric)];
  const hyperparameters = Object.entries(model.hyperparameters);
  const approval = APPROVAL[model.approval_status];

  return (
    <div className="flex flex-col gap-10">
      <header className="flex min-w-0 gap-4">
        <span
          aria-hidden="true"
          className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-bg text-text shadow-sm"
        >
          <LuBoxes className="size-6" />
        </span>
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight break-all">
              {model.dataset_filename ?? "Model"} → {model.target_column}
            </h1>
            <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-semibold">
              Version {model.version}
            </span>
            <StatusBadge status={model.approval_status} />
          </div>
          <p className="text-sm text-muted">
            {algorithmLabel(model.algorithm)} ·{" "}
            {model.task === "classification" ? "Classification" : "Regression"} · from{" "}
            <Link href={`/experiments/${model.experiment_id}`} className="font-medium text-text underline-offset-4 hover:underline">
              the experiment
            </Link>{" "}
            on{" "}
            <Link href={`/datasets/${model.dataset_id}`} className="font-medium text-text underline-offset-4 hover:underline">
              this dataset
            </Link>
          </p>
        </div>
      </header>

      <section
        aria-labelledby="approval-title"
        className={cn(
          cardClass,
          "flex flex-col gap-5 rounded-2xl p-6 sm:flex-row sm:items-center sm:justify-between",
          approval.box,
        )}
      >
        <div className="flex gap-4">
          <span
            aria-hidden="true"
            className={cn("flex size-12 shrink-0 items-center justify-center rounded-2xl", approval.iconBox)}
          >
            <approval.icon className="size-6" />
          </span>
          <div className="flex flex-col gap-1">
            <h2 id="approval-title" className="font-semibold tracking-tight">
              Approval: {approval.title}
            </h2>
            <p className="max-w-2xl text-sm text-muted">
              {model.approval_status === "PENDING" &&
                "This model cannot make predictions until it is approved."}
              {model.approval_status === "APPROVED" &&
                "This model is approved and can make predictions."}
              {model.approval_status === "REVOKED" &&
                "Approval was revoked, so this version can no longer make predictions. Run a new experiment on the dataset to create a new version."}
            </p>
          </div>
        </div>
        {model.approval_status === "PENDING" && (
          <button type="button" onClick={() => openDialog("approve")} className={buttonClass("primary")}>
            <LuShieldCheck aria-hidden="true" className="size-4" />
            Approve model
          </button>
        )}
        {model.approval_status === "APPROVED" && (
          <button
            type="button"
            onClick={() => openDialog("revoke")}
            className={buttonClass("danger-outline")}
          >
            <LuShieldOff aria-hidden="true" className="size-4" />
            Revoke approval
          </button>
        )}
      </section>

      <ConfirmDialog
        open={dialog === "approve"}
        title={`Approve version ${model.version}?`}
        confirmLabel="Yes, approve"
        busyLabel="Approving…"
        busy={busy}
        error={dialog === "approve" ? actionError : null}
        onConfirm={() => perform("approve")}
        onCancel={() => setDialog(null)}
      >
        <p>Approving lets this model answer prediction requests from this account.</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "revoke"}
        title={`Revoke version ${model.version}?`}
        confirmLabel="Revoke model"
        busyLabel="Revoking…"
        destructive
        busy={busy}
        error={dialog === "revoke" ? actionError : null}
        onConfirm={() => perform("revoke")}
        onCancel={() => setDialog(null)}
      >
        <p>The model stops answering predictions immediately.</p>
        <p className="font-medium text-text">
          This cannot be undone. A revoked version cannot be approved again; you would run a new
          experiment to get a new version.
        </p>
      </ConfirmDialog>

      <section aria-labelledby="metrics-title" className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <h2 id="metrics-title" className="text-2xl font-semibold tracking-tight">
            Test-set metrics
          </h2>
          <p className="text-sm text-muted">
            Measured on one held-out test set. The model was trained on the training rows only.
            These scores are not a guarantee of real-world performance.
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-[repeat(auto-fit,minmax(11rem,1fr))]">
          {metricNames.map((name) => (
            <StatCard
              key={name}
              label={metricLabel(name)}
              value={formatNumber(model.metrics[name])}
              hint={name === model.metric ? "Ranking metric" : undefined}
              highlight={name === model.metric}
              icon={name === model.metric ? LuGauge : undefined}
            />
          ))}
        </dl>
      </section>

      <PredictionForm model={model} />

      <section aria-labelledby="inputs-title" className="flex flex-col gap-5">
        <h2 id="inputs-title" className="text-2xl font-semibold tracking-tight">
          Inputs
        </h2>
        <div className={cn(cardClass, "overflow-hidden rounded-2xl")}>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">Features the model expects</caption>
              <thead className="bg-surface/60 text-xs tracking-wide text-muted uppercase">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">Feature</th>
                  <th scope="col" className="px-5 py-3 font-medium">Type</th>
                  <th scope="col" className="px-5 py-3 font-medium">Values seen in training</th>
                </tr>
              </thead>
              <tbody>
                {model.feature_schema.map((spec) => (
                  <tr key={spec.name} className="border-t border-border/50 transition-colors hover:bg-surface/40">
                    <th scope="row" className="px-5 py-3 font-medium break-all">{spec.name}</th>
                    <td className="px-5 py-3">
                      <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium">
                        {featureType(spec)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-muted">
                      {spec.categories ? spec.categories.join(", ") : "any"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <MotionAccordion
        size="sm"
        itemClassName={cn(cardClass, "rounded-2xl bg-bg/90")}
        items={[
          {
            question: "Technical details",
            answer: (
              <ul className="flex flex-col gap-2">
                <li className="flex flex-wrap items-center gap-2">
                  Model ID: <code className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-xs break-all">{model.model_id}</code>
                  <button
                    type="button"
                    onClick={() => void copyId(model.model_id)}
                    className={buttonClass("ghost", "sm", "h-7 px-2")}
                  >
                    <LuCopy aria-hidden="true" className="size-3.5" />
                    Copy
                  </button>
                </li>
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
            ),
          },
        ]}
      />
    </div>
  );
}
