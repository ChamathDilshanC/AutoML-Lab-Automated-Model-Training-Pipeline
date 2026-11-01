"use client";

import { useEffect, useId, useRef } from "react";
import { LuShieldCheck, LuTriangleAlert } from "react-icons/lu";
import Alert from "@/components/ui/Alert";
import { buttonClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  busyLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A modal confirmation built on the native <dialog> element, which traps focus, closes on Escape
 * and marks the rest of the page inert. "Cancel" comes first so it receives the initial focus.
 */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  busyLabel,
  destructive = false,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const Icon = destructive ? LuTriangleAlert : LuShieldCheck;

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault(); // Escape: let the parent decide, and not while busy
        if (!busy) onCancel();
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-md rounded-3xl border border-border/70 bg-bg p-6 text-text shadow-2xl shadow-black/20 sm:p-7"
    >
      <div className="flex gap-4">
        <span
          aria-hidden="true"
          className={cn(
            "flex size-11 shrink-0 items-center justify-center rounded-2xl",
            destructive ? "bg-danger/10 text-danger" : "bg-accent/10 text-accent",
          )}
        >
          <Icon className="size-5" />
        </span>
        <div className="flex min-w-0 flex-col gap-2">
          <h2 id={titleId} className="text-lg font-semibold tracking-tight">
            {title}
          </h2>
          <div className="flex flex-col gap-2 text-sm leading-6 text-muted">{children}</div>
        </div>
      </div>
      {error && (
        <Alert role="alert" className="mt-4">
          {error}
        </Alert>
      )}
      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className={buttonClass("secondary")}
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={buttonClass(destructive ? "danger" : "primary")}
        >
          {busy ? (busyLabel ?? "Working…") : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
