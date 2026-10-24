# Deployment and Cost Control

> **Status:** **Proposed.** Nothing is deployed and no infrastructure code or CI workflow exists. AWS cost **cannot be guaranteed to be $0**; Free Tier / Free Plan eligibility, limits and prices change, so check current terms for the actual account and region before enabling any resource.

Related: [Architecture § 14](ARCHITECTURE.md#14-deployment-topology) · [Security](SECURITY.md) · [Testing](TESTING_STRATEGY.md) · [Roadmap](ROADMAP.md)

## 1. Environments
| Environment | Purpose | State |
|---|---|---|
| Local | Day-to-day development and full workflow validation | Proposed (first target) |
| CI | Lint, tests, build on every PR | Proposed |
| AWS (hybrid) | Optional portfolio deployment | Proposed; runtime choices **Open** |

## 2. Option A — Local-first (recommended starting point)
- Next.js frontend, FastAPI backend, SQLite metadata, a local Python worker, a local artifact directory (or a development S3 bucket if eligible).
- Docker Compose for repeatable setup.
- Validates the entire workflow before any cloud dependency or spend.
- Run commands: **TBD** until the services are scaffolded (see [AGENTS.md](../AGENTS.md)).

## 3. Option B — Hybrid AWS
- Frontend hosted separately or by an appropriate hosting option.
- FastAPI on a selected compute service.
- Private S3 for datasets and artifacts.
- Separate worker runtime for training (Lambda is not assumed to fit).
- EventBridge for scheduled or event-driven automation if needed.
- CloudWatch for logs and metrics.

Select exact runtimes only after measuring memory, execution duration, package size and expected workload, and confirming all service charges.

## 4. Configuration
Environment variables per environment; local values in an untracked `.env`; `.env.example` lists names only. In AWS use IAM roles and temporary credentials; add a managed secrets service only if necessary and budget-checked.

## 5. CI/CD (Proposed)
Pipeline stages on GitHub Actions:
1. Install from lockfiles.
2. Format, lint, static checks.
3. Backend unit and API tests.
4. Frontend lint, type check and build.
5. ML tests on a small deterministic fixture.
6. Build Docker images (if used).
7. Dependency and image scanning.
8. Terraform format and validate.
9. Deploy only from a protected branch/environment after explicit configuration and cost review.

Use GitHub OIDC with a narrowly scoped IAM role instead of long-lived AWS keys where supported. Require approval for deployment and destructive infrastructure changes.

## 6. Release and rollback
Model versions are immutable; rollback of a model means pointing consumers at a previous approved version. Application rollback strategy depends on the chosen runtime (**TBD**).

## 7. Health checks
`GET /health` for liveness. Readiness checks (database, storage reachability) are **Open**.

## 8. Cost-control plan
- Build and test locally first; use small public/sample datasets and enforce upload/training limits.
- Avoid GPU instances and always-on compute in the first release.
- Use Lambda only for short tasks within documented limits; keep the training worker local until a suitable AWS runtime is chosen.
- Avoid NAT Gateways, managed always-on databases and other resources that cause ongoing charges unless required and budgeted.
- Configure AWS Budgets and billing alerts (they are alerts, **not** a hard cap).
- Apply S3 lifecycle policies; remove unused objects, logs and test resources; review CloudWatch log retention.
- Tear down infrastructure after experiments. After `terraform destroy`, confirm what remains — some stores or buckets may intentionally retain data.
- Test workflows must not create long-lived AWS resources.

## 9. Open questions
Hosting for the frontend and API; worker runtime; account Free Tier / Free Plan eligibility; monthly budget threshold; Terraform state location (never commit state).
