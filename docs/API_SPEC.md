# API Specification

> **Status:** **Proposed**, except `GET /health`, the dataset routes (§ 4.1) and the experiment routes (§ 4.2, § 4.3), which are implemented (M1, M2, M4). The error envelope in § 2 is implemented for all routes. The route table in § 3 comes from the owner's architecture brief; request/response field names, the error envelope and the "candidate additions" are design proposals to be finalised when the backend is scaffolded. Once the FastAPI app exists, its generated OpenAPI document becomes the source of truth and this file should link to it.

Related: [Architecture § 6.2](ARCHITECTURE.md#62-fastapi-backend) · [PRD](PRD.md) · [Security](SECURITY.md)

## 1. Conventions
- Base path: `/api/v1`. Breaking changes require a new version prefix (`/api/v2`).
- JSON request and response bodies (`Content-Type: application/json`), except the direct file upload target.
- Every response carries a request ID (header `X-Request-ID`, echoed in error bodies) for log correlation.
- Authentication: required on all routes except `GET /health`. Mechanism **TBD** ([SECURITY.md](SECURITY.md)).
- Ownership: a caller can only access resources they own; foreign resources return `404` (not `403`) to avoid confirming existence.
- Identifiers are opaque strings; clients must not parse them.

## 2. Error envelope (Proposed)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Target column 'price' is not in this dataset.",
    "details": [{ "field": "target_column", "issue": "not_found" }],
    "request_id": "req_..."
  }
}
```
Errors never include stack traces, storage keys, credentials or dataset values.

| HTTP | Meaning | Example `code` |
|---|---|---|
| 400 | Malformed request | `BAD_REQUEST` |
| 401 | Missing/invalid credentials | `UNAUTHENTICATED` |
| 404 | Not found or not owned | `NOT_FOUND` |
| 409 | State conflict (e.g. dataset not `READY`, model not approved) | `STATE_CONFLICT` |
| 413 | Payload or declared size too large | `PAYLOAD_TOO_LARGE` |
| 422 | Schema/validation failure | `VALIDATION_ERROR` |
| 429 | Rate limit exceeded | `RATE_LIMITED` |
| 500 | Unexpected server error (generic message) | `INTERNAL_ERROR` |

## 3. Routes (from the architecture brief)
| Method | Route | Purpose | PRD |
|---|---|---|---|
| `POST` | `/api/v1/datasets` | Upload a dataset as multipart form data. **Implemented** | FR-001, FR-002 |
| `GET` | `/api/v1/datasets/{dataset_id}` | Get dataset metadata and validation report. **Implemented** | FR-004 |
| `POST` | `/api/v1/datasets/{dataset_id}/validate` | Validate uploaded CSV. **Implemented** | FR-003 |
| `POST` | `/api/v1/experiments` | Create and queue an experiment. **Implemented** | FR-010–FR-013 |
| `GET` | `/api/v1/experiments/{experiment_id}` | Get status and configuration. **Implemented** | FR-014 |
| `GET` | `/api/v1/experiments/{experiment_id}/results` | Get model comparison results. **Implemented** | FR-030, FR-031 |
| `GET` | `/api/v1/models` | List registered models | FR-043 |
| `GET` | `/api/v1/models/{model_id}` | Get model metadata and metrics | FR-043 |
| `POST` | `/api/v1/models/{model_id}/predict` | Run inference using an approved model | FR-050–FR-053 |
| `GET` | `/health` | Liveness/health check. **Implemented**, returns `{"status": "ok"}` | FR-062 |

`GET /api/v1/experiments/options` is an addition to the brief that M4 implemented (§ 4.2).

### 3.1 Candidate additions (not in the brief — **Open**)
These are implied by PRD requirements but not yet agreed.

| Method | Route | Why |
|---|---|---|
| `GET` | `/api/v1/datasets` | Dataset list screen |
| `DELETE` | `/api/v1/datasets/{dataset_id}` | FR-006 retention/deletion |
| `GET` | `/api/v1/experiments` | Experiments list/dashboard |
| `POST` | `/api/v1/experiments/{experiment_id}/cancel` | FR-015 (if cancellation is in scope) |
| `POST` | `/api/v1/models/{model_id}/approve` | FR-042 (approval workflow) |

## 4. Payload sketches (Proposed — field names may change)

### 4.1 Dataset routes (**Implemented**, M2)
In local mode the file goes through the backend. A presigned direct-to-S3 upload (the original `PENDING_UPLOAD` flow) is deferred to the AWS milestone (M6).

**`POST /api/v1/datasets`** — `multipart/form-data` with one `file` field (`.csv` only).
- `201` with a dataset: `{ dataset_id, original_filename, size_bytes, status: "UPLOADED", created_at, validation: null }`. `created_at` is UTC. Storage keys are never returned.
- `413 PAYLOAD_TOO_LARGE` above `MAX_UPLOAD_BYTES` (default 10 MiB, **proposed**). A declared `Content-Length` far above the limit is refused up front; otherwise the cap is enforced while the file is written, and the partial file is deleted.
- `422 VALIDATION_ERROR` for a missing `file` field or a non-`.csv` name. The client filename is sanitised for display and never used as a storage path.

**`POST /api/v1/datasets/{dataset_id}/validate`** — runs the CSV through the engine and returns the report: `{ status: "READY" | "REJECTED", row_count, column_count, columns: [{ name, kind, missing_count, missing_percent, unique_count }], warnings: [{ code, severity, message, columns }], message }`.
- A rejected file is a normal `200` with `status: "REJECTED"` and a safe `message`; its stored file is removed.
- Repeating the call on an already-decided dataset returns the stored report.
- Checks: UTF-8 text, a readable header, no empty/duplicate/ambiguous headers, consistent field counts, row/column limits (`ValidationLimits` defaults, **proposed**).
- Warning codes: `tiny_dataset`, `constant_column`, `high_missing`, `identifier_like`, `high_cardinality`, `duplicate_rows`.

**`GET /api/v1/datasets/{dataset_id}`** — dataset metadata with `validation` set once the dataset has been validated (`null` while `UPLOADED`).

Dataset statuses: `UPLOADED` (stored, not validated), `READY`, `REJECTED`. Unknown or other owners' datasets return `404 NOT_FOUND`.

### 4.2 Experiment routes (**Implemented**, M4)
The API only queues work. A separate worker process trains the models (see [ARCHITECTURE § 6.6](ARCHITECTURE.md#66-job-orchestration)), so no request waits for training.

**`GET /api/v1/experiments/options`** returns, for `classification` and `regression`, the allowlisted `algorithms`, the `metrics` (`name`, `higher_is_better`) and the `default_metric`. Clients use it instead of hard-coding the allowlist. Declared before `/{experiment_id}` so `options` is not read as an ID.

**`POST /api/v1/experiments`** with a JSON body:
```json
{
  "dataset_id": "ds_...",
  "task": "classification",
  "target_column": "label",
  "metric": "f1",
  "algorithms": ["logistic_regression", "random_forest"],
  "random_seed": 42,
  "test_size": 0.2
}
```
- `metric` is optional (default `f1` for classification, `rmse` for regression). `random_seed` defaults to 42 and `test_size` to 0.2 (allowed 0.05 to 0.5). Duplicate algorithms are collapsed in order.
- Returns `202` with the experiment, `status: "QUEUED"`.
- `404` for an unknown or foreign dataset; `409 STATE_CONFLICT` unless the dataset is `READY`.
- `422 VALIDATION_ERROR` with `details` naming the field: the target is not in the dataset, has missing values, has fewer than two distinct values, or is not numeric for regression; the metric does not fit the task; an algorithm is not on the allowlist. Checks that need the data itself (for example a class with a single row) happen in the worker, which fails the experiment with a safe message.
- Optional `Idempotency-Key` header (up to 128 characters): repeating a request with the same key and owner returns the first experiment instead of creating another. The body of a repeated request is not compared. The browser sends this header, so the CORS configuration allows it.

**`GET /api/v1/experiments/{id}`** returns the experiment: configuration, `status`, `created_at`, `started_at`, `finished_at` (UTC) and `error_summary` (safe text). Statuses: `CREATED` (reserved), `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`. There is no cancel route and no `CANCELLED` status yet.

### 4.3 Results (**Implemented**, M4)
**`GET /api/v1/experiments/{id}/results`** returns `409 STATE_CONFLICT` until the experiment is `SUCCEEDED` or `FAILED`, then:
- `runs`: ranked runs best first, then successful but unranked runs, then failed runs. Each run has `algorithm`, `status`, `rank`, `metrics` (all metrics for the task; a metric that could not be computed is `null`), `cv_score` (cross-validated primary metric on training data, `null` when nothing was tuned), `cv_folds`, `hyperparameters` (tuned values), `duration_seconds` and `error_summary` (generic text for failed runs).
- `metric`, `higher_is_better`, `selected_run_id`, and `selection_reason`: `{ metric, direction, evaluated_on: "held_out_test_set", tie_breaker: "algorithm_name" }`. Both are `null` when no run could be ranked.
- `split` (strategy, test size, seed, train and test row counts) and `library_versions`.
- Ranking uses the held-out test score of the chosen metric, in the metric's direction; ties are broken by algorithm name.

### 4.4 `POST /api/v1/models/{model_id}/predict`
Request: `{ "instances": [ { "<feature>": <value>, ... } ] }`
Response: `{ "model_id": "...", "model_version": "...", "predictions": [...], "request_id": "..." }`
Rules: model must be approved (`409` otherwise); fields validated against the model schema; unknown fields rejected by default; batch size and body size limited (values **TBD**).

## 5. Pagination, filtering, versioning
List endpoints (once defined) use cursor or `limit`/`offset` pagination with a documented maximum page size — style **TBD**. Models are versioned independently of the API version.

## 6. Rate limiting
Required before the prediction endpoint is publicly exposed; limits **TBD**. Responses use `429` with `Retry-After`.

## 7. Open questions
Auth scheme for the API; list/delete/cancel/approve endpoints (§ 3.1); pagination style; whether predictions accept CSV in addition to JSON.
