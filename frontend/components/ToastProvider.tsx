"use client";

import { GoeyToaster } from "goey-toast";
import "goey-toast/styles.css";

export default function ToastProvider() {
  return (
    <GoeyToaster
      position="bottom-right"
      theme="light"
      preset="smooth"
      closeButton="top-right"
      visibleToasts={4}
      showProgress
      showTimestamp={false}
      toastOptions={{
        className: "automl-toast",
      }}
    />
  );
}
