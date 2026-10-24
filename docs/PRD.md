# Product Requirements Document

> **Status:** early build. See the feature status table in section 5; every requirement not listed there is **Proposed**. Numeric limits are **proposed starting points** pending measurement.

Related: [Architecture](ARCHITECTURE.md) · [API spec](API_SPEC.md) · [Design system](DESIGN_SYSTEM.md) · [Security](SECURITY.md) · [Roadmap](ROADMAP.md)

## 1. Executive summary and problem statement

Running even a basic machine-learning workflow requires stitching together data validation, preprocessing, model training, evaluation and packaging, and it is easy to get wrong (test-set leakage, the wrong metric, irreproducible results). **AutoML Lab** is a web application where a user uploads a tabular CSV, chooses a target column and task, and receives a validated, reproducible comparison of several candidate models, plus a versioned model that can be queried over an API.

## 2. Product vision
A simple, trustworthy place to go from a CSV to an honestly evaluated model, with every step reproducible and explained, built to run cheaply (local-first) and be portable to AWS.

## 3. Target users and roles
| Role | Description | State |
|---|---|---|
| Data practitioner / student | Uploads datasets, runs experiments, reads leaderboards, tests predictions | Assumption (primary user, unconfirmed) |
| API consumer | Calls the prediction API for an approved model | Assumption |
| Maintainer / owner | Operates the deployment, reviews cost and security | ChamathDilshanC |

Role model beyond "authenticated owner of their own resources" is **Open**.

## 4. Goals and non-goals
**Goals (from the architecture brief)**
- G1 Make a basic ML workflow accessible through a web UI.
- G2 Keep preprocessing, training, evaluation and inference reproducible.
- G3 Prevent test-set leakage and use task-appropriate metrics.
- G4 Track experiment status, configuration, metrics and model versions.
- G5 Expose a versioned prediction API.
- G6 Keep infrastructure simple and cost-aware.
- G7 Apply least-privilege access and safe dataset handling.

**Non-goals (first release)**
- Large-scale distributed or GPU training; deep learning.
- Arbitrary user-supplied Python code execution.
- Automatic public deployment of every model.
- Guaranteed zero-cost AWS hosting.
- File formats other than CSV.

## 5. Feature status
| Feature | Status |
|---|---|
| FR-062 `GET /health` | **Implemented (M1)** |
| FR-001, FR-002, FR-003 | **Implemented (M2, reworked in M6)**: register the file, send the bytes to a target (this API locally, or a short-lived presigned S3 URL), then validate to `READY`/`REJECTED`. The browser never holds storage credentials. The S3 path has not been run against real AWS |
| FR-004, FR-005 | **Partly implemented (M2)**: schema, missing values and data-quality warnings; no first-rows preview and no target-leakage warning yet (the target is chosen at experiment time) |
| FR-020, FR-021, FR-022, FR-024, FR-026, FR-027, FR-030 | **Implemented** in the ML engine (M3) and run by the worker since M4 |
| FR-023, FR-025 | **Implemented (M3, M4)**: per-run hyper-parameters, metrics, duration and status, plus split strategy, seed and library versions, are recorded |
| FR-010, FR-011, FR-012, FR-013, FR-014 | **Implemented (M4)**: experiment configuration and validation, queueing, idempotent submission, status and error display |
| FR-031, FR-032 | **Implemented (M4)**: leaderboard with all metrics and a selection explanation, and a real-world performance caveat |
| FR-015, FR-016, FR-033 | Not implemented (cancellation, time-aware split, metric charts) |
| FR-040, FR-041, FR-042, FR-043 | **Implemented (M5)**: the winning pipeline is saved as a versioned artifact with metadata; versions are immutable (no update path); models start `PENDING` and only `APPROVED` ones serve predictions; list and detail views |
| FR-050, FR-051, FR-052, FR-053, FR-054 | **Implemented (M5)**: strict schema validation, batch-size limit, predictions with model version and request ID, version logged per request, and a prediction form generated from the schema. FR-051's request-size limit is the general body limit, not a prediction-specific one |
| FR-006 | **Implemented (M7)**: deleting a dataset removes its source file, experiments, runs, models and artifacts. No retention window: deletion is immediate |
| FR-060, FR-061 | **Implemented (M7)** for local accounts: sign-in, a token on every route, ownership checks returning 404 for foreign IDs, and audit events for sign-in, account creation, approve, revoke and delete |
| FR-042 (revocation) | **Implemented (M7)**: `REVOKED` is terminal and stops predictions immediately |
| All other features in this PRD | Proposed |

## 6. MVP scope (Definition of Done for the first portfolio release)
A user can: upload a valid CSV and receive a clear data-quality report; select target, task and metric; run multiple supported algorithms through a reproducible pipeline; compare metrics and see why a model was selected; save and version the selected model; submit a valid prediction request via FastAPI; view experiment status, logs and understandable errors; and run tests and CI successfully from a clean checkout while following the documented security, deployment and cost-control steps.

## 7. Functional requirements

Priority: **P0** = required for MVP, **P1** = important, **P2** = later.

### 7.1 Datasets
| ID | Requirement | Priority |
|---|---|---|
| FR-001 | The user can register a CSV upload by supplying filename and declared size; the system creates a dataset record owned by that user. | P0 |
| FR-002 | The system uploads the file to private storage using either a backend-mediated upload or a short-lived presigned URL; the browser never holds long-lived storage credentials. | P0 |
| FR-003 | The system validates the stored object: allowed type, actual size, parseable CSV, non-empty, unambiguous unique headers, row/column limits. Status becomes `READY` or `REJECTED` with a reason. | P0 |
| FR-004 | The system shows a schema summary (column names, inferred numeric/categorical types), missing-value counts and a preview of the first rows. | P0 |
| FR-005 | The system warns about identifier-like columns, high-cardinality columns, suspected target leakage and tiny datasets. | P1 |
| FR-006 | The user can delete a dataset; source file and derived artifacts are removed subject to documented retention rules. | P1 |

*Acceptance (FR-003):* a zero-byte file, a file with duplicate headers, a file exceeding the size limit and a non-CSV file are each rejected with a specific, non-leaky error; a valid fixture file becomes `READY`.

### 7.2 Experiments
| ID | Requirement | Priority |
|---|---|---|
| FR-010 | The user configures an experiment: dataset, target column, task (classification or regression), primary metric, allowed algorithms (from the allowlist), random seed. | P0 |
| FR-011 | The system rejects configurations that are invalid: target not in dataset, metric incompatible with the task or class structure, algorithm not on the allowlist. | P0 |
| FR-012 | Creating an experiment queues it; status moves through `CREATED → QUEUED → RUNNING → SUCCEEDED/FAILED`. | P0 |
| FR-013 | Job submission is idempotent; a repeated submission does not create duplicate runs. | P1 |
| FR-014 | The user sees status, timestamps and an understandable error summary on failure. | P0 |
| FR-015 | The user can cancel a `CREATED`/`QUEUED` experiment (and `RUNNING` only if safe stop is implemented). | P2 (**Open**) |
| FR-016 | The system offers a time-aware split for time-dependent datasets. | P2 (**Open**) |

*Acceptance (FR-012):* submitting a valid experiment returns `QUEUED`; the worker moves it to `RUNNING` and then to a terminal state; invalid transitions are rejected.

### 7.3 Training and evaluation
| ID | Requirement | Priority |
|---|---|---|
| FR-020 | Preprocessing (imputation, encoding, scaling) is fitted only on training data inside a scikit-learn pipeline. | P0 |
| FR-021 | The target column is never used as an input feature. | P0 |
| FR-022 | Data is split into train and held-out test sets; classification splits are stratified where appropriate. | P0 |
| FR-023 | The system trains each selected allowlisted algorithm and records per-run hyper-parameters, metrics, duration and status. | P0 |
| FR-024 | Test data is never used for hyper-parameter selection; tuning uses cross-validation within training data. | P0 |
| FR-025 | The system records split strategy, random seed, metric definition and library versions. | P0 |
| FR-026 | Re-running with the same dataset, configuration and seed yields the same metrics (deterministic fixtures). | P0 |
| FR-027 | The system never imports or executes code from dataset content or user configuration. | P0 |

### 7.4 Results and model selection
| ID | Requirement | Priority |
|---|---|---|
| FR-030 | The system ranks only successfully evaluated runs by the declared primary metric, respecting metric direction (MAE/RMSE lower is better; R², F1, etc. higher is better), with configured tie-breakers. | P0 |
| FR-031 | The results view shows a leaderboard with all recorded metrics (not only the primary) and an explanation of why the winner was chosen. | P0 |
| FR-032 | The UI states that the best score among tested candidates does not guarantee real-world performance. | P1 |
| FR-033 | Metric visualisations (e.g. comparison chart, confusion matrix for classification, predicted-vs-actual for regression). | P1 |

### 7.5 Model registry
| ID | Requirement | Priority |
|---|---|---|
| FR-040 | The selected pipeline is saved as a versioned artifact with metadata (feature schema, preprocessing spec, training config, metrics, library versions). | P0 |
| FR-041 | Model versions are immutable once registered. | P0 |
| FR-042 | Models have an approval/deployment status; only approved models serve predictions. | P0 |
| FR-043 | The user can list models and view a model's metadata and metrics. | P0 |

### 7.6 Prediction
| ID | Requirement | Priority |
|---|---|---|
| FR-050 | `POST /api/v1/models/{model_id}/predict` validates input against the model's expected schema and rejects missing, extra or invalid fields according to a documented policy. | P0 |
| FR-051 | Request size and batch size are limited. | P0 |
| FR-052 | The response includes predictions, model version and a request ID. | P0 |
| FR-053 | The system records which model version handled each prediction, without logging raw input values. | P1 |
| FR-054 | The UI offers a prediction test form generated from the model schema. | P1 |

### 7.7 Platform
| ID | Requirement | Priority |
|---|---|---|
| FR-060 | Users authenticate; every dataset, experiment and model access is ownership-checked. | P0 |
| FR-061 | The system writes audit events (actor, action, resource ID, timestamp, outcome) without row values or secrets. | P1 |
| FR-062 | `GET /health` returns liveness. | P0 |

## 8. Permissions and role boundaries
Default rule (**Implemented**, M7): a user may read and modify only resources they own. Cross-user sharing, admin roles and organisation tenancy are **Open** and out of the MVP.

## 9. Key workflows and edge cases
- **Upload then reject:** file passes declared size but exceeds the limit when measured → `REJECTED`, object removed.
- **Target is constant or has a single class:** experiment rejected at validation with a clear message.
- **Metric incompatible** (e.g. ROC-AUC on multi-class without probability support): rejected at configuration time (FR-011).
- **One algorithm fails:** its run is `FAILED`, other runs continue; the leaderboard ranks successful runs only; if none succeed the experiment is `FAILED`.
- **Worker dies mid-run:** reaper marks the experiment `FAILED` after the timeout.
- **Prediction input has unknown fields:** handled per the documented policy (default: reject).

## 10. Non-functional requirements
| ID | Area | Requirement (limits are **Proposed**) |
|---|---|---|
| NFR-001 | Security | Private buckets, TLS, least-privilege IAM, ownership checks, safe error responses. See [SECURITY.md](SECURITY.md) |
| NFR-002 | Privacy | Logs never contain raw dataset records, secrets or tokens; defined retention and deletion |
| NFR-003 | Reproducibility | Same data + config + seed → same metrics; versions recorded |
| NFR-004 | Reliability | Bounded retries for transient errors; no endless retry of validation failures; abandoned jobs cleaned up |
| NFR-005 | Performance | Training and prediction limits (file size, rows, columns, training time, batch size) enforced; values **TBD**. Starting point to evaluate: small-to-medium datasets that train on a single CPU worker |
| NFR-006 | Cost | Local-first; no always-on or GPU compute in the first release; budget alerts configured before any AWS deploy |
| NFR-007 | Accessibility | WCAG 2.2 AA is the target for the UI (see [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)) |
| NFR-008 | Observability | Structured logs, request IDs, job and prediction metrics |
| NFR-009 | Portability | ML engine has no AWS dependency; cloud access via adapters |
| NFR-010 | Maintainability | CI runs lint, tests and build from a clean checkout |

## 11. Dependencies and assumptions
- Python and scikit-learn for the engine; FastAPI for the API; Next.js for the UI (**Proposed stack**, versions TBD).
- AWS services are optional and used only where Free Tier / Free Plan eligibility and limits allow; account eligibility is unconfirmed.
- Assumption: first users are the owner and portfolio reviewers, not production customers.

## 12. Risks
See [ARCHITECTURE.md § 15](ARCHITECTURE.md#15-trade-offs-and-risks). Product-level risks: misleading confidence in leaderboard scores; unexpected AWS charges; unsafe CSV or artifact handling.

## 13. Success indicators (Proposed — no targets supplied)
- The Definition of Done in § 6 passes end to end on a fixture dataset in CI.
- Reproducibility test (FR-026) passes.
- Zero secrets detected by secret scanning.
- AWS spend stays within the budget the owner sets (**TBD**).

## 14. Roadmap
Phased milestones with requirement mapping are in [ROADMAP.md](ROADMAP.md).

## 15. Open questions
1. Primary persona confirmation and expected number of users.
2. Authentication provider; API-key vs user-token model for predictions.
3. Concrete size/time limits (NFR-005).
4. Cancellation and time-aware splits in or out of MVP.
5. Model approval: manual action by the owner, or automatic when metrics pass a threshold?
