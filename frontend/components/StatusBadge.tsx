import type { DatasetStatus, ExperimentStatus } from "@/lib/types";

type BadgeStatus = DatasetStatus | ExperimentStatus;

const STATUS: Record<BadgeStatus, { label: string; icon: string; color: string }> = {
  UPLOADED: { label: "Uploaded, not validated", icon: "●", color: "text-accent" },
  READY: { label: "Ready", icon: "✓", color: "text-success" },
  REJECTED: { label: "Rejected", icon: "✕", color: "text-danger" },
  CREATED: { label: "Created", icon: "○", color: "text-accent" },
  QUEUED: { label: "Queued", icon: "○", color: "text-accent" },
  RUNNING: { label: "Running", icon: "◐", color: "text-accent" },
  SUCCEEDED: { label: "Succeeded", icon: "✓", color: "text-success" },
  FAILED: { label: "Failed", icon: "✕", color: "text-danger" },
};

/** Status is conveyed by text and icon as well as colour. */
export default function StatusBadge({ status }: { status: BadgeStatus }) {
  const { label, icon, color } = STATUS[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-current px-3 py-0.5 text-sm font-medium ${color}`}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}
