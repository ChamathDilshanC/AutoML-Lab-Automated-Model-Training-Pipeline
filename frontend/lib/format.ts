const METRIC_LABELS: Record<string, string> = {
  accuracy: "Accuracy",
  precision: "Precision",
  recall: "Recall",
  f1: "F1",
  roc_auc: "ROC-AUC",
  mae: "MAE",
  rmse: "RMSE",
  r2: "R²",
};

export function metricLabel(name: string): string {
  return METRIC_LABELS[name] ?? name;
}

/** `random_forest` becomes `Random Forest`. */
export function algorithmLabel(name: string): string {
  return name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatNumber(value: number | null | undefined, digits = 4): string {
  return value === null || value === undefined ? "n/a" : value.toFixed(digits);
}

export function directionText(higherIsBetter: boolean): string {
  return higherIsBetter ? "higher is better" : "lower is better";
}
