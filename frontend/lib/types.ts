export type DatasetStatus = "UPLOADED" | "READY" | "REJECTED";

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
