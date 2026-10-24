# Documentation Index

Documentation for **AutoML Lab — Automated Model Training Pipeline**. Back to the [project README](../README.md).

## Status legend
- **Verified / Implemented** — confirmed in code or configuration.
- **Proposed** — planned design, not built. *Milestones M1 to M7 are implemented (M6, the AWS integration, has never been run against a real AWS account); M8 (deployment) is Proposed.*
- **Assumption** — believed true, unconfirmed.
- **Open decision** — explicitly unresolved (`TBD` / "Open" in the documents).

## Core documents
| Document | Purpose |
|---|---|
| [PRD.md](PRD.md) | Problem, goals, personas, MVP scope, functional requirements (FR-xxx), non-functional requirements, risks |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Target system design, components, data flows, ML design, trade-offs |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | UI principles, tokens, components, screens, flows, accessibility |
| [../AGENTS.md](../AGENTS.md) | Rules and protocol for coding agents |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Contribution and review guide |
| [../CONTRIBUTORS.md](../CONTRIBUTORS.md) | Maintainer record |

## Supporting documents
| Document | Purpose |
|---|---|
| [API_SPEC.md](API_SPEC.md) | Routes, error envelope, payload sketches |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Metadata entities, relationships, indexing, retention |
| [SECURITY.md](SECURITY.md) | Threat model, controls, IAM, secrets, privacy |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Environments, CI/CD, cost-control plan |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test layers, fixtures, invariants, quality gates |
| [ROADMAP.md](ROADMAP.md) | Milestones M1–M8 with dependencies and exit criteria |

## Architecture decision records
| ADR | Title | Status |
|---|---|---|
| [0001](ADR/0001-local-first-adapter-architecture.md) | Local-first, adapter-based architecture | Accepted (not yet implemented) |
| [0002](ADR/0002-trusted-joblib-artifacts.md) | Trusted joblib artifacts only | Accepted (implemented in M5) |
| [0003](ADR/0003-save-winning-model-at-training-time.md) | Save the winning model at training time | Accepted (implemented in M5) |
| [0004](ADR/0004-local-accounts-and-bearer-tokens.md) | Local accounts with bearer tokens | Accepted for local use (implemented in M7); cloud provider Open |
| [0005](ADR/0005-s3-storage-and-sqs-job-queue.md) | S3 storage, presigned uploads and an SQS job queue | Accepted (implemented in M6; not run against real AWS) |

## Requirement traceability
PRD requirement IDs map to roadmap milestones in [ROADMAP.md](ROADMAP.md), to routes in [API_SPEC.md](API_SPEC.md), to screens in [DESIGN_SYSTEM.md § 8](DESIGN_SYSTEM.md#8-screen-inventory-proposed), and to test layers in [TESTING_STRATEGY.md](TESTING_STRATEGY.md).

## Top open decisions
1. Authentication provider and prediction-API credential model.
2. Cloud metadata store and training worker runtime.
3. Concrete upload, row, column, time and batch limits.
4. Cancellation and time-aware splits in the MVP.
5. Linter/formatter/type-checker choices and verified run commands (M1).
