import type { IconType } from "react-icons";
import { LuCircleCheck, LuCircleX, LuInfo, LuTriangleAlert } from "react-icons/lu";
import { cn } from "@/lib/utils";

type Tone = "danger" | "warning" | "success" | "info";

const TONES: Record<Tone, { icon: IconType; box: string; color: string }> = {
  danger: { icon: LuCircleX, box: "border-danger/25 bg-danger/[0.04]", color: "text-danger" },
  warning: { icon: LuTriangleAlert, box: "border-warning/25 bg-warning/[0.05]", color: "text-warning" },
  success: { icon: LuCircleCheck, box: "border-success/25 bg-success/[0.05]", color: "text-success" },
  info: { icon: LuInfo, box: "border-accent/20 bg-accent/[0.04]", color: "text-accent" },
};

interface Props {
  tone?: Tone;
  title?: React.ReactNode;
  children?: React.ReactNode;
  /** "alert" for blocking errors, "status" for polite updates, none for static notes. */
  role?: "alert" | "status";
  className?: string;
}

/** An inline message. Its meaning is carried by the icon and text as well as the colour. */
export default function Alert({ tone = "danger", title, children, role, className }: Props) {
  const { icon: Icon, box, color } = TONES[tone];
  return (
    <div role={role} className={cn("flex gap-3 rounded-2xl border p-4 text-sm", box, className)}>
      <Icon aria-hidden="true" className={cn("mt-0.5 size-5 shrink-0", color)} />
      <div className="flex min-w-0 flex-col gap-1">
        {title && <p className={cn("font-semibold", color)}>{title}</p>}
        {children && <div className="break-words text-text/90">{children}</div>}
      </div>
    </div>
  );
}
