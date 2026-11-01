import type { IconType } from "react-icons";
import {
  LuBan,
  LuCircleCheck,
  LuCircleDashed,
  LuCircleX,
  LuClock,
  LuCloudUpload,
  LuLoaderCircle,
  LuShieldCheck,
} from "react-icons/lu";
import type { ApprovalStatus, DatasetStatus, ExperimentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type BadgeStatus = DatasetStatus | ExperimentStatus | ApprovalStatus;

const TONE = {
  info: "bg-accent/[0.07] text-accent ring-accent/20",
  success: "bg-success/[0.08] text-success ring-success/20",
  warning: "bg-warning/[0.08] text-warning ring-warning/20",
  danger: "bg-danger/[0.07] text-danger ring-danger/20",
};

const STATUS: Record<BadgeStatus, { label: string; icon: IconType; tone: keyof typeof TONE }> = {
  PENDING_UPLOAD: { label: "Waiting for upload", icon: LuClock, tone: "warning" },
  UPLOADED: { label: "Uploaded, not validated", icon: LuCloudUpload, tone: "info" },
  READY: { label: "Ready", icon: LuCircleCheck, tone: "success" },
  REJECTED: { label: "Rejected", icon: LuCircleX, tone: "danger" },
  CREATED: { label: "Created", icon: LuCircleDashed, tone: "info" },
  QUEUED: { label: "Queued", icon: LuClock, tone: "info" },
  RUNNING: { label: "Running", icon: LuLoaderCircle, tone: "info" },
  SUCCEEDED: { label: "Succeeded", icon: LuCircleCheck, tone: "success" },
  FAILED: { label: "Failed", icon: LuCircleX, tone: "danger" },
  PENDING: { label: "Pending approval", icon: LuClock, tone: "warning" },
  APPROVED: { label: "Approved", icon: LuShieldCheck, tone: "success" },
  REVOKED: { label: "Revoked", icon: LuBan, tone: "danger" },
};

/** Status is conveyed by text and icon as well as colour. */
export default function StatusBadge({
  status,
  className,
}: {
  status: BadgeStatus;
  className?: string;
}) {
  const { label, icon: Icon, tone } = STATUS[status];
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap ring-1 ring-inset",
        TONE[tone],
        className,
      )}
    >
      <Icon aria-hidden="true" className={cn("size-3.5", status === "RUNNING" && "animate-spin")} />
      {label}
    </span>
  );
}
