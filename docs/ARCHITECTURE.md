# System Architecture

> **Status of this document:** apart from the M1 scaffold, the repository contains no application code. Everything below is the **target architecture (Proposed)** taken from the owner's architecture brief. The *Current state* section is the only part that describes what exists today.

Legend: **Implemented** = verified in code/config · **Proposed** = planned design · **Assumption** · **Open question**. See [docs/README.md](README.md).

Related: [PRD](PRD.md) · [API spec](API_SPEC.md) · [Database schema](DATABASE_SCHEMA.md) · [Security](SECURITY.md) · [Deployment and cost](DEPLOYMENT.md) · [Testing](TESTING_STRATEGY.md) · [Roadmap](ROADMAP.md) · [ADRs](ADR/)

## 1. Current state

| Area | State |
|---|---|
| Frontend | **Implemented (M1, M2):** Next.js App Router shell with a backend health indicator, `/datasets/new` (upload) and `/datasets/[id]` (validation report), `/experiments/new` (configuration form), `/experiments/[id]` (status polling and leaderboard), `/models` and `/models/[id]` (approval, revocation and a prediction form generated from the model's feature schema), `/login`, a sign-in gate around every other page, a header with the signed-in user, confirmation dialogs for approve, revoke and delete, design tokens in `globals.css` (`frontend/`) |
| Backend | **Implemented (M1):** FastAPI app, `GET /health`, request-ID middleware, CORS, settings, SQLite engine/session factory (`backend/app/`). **M2 adds:** dataset upload/validate/read routes under `/api/v1/datasets`, the API error envelope, a body-size middleware, a `StorageAdapter` protocol with a local-disk implementation (under `ARTIFACT_DIR`), the `datasets` table, and an `get_owner_id` dependency that returns a placeholder owner until M7. **M4 adds:** experiment routes (`/api/v1/experiments`: options, create, read, results), the `experiments` and `experiment_runs` tables and idempotent submission. **M5 adds:** model routes (list, read, approve, predict), the `models` table, and checksum-verified artifact loading with a small in-process cache of loaded pipelines. **M7 adds:** sign-in (`/api/v1/auth/login`, `/me`) with scrypt-hashed local accounts and JWT bearer tokens, one router-level authentication dependency in front of every other route, `DELETE` for datasets with cascade, `revoke` for models, per-user and per-address rate limits, security headers, an audit table, an operator CLI (`python -m app.cli`), and a background reaper that fails stale `RUNNING` experiments. **M9 adds:** Google sign-in through Supabase (`/api/v1/auth/google`), local subject/email mapping and a rolling daily experiment limit.**
| ML engine | **Implemented (M3):** `backend/automl/` provides dataset and target validation, a `ColumnTransformer` preprocessor, stratified/random splits, the algorithm allowlist with train-only grid search, held-out evaluation, and metric-aware ranking. It is not yet wired to the API or worker. `registry.py` is still a stub (M5) |
| Worker | **Implemented (M4):** `python -m worker.main` is a separate process. It polls the database, atomically claims `QUEUED` experiments one at a time, runs the engine, records each run and the outcome, saves the winning pipeline as a versioned `joblib` artifact with a `metadata.json` before marking the experiment `SUCCEEDED`, and fails `RUNNING` jobs that exceed `JOB_TIMEOUT_SECONDS`. Any failure is recorded on the experiment and the loop continues. It imports no web-framework code (tested) |
| Infrastructure | `infrastructure/terraform/` exists and is empty |
| CI | **Implemented (M1):** `.github/workflows/ci.yml` runs backend lint/format/type/test and frontend lint/type/build |
| Local run | `docker-compose.yml` defined; not yet run |
| Cloud mode | **Implemented (M6), never run against real AWS:** `STORAGE_MODE=s3`, `JOB_MODE=sqs`, presigned direct uploads, the SQS worker loop, and Terraform for the bucket, queues and IAM policies (`infrastructure/terraform/`). Tested with `moto` and, in a real browser, against a local `moto` server |

Engine functions (all in `backend/automl/`):

| Module | Public functions |
|---|---|
| `validation.py` | `read_csv_bytes`, `validate_headers`, `validate_dataframe`, `validate_target`, `ValidationLimits`, `DataValidationError` |
| `preprocessing.py` | `split_column_types`, `build_preprocessor` (unfitted; fitted inside the training pipeline) |
| `splits.py` | `separate_target`, `split_data` returning a `DataSplit` that records strategy, test size and seed |
| `trainer.py` | `ESTIMATORS` allowlist, `available_algorithms`, `train_model` returning a `TrainedModel` (pipeline, best parameters, CV score, feature names, library versions) |
| `evaluator.py` | `METRICS` with direction, `evaluate`, `rank_results`, `scoring_for` |
| `quality.py` | `summarize_schema`, `quality_warnings` |
| `registry.py` | `build_feature_schema`, `instances_to_frame` (strict prediction-input validation), `dumps_pipeline` / `loads_pipeline` (trusted bytes only), `sha256_hex`, `build_metadata` |

The winning fitted pipeline is saved at training time ([ADR 0003](ADR/0003-save-winning-model-at-training-time.md)). It is fitted on the training split only, so it is exactly the model the leaderboard measured.

Everything else in this document is the target design.

## 2. System context and boundaries (Proposed)

AutoML Lab lets a signed-in user upload a tabular CSV, choose a target column and ML task, run a reproducible training pipeline over an allowlisted set of scikit-learn estimators, compare results on a leaderboard, register the winning model as an immutable version, and request predictions through a versioned API.

**In scope for the first release:** small-to-medium tabular **classification and regression**; CSV only; CPU only.

**Out of scope:** distributed or GPU training, deep learning, user-supplied code execution, automatic public deployment of every model, support for formats other than CSV, guaranteed zero-cost AWS hosting.

External actors and systems:

| Actor / system | Interaction |
|---|---|
| User (browser) | Uses the Next.js UI; never holds AWS credentials |
| API client | Calls the prediction API with a bearer credential (mechanism TBD, see [SECURITY.md](SECURITY.md)) |
| Amazon S3 (cloud mode) | Private storage for datasets, artifacts, reports |
| Amazon EventBridge (optional) | Scheduled or event-driven automation such as cleanup |
| AWS Lambda (optional) | Short orchestration, validation, event handling only |
| Amazon CloudWatch (cloud mode) | Logs and metrics |

## 3. Architecture diagram (Proposed)

```mermaid
flowchart TD
    U[User / Browser] --> FE[Next.js Frontend]
    FE --> API[FastAPI Backend]
    API --> AUTH[Authentication and Authorization]
    API --> META[(Metadata Store)]
    API --> STORE[(Storage Adapter: local disk or S3)]
    API --> JOB[Job Orchestrator Adapter]
    JOB --> WORKER[Python Training Worker]
    JOB -.optional.-> EVT[Amazon EventBridge]
    WORKER --> ENGINE[automl engine package]
    WORKER --> STORE
    WORKER --> META
    API --> PRED[Prediction Service]
    PRED --> STORE
    API --> LOG[Structured Logs: stdout / CloudWatch]
    WORKER --> LOG
```

The diagram shows logical components. In AWS (M8) the API runs on Lambda behind a Function URL and the worker on ECS Fargate, both from one Docker image, with RDS PostgreSQL for metadata and the frontend on Amplify Hosting or Vercel ([ADR 0006](ADR/0006-aws-deployment.md), [ADR 0007](ADR/0007-lambda-api-and-amplify-frontend.md), [DEPLOYMENT.md](DEPLOYMENT.md)). The memory, duration and cost figures behind that choice have not been measured on real AWS.

## 4. Core architectural principle

**The ML engine is independent of AWS.** The `automl` package contains validation, preprocessing, splitting, training, evaluation and registry logic and imports no AWS SDK. Storage, job orchestration, and monitoring are reached through adapters: *local adapters* for development, *cloud adapters* for S3, queueing/orchestration and CloudWatch. This keeps the core testable, portable and cheap. See [ADR 0001](ADR/0001-local-first-adapter-architecture.md).

## 5. Repository and module map (Proposed target layout)

```text
automl-lab/
├── frontend/                 Next.js app: dashboard, datasets, experiments, models
│   ├── app/  components/  lib/
├── backend/
│   ├── app/                  FastAPI service
│   │   ├── api/              route handlers (versioned: /api/v1)
│   │   ├── core/             config, security, logging, request IDs
│   │   ├── db/               metadata persistence
│   │   ├── schemas/          request/response models
│   │   └── services/         dataset, experiment, model, prediction services
│   ├── automl/               AWS-independent ML engine
│   │   ├── validation.py  preprocessing.py  splits.py
│   │   └── trainer.py  evaluator.py  registry.py
│   ├── worker/main.py        job runner entry point
│   ├── tests/
│   └── pyproject.toml
├── infrastructure/terraform/ AWS resources (cloud mode only)
├── .github/workflows/        CI
├── docs/                     this documentation suite
├── docker-compose.yml        local run (Proposed)
└── .env.example              variable names only, no values
```

| Module | Owns | Must not |
|---|---|---|
| `frontend/` | UI, client state, calls to the API | Hold AWS credentials; read private S3 objects with permanent credentials |
| `backend/app/` | AuthN/Z, validation, metadata, presigned URLs, job creation, prediction serving | Leak stack traces, S3 keys or dataset contents in errors |
| `backend/automl/` | Pure ML pipeline logic | Import `boto3`, FastAPI, or any web/cloud SDK |
| `backend/worker/` | Claim a job, run the engine, persist results | Depend on an open HTTP request; execute user-supplied code |
| `infrastructure/` | IaC | Contain secrets or committed state files |

## 6. Components and responsibilities (Proposed)

### 6.1 Next.js frontend
Dataset upload with progress; dataset preview, schema and data-quality summary; task, target and metric selection; experiment configuration; job status and error display; leaderboard and metric visualisations; model registry and prediction testing. Direct-to-S3 uploads are allowed only through a short-lived presigned URL issued by the backend after authorisation and validation. Visual rules: [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

### 6.2 FastAPI backend
Authentication and authorisation; request validation and API versioning; dataset/experiment/model metadata; upload-limit enforcement; presigned URLs; job creation and tracking; experiment results; prediction serving for approved models; audit events and structured logs. Routes: [API_SPEC.md](API_SPEC.md).

### 6.3 Metadata store
Metadata is kept separate from dataset and model files. Local: **SQLite**. Cloud and any `ENVIRONMENT` other than `local`: **PostgreSQL** (RDS), with Alembic migrations; SQLite is refused there ([ADR 0006](ADR/0006-aws-deployment.md)). Entities and relationships: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md).

### 6.4 Object storage
**Implemented (M6).** `STORAGE_MODE=local` (default) uses a local artifact directory; `STORAGE_MODE=s3` uses one private S3 bucket. Both implement `StorageAdapter` (save, read, size, delete, delete a folder, create an upload target). The S3 bucket has Block Public Access, owner-enforced ownership, SSE-S3 encryption, a TLS-only policy, CORS for the configured origin and cleanup of incomplete multipart uploads; permissions are scoped to the `datasets/` and `models/` prefixes ([ADR 0005](ADR/0005-s3-storage-and-sqs-job-queue.md), `infrastructure/terraform/`). Provider error text never reaches callers.

```text
datasets/{owner_id}/{dataset_id}/source.csv
experiments/{experiment_id}/reports/summary.json
models/{model_id}/{version}/model.joblib
models/{model_id}/{version}/metadata.json
```

Object names must not contain secrets or sensitive user data. Uploaded files are untrusted input.

### 6.5 Training worker
A separate Python process that does not depend on an open web request. Pipeline stages:

1. Load the approved dataset object.
2. Validate format, size, row/column counts and target selection.
3. Inspect schema; summarise missing values and categorical/numeric columns.
4. Split into train and test sets (stratified for suitable classification tasks; time-aware split offered for time-dependent data).
5. Fit preprocessing **only on training data**, inside a scikit-learn `Pipeline`/`ColumnTransformer`.
6. Train the allowlisted candidate estimators.
7. Evaluate on held-out data, or cross-validate within the training set for tuning.
8. Rank by the selected metric with configured tie-breakers.
9. Save the chosen fitted pipeline plus metrics and report.
10. Update experiment status and emit structured logs.

Algorithm allowlist (Proposed): classification — Logistic Regression, Decision Tree, Random Forest; regression — Linear Regression, Decision Tree Regressor, Random Forest Regressor. Code or class names are never imported from dataset content or user-provided configuration.

### 6.6 Job orchestration
| Mode | Mechanism | State |
|---|---|---|
| Local | The API writes a `QUEUED` experiment to the database; a separate worker process polls the table and claims jobs with a conditional update, so several workers cannot take the same job | **Implemented (M4)** |
| Cloud queue | `JOB_MODE=sqs`: the API also sends the experiment ID to a standard SQS queue (dead-letter queue after 3 deliveries); the worker long-polls it, claims the experiment with the same conditional update, and deletes the message once it is dealt with. The message is only a hint, so duplicates and redeliveries are harmless | **Implemented (M6)** |
| Cloud worker runtime | The API on Lambda (Function URL) and the worker on ECS Fargate | **Decided** in M8 ([ADR 0006](ADR/0006-aws-deployment.md); API changed by [ADR 0007](ADR/0007-lambda-api-and-amplify-frontend.md)); API live on Lambda, worker training not yet verified on AWS |
| EventBridge | Optional: scheduled experiments, periodic cleanup, supported event routing. Not a job queue or training runtime | Proposed, optional |
| Lambda | Short orchestration, validation or event handling within its limits. Training does not default to Lambda | Proposed, optional |

### 6.7 Prediction service
Loads only registered, approved model artifacts produced by trusted pipeline code. An artifact contains the fitted preprocessing + estimator pipeline, feature names/schema, model version, training configuration and evaluation metrics. Safeguards: validate JSON against the model schema; documented policy for missing/extra/invalid fields; request-size and batch-size limits; model versions immutable; record which version served each prediction; authentication and rate limiting before any public exposure. `joblib`/pickle can execute code on load, so the system must never deserialise untrusted artifacts ([ADR 0002](ADR/0002-trusted-joblib-artifacts.md)).

## 7. End-to-end data flows

### 7.1 Dataset upload (Implemented, M2 and M6)
```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant ST as Storage
    participant V as Validation
    U->>FE: Choose CSV
    FE->>API: POST /api/v1/datasets (filename, declared size)
    API->>API: Authenticate, check name and size against the limit
    API->>ST: Create record, ask for an upload target
    API-->>FE: dataset_id + target (presigned S3 URL, or this API in local mode)
    FE->>ST: PUT the file (no bearer token for a presigned URL)
    FE->>API: POST /datasets/{id}/validate
    API->>ST: Check the stored size equals the declared size
    API->>V: Check CSV structure, schema, limits
    V-->>API: READY or REJECTED
    API-->>FE: Status + data-quality report
```

### 7.2 Experiment execution
```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> QUEUED
    CREATED --> CANCELLED
    QUEUED --> RUNNING
    QUEUED --> CANCELLED
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

1. User picks task, target, primary metric and allowed algorithms.
2. Backend validates the configuration and creates the experiment (`QUEUED`).
3. A worker claims the job (`RUNNING`).
4. The worker runs validation, preprocessing, training and evaluation; each run's status, metrics and duration are recorded.
5. The best eligible model is selected by the declared metric and policy.
6. Artifact and report are saved; model metadata is registered.
7. Status becomes `SUCCEEDED` or `FAILED`.

Cancellation is implemented only if the worker can stop safely and keep metadata consistent (**Open**).

### 7.3 Prediction
Client calls the model-specific route → authenticate and authorise → validate request schema → load or reuse the approved pipeline → transform and predict → return predictions, model version and request ID. Logs record timing and outcome, never raw input values.

## 8. Machine-learning design

| Concern | Rule |
|---|---|
| Classification metrics | F1, precision, recall, ROC-AUC (only when the class structure/probabilities allow it), accuracy. Prefer a metric aligned with the objective over accuracy alone for imbalanced classes |
| Regression metrics | MAE, RMSE (lower is better), R² (higher is better); direction is explicit in metadata |
| Leakage | Target never used as a feature; imputers, encoders, scalers and feature selection fitted on training data only; test set never used for hyper-parameter selection |
| Reproducibility | Record split strategy, random seed, metric definition and library versions per experiment |
| Warnings | Identifier-like columns, high-cardinality columns, suspected target leakage, tiny datasets |
| Selection policy | Rank only runs that finished evaluation and pass minimum validity checks; store all metrics; state that the best candidate score is not a real-world performance guarantee |

## 9. Authentication and authorisation (Implemented, M9)
Cloud users sign in with Google through Supabase; the API maps the verified subject to a local user
and returns a signed application JWT. Local password accounts remain a development fallback
([ADR 0010](ADR/0010-google-sign-in-with-supabase.md)). Every `/api/v1` route except sign-in sits
behind one router-level dependency, and repositories filter by the caller's user ID, so a foreign
ID is a `404` identical to a missing one. Predictions are rate limited per user. The worker has no
user: it acts on rows that were already authorised when they were created.

```mermaid
sequenceDiagram
    actor U as Browser
    participant API as FastAPI
    participant DB as Metadata store
    U->>API: Google OAuth, then POST /auth/google
    API->>API: verify Supabase signature, issuer, audience
    API->>DB: load or create subject/email
    API-->>U: access_token (60 min)
    U->>API: GET /models/{id} with Bearer token
    API->>API: verify signature, exp, algorithm
    API->>DB: load user (must exist and be active)
    API->>DB: load model WHERE id AND owner = user
    API-->>U: 200, or 404 if not the owner's
```

Cloud identity uses Supabase Auth for Google sign-in; local password login remains a configurable
development fallback. Details: [ADR 0010](ADR/0010-google-sign-in-with-supabase.md) and
[SECURITY.md](SECURITY.md).

## 10. Configuration and secrets boundary
- Local development: environment variables loaded from an untracked `.env`; the repo carries only `.env.example` with variable **names**.
- AWS: IAM roles and temporary credentials; no access keys in code, frontend bundles or committed files.
- A managed secrets service is introduced only if required and budget-checked.
- Environment variable names are defined when the backend is scaffolded (**TBD**); none are claimed here.

## 11. Errors, retries and idempotency (Proposed)
- Bounded retries with back-off for transient storage/API errors.
- Deterministic validation failures are **not** retried; they surface as clear user-facing errors.
- Job submission is idempotent (a repeated submit does not create duplicate runs).
- A reaper marks abandoned `RUNNING` jobs as `FAILED` after a timeout (value **TBD**).
- API errors never expose stack traces, private keys, credentials or dataset content.

## 12. Observability (Proposed)
Structured logs with request IDs on stdout locally and in CloudWatch when deployed. Capture request latency and error rate, queue wait, training duration, failed-job counts, per-run metrics and configuration, worker exceptions and resource-limit failures, artifact transfer errors, model version and prediction latency. Review CloudWatch retention to control cost.

## 13. Test architecture
Unit, integration, ML, API, security, end-to-end and cost tests, with deterministic fixture datasets. See [TESTING_STRATEGY.md](TESTING_STRATEGY.md).

## 14. Deployment topology
| Option | Description | State |
|---|---|---|
| A — Local-first | Next.js, FastAPI, SQLite, local worker, local artifact directory, Docker Compose | Proposed, **recommended starting point** |
| B — Hybrid AWS | Frontend on Amplify Hosting or Vercel, API on Lambda, worker on ECS Fargate, RDS PostgreSQL, private S3, SQS; optional EventBridge and CloudWatch alarms are not built | Implemented in M8 and applied: API live on Lambda, frontend on Vercel; worker training and Amplify **not verified** |

Details and cost controls: [DEPLOYMENT.md](DEPLOYMENT.md).

## 15. Trade-offs and risks
| Risk / trade-off | Mitigation |
|---|---|
| AWS cost cannot be guaranteed at $0 | Local-first, strict limits, budgets/alerts (alerts are not a hard cap), teardown plan |
| Lambda limits vs training duration | Keep training in a separate worker runtime; Lambda only for short tasks |
| Pickle/joblib code execution on load | Trusted artifacts only, restricted write access, pinned dependencies |
| Malicious or malformed CSVs | Allowlisted type, real-size limits, safe parsing, timeouts, row/column caps |
| Overfitting to the leaderboard | Held-out test set, clear caveat in the UI |
| Premature cloud lock-in | Adapter boundary around storage, jobs, monitoring |

## 16. Architecture decision records
- [ADR 0001 — Local-first, adapter-based architecture](ADR/0001-local-first-adapter-architecture.md)
- [ADR 0002 — Trusted joblib artifacts only](ADR/0002-trusted-joblib-artifacts.md)
- [ADR 0003 — Save the winning model at training time](ADR/0003-save-winning-model-at-training-time.md)
- [ADR 0004 — Local accounts with bearer tokens](ADR/0004-local-accounts-and-bearer-tokens.md)
- [ADR 0005 — S3 storage, presigned uploads and an SQS job queue](ADR/0005-s3-storage-and-sqs-job-queue.md)

## 17. Open questions
1. Authentication provider and API-credential model for the prediction endpoint.
2. Cloud metadata store (e.g. DynamoDB) and cloud worker runtime.
3. Concrete limits: maximum file size, rows, columns, training time, batch size.
4. Whether experiment cancellation is in the first release.
5. Whether time-aware splits are in the first release.
