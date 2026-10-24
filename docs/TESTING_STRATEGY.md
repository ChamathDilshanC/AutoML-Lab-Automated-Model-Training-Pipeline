# Testing Strategy

> **Status:** CI and a first set of tests exist (`backend/tests/`: health, config, database, ML engine, dataset API, experiment API, worker, model registry and prediction API, authentication, ownership (IDOR), deletion and revocation, rate limiting, the reaper, S3 and SQS in cloud mode (against `moto`, no AWS account), the Terraform files, storage, data quality, `automl` import-independence). ML tests build small seeded data in-code instead of reading fixture files. Headless-browser checks of the upload flow (M2) and of the experiment flow with a separately started worker (M4: queued with no worker, live update to the leaderboard, metric direction, server-side validation errors) were run by hand and are not part of CI. They caught a CORS bug that `TestClient` cannot see, now covered by a preflight test. The M5 run (33 checks) covered approval gating, predictions for a classifier and a regressor through the generated form, versioning and the model list. ML and registry tests train real models through the worker; artifact-trust tests assert that a tampered artifact never reaches `joblib.load`. All API tests sign in as a real user with a real token; there is no authentication bypass in the fixtures. The security tests were checked by **mutation**: seven deliberate breakages (an unprotected router, a removed rate limit, a dropped ownership filter, an unconditional finish, an extra accepted JWT algorithm, leftover model files after deletion, and different answers for unknown user versus wrong password) were each caught by the suite. The M6 cloud-mode browser run (16 checks) used a local `moto` HTTP server: direct presigned upload with CORS and no bearer token sent to storage, the SQS worker, a model loaded from the bucket, cleanup after a failed upload, and an empty bucket after deletion. It also exposed that `bucket.localhost` URLs cannot be resolved by Python on Windows, which led to the `S3_ADDRESSING_STYLE` setting. The first browser run after the M6 flow change caught a CORS gap (the `PUT` method was not allowed) that `TestClient` cannot see; a preflight test now covers every call the frontend makes. Nine deliberate breakages of the AWS code, queue rules, IAM lists and Terraform were each caught by the suite. `terraform fmt`, `init` and `validate` run only in CI. The M7 browser run (35 checks, two real users) covered the sign-in gate, the open-redirect guard, dialogs, the rate limit, revocation, deletion, cross-user isolation and bad tokens. Everything else below is **Proposed**. Verified commands are in [AGENTS.md § 5](../AGENTS.md#5-commands).

Related: [PRD](PRD.md) · [Architecture § 13](ARCHITECTURE.md#13-test-architecture) · [Deployment § 5](DEPLOYMENT.md#5-cicd)

## 1. Principles
- The `automl` engine has no AWS dependency, so most tests run offline and fast.
- ML tests use small, deterministic fixture datasets with fixed seeds.
- Cloud-dependent tests run against local adapters or mocks by default; real AWS is opt-in and must not leave resources behind.

## 2. Test layers
| Layer | Scope | Key scenarios | PRD |
|---|---|---|---|
| Unit | CSV validation, target validation, preprocessing, metrics, ranking, artifact metadata | Empty file, duplicate headers, constant target, metric direction, tie-breakers | FR-003, FR-011, FR-030 |
| ML | Pipeline correctness | Train/test separation, no target leakage, imputer/encoder fitted on train only, reproducible metrics for same seed, stratification | FR-020–FR-026 |
| Integration | Experiment lifecycle, storage adapter, result retrieval | Valid state transitions, invalid transitions rejected, idempotent submission, abandoned-job reaper | FR-012, FR-013 |
| API | Contract and behaviour | Authentication, ownership (`404` on foreign IDs), malformed payloads, size limits, rate limits, safe errors | FR-050–FR-060 |
| Security | Abuse cases | Oversized/mis-typed uploads, CSV formula cells in exports, unauthorised object access, secret scan, dependency scan | NFR-001, NFR-002 |
| Frontend | Lint, type check, component and accessibility checks | Keyboard flow for upload and experiment forms, status badge text alternatives | NFR-007 |
| End-to-end | Whole workflow | Upload fixture → train small experiment → inspect leaderboard → register → request prediction | § 6 MVP |
| Cost | Infra hygiene | Test workflows create no unplanned long-lived AWS resources | NFR-006 |

## 3. Fixture datasets
Small tabular CSVs committed under a test-data directory (location **TBD**): one classification (including an imbalanced variant), one regression, and malformed variants (empty, duplicate headers, wrong delimiter, oversized-by-rows). Fixtures contain no personal data.

## 4. Key invariants to assert
1. Predictions from a registered model match predictions from the pipeline that was evaluated.
2. The target column is absent from the model's feature schema.
3. Higher-is-better vs lower-is-better ordering is correct for every supported metric.
4. A failed run never appears in the leaderboard.
5. Error responses contain no stack trace, storage key or dataset value.

## 5. Quality gates (Proposed)
A PR can merge only if format/lint, type checks, backend tests, ML tests, frontend build and secret/dependency scans pass in CI. Coverage thresholds are **TBD**.

## 6. Reporting
Test and CI results are recorded in PR descriptions; do not claim a check passed unless it ran.
