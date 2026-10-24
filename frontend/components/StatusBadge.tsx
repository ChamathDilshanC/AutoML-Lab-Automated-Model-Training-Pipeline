import type { DatasetStatus } from "@/lib/types";

const STATUS: Record<DatasetStatus, { label: string; icon: string; color: string }> = {
  UPLOADED: { label: "Uploaded, not validated", icon: "●", color: "text-accent" },
  READY: { label: "Ready", icon: "✓", color: "text-success" },
  REJECTED: { label: "Rejected", icon: "✕", color: "text-danger" },
};

/** Status is conveyed by text and icon as well as colour. */
export default function StatusBadge({ status }: { status: DatasetStatus }) {
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
