"use client";

import { useEffect, useId, useRef } from "react";

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

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault(); // Escape: let the parent decide, and not while busy
        if (!busy) onCancel();
      }}
      className="m-auto w-full max-w-md rounded-lg border border-border bg-bg p-6 text-text backdrop:bg-black/50"
    >
      <h2 id={titleId} className="text-lg font-semibold">
        {title}
      </h2>
      <div className="mt-2 flex flex-col gap-2">{children}</div>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded-md border border-border px-4 py-2 font-medium disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={`rounded-md px-4 py-2 font-medium disabled:opacity-60 ${
            destructive ? "bg-danger text-bg" : "bg-accent text-on-accent"
          }`}
        >
          {busy ? (busyLabel ?? "Working…") : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
