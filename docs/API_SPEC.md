# API Specification

> **Status:** **Proposed.** No endpoint exists yet. The route table in § 3 comes from the owner's architecture brief; request/response field names, the error envelope and the "candidate additions" are design proposals to be finalised when the backend is scaffolded. Once the FastAPI app exists, its generated OpenAPI document becomes the source of truth and this file should link to it.

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
| `POST` | `/api/v1/datasets` | Register a dataset upload | FR-001, FR-002 |
| `GET` | `/api/v1/datasets/{dataset_id}` | Get dataset metadata | FR-004 |
| `POST` | `/api/v1/datasets/{dataset_id}/validate` | Validate uploaded CSV | FR-003 |
| `POST` | `/api/v1/experiments` | Create and queue an experiment | FR-010–FR-012 |
| `GET` | `/api/v1/experiments/{experiment_id}` | Get status and configuration | FR-014 |
| `GET` | `/api/v1/experiments/{experiment_id}/results` | Get model comparison results | FR-030, FR-031 |
| `GET` | `/api/v1/models` | List registered models | FR-043 |
| `GET` | `/api/v1/models/{model_id}` | Get model metadata and metrics | FR-043 |
| `POST` | `/api/v1/models/{model_id}/predict` | Run inference using an approved model | FR-050–FR-053 |
| `GET` | `/health` | Liveness/health check | FR-062 |

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

### 4.1 `POST /api/v1/datasets`
Request: `{ "filename": "housing.csv", "size_bytes": 1048576 }`
Response `201`: `{ "dataset_id": "...", "status": "PENDING_UPLOAD", "upload": { "method": "PUT", "url": "<short-lived>", "expires_in_seconds": 300 } }`
Rejects: unsupported extension, declared size above the limit, quota exceeded.

### 4.2 `POST /api/v1/experiments`
```json
{
  "dataset_id": "...",
  "task": "classification",
  "target_column": "churned",
  "metric": "f1",
  "algorithms": ["logistic_regression", "random_forest"],
  "random_seed": 42,
  "split": { "strategy": "stratified_random", "test_size": 0.2 }
}
```
Response `202` with `status: "QUEUED"`. Algorithm identifiers are an **allowlisted enum**; unknown values return `422`.

### 4.3 `GET /api/v1/experiments/{id}/results`
Returns the ranked runs with all metrics, durations, per-run status, the selected run, and a machine-readable `selection_reason` (metric, direction, tie-breakers applied).

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
