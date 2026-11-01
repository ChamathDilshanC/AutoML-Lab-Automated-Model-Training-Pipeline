import { gooeyToast, type GooeyToastAction } from "goey-toast";
import type { ReactNode } from "react";
import { errorMessage } from "@/lib/api";

// Every toast in the app goes through these helpers, so they look and behave the same.
// Messages must never contain secrets or tokens; errors use the same safe text as inline errors.

export function notifyError(message: string, description: ReactNode = "Please try again.") {
  gooeyToast.error(message, { description, showTimestamp: false });
}

export function notifySuccess(message: string, description?: ReactNode, action?: GooeyToastAction) {
  gooeyToast.success(message, { description, action, showTimestamp: false });
}

export function notifyInfo(message: string, description?: ReactNode) {
  gooeyToast.info(message, { description, showTimestamp: false });
}

export function notifyWarning(message: string, description?: ReactNode, action?: GooeyToastAction) {
  gooeyToast.warning(message, { description, action, showTimestamp: false });
}

interface PromiseMessages<T> {
  loading: string;
  loadingDescription?: ReactNode;
  success: string | ((result: T) => string);
  successDescription?: ReactNode | ((result: T) => ReactNode);
  error: string;
}

/**
 * One toast that shows `loading` while the promise runs and then morphs into its outcome. A
 * failure is described with the same safe text as inline errors. Returns the promise unchanged,
 * so the caller still awaits it and handles the error itself.
 */
export function notifyPromise<T>(promise: Promise<T>, messages: PromiseMessages<T>): Promise<T> {
  gooeyToast.promise(promise, {
    loading: messages.loading,
    success: messages.success,
    error: messages.error,
    description: {
      loading: messages.loadingDescription,
      success: messages.successDescription,
      error: (err: unknown) => errorMessage(err),
    },
    showTimestamp: false,
  });
  return promise;
}
