export type DatasetStatus = "PENDING_UPLOAD" | "UPLOADED" | "READY" | "REJECTED";

export interface ColumnSummary {
  name: string;
  kind: "numeric" | "categorical";
  missing_count: number;
  missing_percent: number;
  unique_count: number;
}

export interface QualityWarning {
  code: string;
  severity: "info" | "warning";
  message: string;
  columns: string[];
}

export interface ValidationReport {
  status: DatasetStatus;
  row_count: number | null;
  column_count: number | null;
  columns: ColumnSummary[];
  warnings: QualityWarning[];
  message: string | null;
}

export interface Dataset {
  dataset_id: string;
  original_filename: string;
  size_bytes: number;
  status: DatasetStatus;
  created_at: string;
  validation: ValidationReport | null;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { field: string; issue: string }[];
    request_id: string | null;
  };
}

export type Task = "classification" | "regression";

export type ExperimentStatus = "CREATED" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";

export const TERMINAL_EXPERIMENT_STATUSES: ExperimentStatus[] = ["SUCCEEDED", "FAILED"];

export interface MetricOption {
  name: string;
  higher_is_better: boolean;
}

export interface TaskOptions {
  algorithms: string[];
  metrics: MetricOption[];
  default_metric: string;
}

export type ExperimentOptions = Record<Task, TaskOptions>;

export interface ExperimentCreate {
  dataset_id: string;
  task: Task;
  target_column: string;
  metric: string;
  algorithms: string[];
  random_seed: number;
  test_size: number;
}

export interface Experiment {
  experiment_id: string;
  dataset_id: string;
  task: Task;
  target_column: string;
  metric: string;
  algorithms: string[];
  random_seed: number;
  test_size: number;
  status: ExperimentStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
}

export interface ExperimentRun {
  run_id: string;
  algorithm: string;
  status: "SUCCEEDED" | "FAILED";
  hyperparameters: Record<string, unknown>;
  cv_score: number | null;
  cv_folds: number | null;
  metrics: Record<string, number | null>;
  duration_seconds: number;
  error_summary: string | null;
  rank: number | null;
}

export interface Leaderboard {
  experiment: Experiment;
  metric: string;
  higher_is_better: boolean;
  runs: ExperimentRun[];
  selected_run_id: string | null;
  model_id: string | null;
  selection_reason: {
    metric: string;
    direction: "higher_is_better" | "lower_is_better";
    evaluated_on: string;
    tie_breaker: string;
  } | null;
  split: { strategy: string; test_size: number; random_state: number; n_train: number; n_test: number } | null;
  library_versions: Record<string, string> | null;
}

export type ApprovalStatus = "PENDING" | "APPROVED" | "REVOKED";

export interface FeatureSpec {
  name: string;
  kind: "numeric" | "categorical";
  value_type: "number" | "string" | "boolean";
  categories: string[] | null;
}

export interface RegisteredModel {
  model_id: string;
  version: number;
  dataset_id: string;
  dataset_filename: string | null;
  experiment_id: string;
  run_id: string;
  task: Task;
  target_column: string;
  algorithm: string;
  metric: string;
  metrics: Record<string, number | null>;
  hyperparameters: Record<string, unknown>;
  feature_schema: FeatureSpec[];
  classes: (string | number | boolean)[] | null;
  library_versions: Record<string, string>;
  artifact_bytes: number;
  approval_status: ApprovalStatus;
  approved_at: string | null;
  created_at: string;
}

export type FeatureValue = string | number | boolean | null;

export interface PredictionResponse {
  model_id: string;
  model_version: number;
  predictions: (string | number | boolean | null)[];
  classes: (string | number | boolean)[] | null;
  probabilities: Record<string, number>[] | null;
  request_id: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface CurrentUser {
  user_id: string;
  username: string;
}

/** Where to send a file's bytes: this API (local mode) or a presigned storage URL (S3 mode). */
export interface UploadTarget {
  method: string;
  url: string; // a path on this API when requires_auth is true, otherwise absolute
  headers: Record<string, string>;
  expires_in_seconds: number | null;
  requires_auth: boolean; // send the bearer token only when true
}

export interface DatasetUpload extends Dataset {
  upload: UploadTarget;
}
