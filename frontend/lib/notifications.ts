import { gooeyToast } from "goey-toast";

export function notifyError(message: string, description = "Please try again.") {
  gooeyToast.error(message, { description, showTimestamp: false });
}

export function notifySuccess(message: string, description?: string) {
  gooeyToast.success(message, { description, showTimestamp: false });
}

export function notifyInfo(message: string, description?: string) {
  gooeyToast.info(message, { description, showTimestamp: false });
}
