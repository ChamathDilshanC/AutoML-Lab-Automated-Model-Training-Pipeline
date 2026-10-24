# API Specification

> **Status:** **Proposed**, except `GET /health`, the auth routes (§ 4.0), the dataset routes (§ 4.1), the experiment routes (§ 4.2, § 4.3) and the model routes (§ 4.4), which are implemented (M1, M2, M4, M5, M7). The error envelope in § 2 is implemented for all routes. The route table in § 3 comes from the owner's architecture brief; request/response field names, the error envelope and the "candidate additions" are design proposals to be finalised when the backend is scaffolded. Once the FastAPI app exists, its generated OpenAPI document becomes the source of truth and this file should link to it.

Related: [Architecture § 6.2](ARCHITECTURE.md#62-fastapi-backend) · [PRD](PRD.md) · [Security](SECURITY.md)

## 1. Conventions
- Base path: `/api/v1`. Breaking changes require a new version prefix (`/api/v2`).
- JSON request and response bodies (`Content-Type: application/json`), except the direct file upload target.
- Every response carries a request ID (header `X-Request-ID`, echoed in error bodies) for log correlation.
- Authentication: a bearer token (`Authorization: Bearer <token>`) is required on every route except `GET /health` and `POST /api/v1/auth/login` (§ 4.0). A missing, malformed, expired, forged or no-longer-valid token returns `401 UNAUTHENTICATED` with `WWW-Authenticate: Bearer`, before the request body is looked at.
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
| `GET` | `/api/v1/models` | List registered models. **Implemented** | FR-043 |
| `GET` | `/api/v1/models/{model_id}` | Get model metadata and metrics. **Implemented** | FR-043 |
| `POST` | `/api/v1/models/{model_id}/predict` | Run inference using an approved model. **Implemented** | FR-050–FR-053 |
| `GET` | `/health` | Liveness/health check. **Implemented**, returns `{"status": "ok"}` | FR-062 |

`GET /api/v1/experiments/options` (§ 4.2), `POST /api/v1/models/{model_id}/approve` and `/revoke` (§ 4.4), `DELETE /api/v1/datasets/{dataset_id}` (§ 4.1) and the auth routes (§ 4.0) are additions to the brief that were implemented in M4, M5 and M7.

### 3.1 Candidate additions (not in the brief — **Open**)
These are implied by PRD requirements but not yet agreed.

| Method | Route | Why |
|---|---|---|
| `GET` | `/api/v1/datasets` | Dataset list screen |
| `GET` | `/api/v1/experiments` | Experiments list/dashboard |
| `POST` | `/api/v1/experiments/{experiment_id}/cancel` | FR-015 (if cancellation is in scope) |

## 4. Payload sketches (Proposed — field names may change)

### 4.0 Auth routes (**Implemented**, M7)
There is no public sign-up; accounts are created with `python -m app.cli create-user` ([ADR 0004](ADR/0004-local-accounts-and-bearer-tokens.md)).

**`POST /api/v1/auth/login`** takes `application/x-www-form-urlencoded` `username` and `password` (the OAuth2 password form) and returns `{ "access_token": "...", "token_type": "bearer", "expires_in": 3600 }`. Usernames are case-insensitive. A wrong password, an unknown user and a disabled user all return the same `401` message, "Incorrect username or password.". Attempts are limited per client address (default 10 per minute, **proposed**); beyond that the answer is `429 RATE_LIMITED` with `Retry-After`, even for a correct password.

**`GET /api/v1/auth/me`** returns `{ user_id, username }` for the token's user.

Tokens are signed JWTs (HS256), valid for 60 minutes by default. The user is looked up on every request, so disabling or deleting an account ends its tokens immediately. There are no refresh tokens and no server-side logout.

### 4.1 Dataset routes (**Implemented**, M2, reworked in M6)
Uploading is three calls: register, send the bytes, validate. The same sequence is used with local storage and with S3 ([ADR 0005](ADR/0005-s3-storage-and-sqs-job-queue.md)).

**`POST /api/v1/datasets`** with JSON `{ "filename": "housing.csv", "size_bytes": 1048576 }` registers a dataset and returns `201`:
```json
{
  "dataset_id": "ds_...", "original_filename": "housing.csv", "size_bytes": 1048576,
  "status": "PENDING_UPLOAD", "created_at": "...Z", "validation": null,
  "upload": {
    "method": "PUT",
    "url": "https://<bucket>.s3.<region>.amazonaws.com/datasets/...?X-Amz-...",
    "headers": { "Content-Type": "text/csv" },
    "expires_in_seconds": 300,
    "requires_auth": false
  }
}
```
- `STORAGE_MODE=s3`: `url` is a presigned S3 URL for that one key, valid for 300 seconds (`S3_PRESIGN_EXPIRES_SECONDS`). `Content-Type` and the exact `Content-Length` are signed, so S3 refuses any other size or type. `requires_auth` is `false`: send **no** `Authorization` header to it.
- `STORAGE_MODE=local`: `url` is `/api/v1/datasets/{id}/content` on this API and `requires_auth` is `true`.
- `413 PAYLOAD_TOO_LARGE` if `size_bytes` exceeds `MAX_UPLOAD_BYTES` (default 10 MiB, **proposed**); no URL is issued. `422 VALIDATION_ERROR` for a non-`.csv` name or a size below 1. The client filename is sanitised for display and never used as a storage path.

**`PUT /api/v1/datasets/{dataset_id}/content`** (local mode only) takes the raw bytes. `204` on success. `413` if the body is larger than the declared size, `422` if it is smaller (nothing is kept either way), `409 STATE_CONFLICT` unless the dataset is `PENDING_UPLOAD`, or in S3 mode. The body-limit middleware also refuses, up front, a declared `Content-Length` far above the limit.

**`POST /api/v1/datasets/{dataset_id}/validate`** — runs the CSV through the engine and returns the report: `{ status: "READY" | "REJECTED", row_count, column_count, columns: [{ name, kind, missing_count, missing_percent, unique_count }], warnings: [{ code, severity, message, columns }], message }`.
- `409 STATE_CONFLICT` if no file has been uploaded yet (this is not a rejection: upload and call again).
- The stored object's size must equal the declared size, whatever mechanism uploaded it; otherwise the dataset is `REJECTED` and the object is deleted.
- A rejected file is a normal `200` with `status: "REJECTED"` and a safe `message`; its stored file is removed.
- Repeating the call on an already-decided dataset returns the stored report.
- Checks: UTF-8 text, a readable header, no empty/duplicate/ambiguous headers, consistent field counts, row/column limits (`ValidationLimits` defaults, **proposed**).
- Warning codes: `tiny_dataset`, `constant_column`, `high_missing`, `identifier_like`, `high_cardinality`, `duplicate_rows`.

**`GET /api/v1/datasets/{dataset_id}`** — dataset metadata with `validation` set once the dataset has been validated (`null` while `PENDING_UPLOAD`).

**`DELETE /api/v1/datasets/{dataset_id}`** (M7) returns `204` after deleting the dataset and everything derived from it: its experiments, runs and models, and the stored files (source CSV and model artifacts). Database rows are removed first in one transaction; file removal follows, and a failure there is logged but does not fail the request (the files are then unreachable, not referenced). `409 STATE_CONFLICT` while one of its experiments is `RUNNING`. Deleting twice gives `404`.

Dataset statuses: `PENDING_UPLOAD` (registered, not validated), `READY`, `REJECTED`. `UPLOADED` is a legacy value on rows created before M6 and is treated like `PENDING_UPLOAD`. Unknown or other owners' datasets return `404 NOT_FOUND`.

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
- Returns `202` with the experiment, `status: "QUEUED"`. With `JOB_MODE=sqs` the API also sends `{"experiment_id": "...", "version": 1}` to the queue; the message carries only the ID, and the configuration always comes from the database. If the queue cannot be reached the experiment is removed again and the answer is `503 SERVICE_UNAVAILABLE` with `Retry-After: 5`, so retrying (also with the same `Idempotency-Key`) is safe.
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

### 4.4 Model routes (**Implemented**, M5)
A model is registered automatically when an experiment succeeds ([ADR 0003](ADR/0003-save-winning-model-at-training-time.md)). `model_id` identifies one immutable artifact; `version` counts the artifacts registered for the same owner, dataset, target column and task (a re-run gives version 2). Storage keys and checksums are never returned.

**`GET /api/v1/models`** lists the caller's models, newest first (not paginated yet). **`GET /api/v1/models/{model_id}`** returns one:
`{ model_id, version, dataset_id, dataset_filename, experiment_id, run_id, task, target_column, algorithm, metric, metrics, hyperparameters, feature_schema, classes, library_versions, artifact_bytes, approval_status, approved_at, created_at }`.
`feature_schema` is a list of `{ name, kind, value_type, categories }` where `value_type` is `number`, `string` or `boolean` and `categories` lists the values seen in training for string columns with at most 50 distinct values (otherwise `null`). `metrics` are the winner's held-out test scores.

**`POST /api/v1/models/{model_id}/approve`** with body `{ "confirm": true }` sets `approval_status` to `APPROVED` (it starts as `PENDING`). Any other body is `422`. Approving an approved model changes nothing. Approving a `REVOKED` model is `409`.

**`POST /api/v1/models/{model_id}/revoke`** (M7) with body `{ "confirm": true }` sets `REVOKED`. The model stops answering predictions at once (the approval is checked in the database on every request, so a cached pipeline does not matter). `REVOKED` is terminal: it cannot be approved again, and a new experiment gives a new version. Revoking a `PENDING` model is `409`; revoking a revoked one is a no-op.

**`POST /api/v1/models/{model_id}/predict`** with body `{ "instances": [ { "<feature>": <value>, ... } ] }`:
- `409 STATE_CONFLICT` if the model is not `APPROVED`, or if it was trained with a different scikit-learn version than the one installed.
- `422 VALIDATION_ERROR` with `details` like `{ "field": "instances[1].x2", "issue": "required field is missing" }`. Each instance must contain exactly the schema's fields: unknown and missing fields are rejected; a number must be a finite JSON number (not a string or boolean); a string field must be a string of at most 200 characters; a boolean field must be `true` or `false`. `null` is accepted for any field and is imputed from training statistics. A category not seen in training is accepted (the encoder ignores it). At most `MAX_PREDICTION_BATCH` instances (default 100, **proposed**). Details never contain submitted values.
- `200` with `{ model_id, model_version, predictions, classes, probabilities, request_id }`. `probabilities` (one object per instance, keyed by class label) and `classes` are only present for classification.
- `429 RATE_LIMITED` with `Retry-After` after too many requests: a token bucket of `PREDICT_RATE_LIMIT_PER_MINUTE` (default 60, **proposed**) per signed-in user, shared by all models. It is checked before the body is read and counts malformed, unknown-model and unapproved requests too; unauthenticated requests are refused with `401` first and do not use it.
- `500 INTERNAL_ERROR` if the artifact is missing or fails its checksum; the message is generic.
- Input is plain JSON validated field by field. It is never passed to joblib or pickle; only the stored artifact is deserialised, after its SHA-256 matches.

## 5. Pagination, filtering, versioning
List endpoints (once defined) use cursor or `limit`/`offset` pagination with a documented maximum page size — style **TBD**. Models are versioned independently of the API version.

## 6. Rate limiting
**Implemented (M7)** for `POST /auth/login` (per client address, `LOGIN_RATE_LIMIT_PER_MINUTE`, default 10) and `POST /models/{id}/predict` (per user, `PREDICT_RATE_LIMIT_PER_MINUTE`, default 60). Over the limit the answer is `429 RATE_LIMITED` with `Retry-After`. The limiter is in memory, so each API process keeps its own counts; a shared store or a gateway limit is needed once there is more than one process.

## 7. Open questions
Auth scheme for the API; list/delete/cancel/approve endpoints (§ 3.1); pagination style; whether predictions accept CSV in addition to JSON.
