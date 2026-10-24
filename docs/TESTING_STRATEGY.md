# Testing Strategy

> **Status:** CI and a first set of tests exist (`backend/tests/`: health, config, database, ML engine, `automl` import-independence). ML tests build small seeded data in-code instead of reading fixture files. Everything else below is **Proposed**. Verified commands are in [AGENTS.md § 5](../AGENTS.md#5-commands).

Related: [PRD](PRD.md) · [Architecture § 13](ARCHITECTURE.md#13-test-architecture) · [Deployment § 5](DEPLOYMENT.md#5-cicd-proposed)

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
