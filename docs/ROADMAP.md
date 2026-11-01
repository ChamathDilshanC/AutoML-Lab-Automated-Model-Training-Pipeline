# Roadmap

> **Status:** M1 is **implemented and merged** (CI passing). M2 to M8 are **implemented** (see their rows). M7 was done before M6 so the AWS work starts from a secure base. M6 and M8 have not been applied to or run against a real AWS account. Milestones follow the order in the owner's architecture brief. Dates are intentionally absent (none supplied).

Related: [PRD](PRD.md) · [Architecture](ARCHITECTURE.md) · [Testing](TESTING_STRATEGY.md)

## Milestone overview
```mermaid
flowchart LR
    M1[M1 Foundation] --> M2[M2 Dataset workflow]
    M2 --> M3[M3 ML engine]
    M3 --> M4[M4 Experiment management]
    M4 --> M5[M5 Model registry]
    M5 --> M6[M6 AWS integration]
    M5 --> M7[M7 Security and reliability]
    M6 --> M8[M8 Deployment and docs]
    M7 --> M8
```
M3 can start in parallel with M2 because the engine is AWS- and web-independent.

## Milestones
| ID | Milestone | Deliverables | Depends on | PRD coverage | Exit criteria | Status |
|---|---|---|---|---|---|---|
| M1 | Foundation | Repo structure, Next.js app shell, FastAPI skeleton with `/health`, local SQLite, CI (lint, test, build), `.env.example`, Docker Compose | — | FR-062, NFR-010 | CI green from a clean checkout | Implemented; CI passing; Docker Compose run not verified |
| M2 | Dataset workflow | CSV upload, storage adapter (local), validation, schema preview, quality report, limits | M1 | FR-001–FR-005 | Valid fixture becomes `READY`; malformed fixtures `REJECTED` with safe errors | Implemented with local storage; owner is a placeholder until M7; presigned upload deferred to M6 |
| M3 | ML engine | `automl` package: validation, preprocessing pipeline, splits, trainer, evaluator, metrics | M1 (not M2) | FR-020–FR-027, FR-030 | Deterministic ML tests pass; no leakage tests pass | Implemented (engine only; not yet exposed through the API) |
| M4 | Experiment management | Experiment API, job states, local worker, run history, leaderboard, reports | M2, M3 | FR-010–FR-014, FR-031–FR-033 | Fixture experiment runs queued → succeeded; leaderboard explains winner | Implemented with a local polling worker. Cancellation and stored run reports are not included |
| M5 | Model registry | Artifact versioning, metadata, approval, prediction endpoint, prediction test UI | M4 | FR-040–FR-054 | Registered model serves valid prediction; invalid payloads rejected | Implemented with local storage. No revoke, model deletion, authentication or rate limiting yet |
| M6 | AWS integration | S3 adapter, scoped IAM, optional EventBridge orchestration, CloudWatch logging | M5 | NFR-006, NFR-009 | Same E2E test passes against S3 adapter with no long-lived stray resources | Implemented: S3 storage with presigned uploads, an SQS queue with a dead-letter queue, least-privilege IAM and Terraform, all tested against a mock and in a real browser against a local mock server. **The live API runs in this mode, but uploads and job queueing have not been exercised on AWS yet**; EventBridge and CloudWatch are left to M8 |
| M7 | Security and reliability | Auth, ownership checks everywhere, retention/deletion, retries, rate limits, failure handling | M5 | FR-006, FR-013, FR-060, FR-061, NFR-001–NFR-004 | Security test suite passes; abandoned jobs are reaped | Implemented for local accounts (see [SECURITY § 15](SECURITY.md#15-implemented-so-far-m7) for the gaps: no password reset or MFA, no server-side logout) |
| M8 | Deployment and documentation | Terraform, CI/CD with OIDC, architecture diagram, screenshots, setup and cost notes | M6, M7 | § 6 MVP | Definition of Done in the PRD demonstrably met | Deployment part implemented as code: production Dockerfile, PostgreSQL with Alembic, Terraform (VPC without NAT, RDS, ECR, the API on Lambda, the Fargate worker with queue-driven autoscaling, an optional Amplify app, OIDC role, budget), `deploy.yml`, ADRs 0006 to 0009, the deployment and worker-autoscaling guides and the architecture diagram. Verified: whole suite on PostgreSQL 18, a production-mode run through the entrypoint, `terraform validate`, `actionlint`. **Applied to AWS: the API is live on Lambda (deployed by hand) and the frontend runs on Vercel; worker autoscaling pending the next apply; an end-to-end training run on AWS and the deploy workflow not verified; screenshots are not done** |

## Recommended first milestone
**M1 Foundation**, followed immediately by **M3 ML engine**. The engine is the product's core value, is cheap to test, and has no external dependencies, which de-risks the project before any cloud work.

## Deferred / Open
Cancellation (FR-015), time-aware splits (FR-016), multi-user sharing, additional file formats, additional algorithms.
