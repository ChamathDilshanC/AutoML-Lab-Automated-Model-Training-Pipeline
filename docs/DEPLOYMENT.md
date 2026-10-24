# Deployment and Cost Control

> **Status:** **Proposed.** Nothing is deployed and there is no infrastructure code. A CI workflow (`.github/workflows/ci.yml`) and `docker-compose.yml` exist from M1. AWS cost **cannot be guaranteed to be $0**; Free Tier / Free Plan eligibility, limits and prices change, so check current terms for the actual account and region before enabling any resource.

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
- Run commands: see [AGENTS.md § 5](../AGENTS.md#5-commands). `docker compose up` is defined in `docker-compose.yml` but has not been run yet.

## 3. Option B — Hybrid AWS
**Done in M6** (infrastructure and code, not yet applied or run against real AWS; see [ADR 0005](ADR/0005-s3-storage-and-sqs-job-queue.md)):
- Private S3 bucket for datasets and models, with direct browser uploads through short-lived presigned URLs.
- A standard SQS queue and a dead-letter queue between the API and the worker.
- Least-privilege IAM policies for the API, the worker, and both together (local development).
- Everything defined in Terraform under `infrastructure/terraform/`, checked by `terraform fmt`, `init -backend=false` and `validate` in CI.

**Still open (M8):** where the frontend, the API and the worker run; CloudWatch dashboards and alarms; EventBridge schedules; a budget and alerts.

Trying it yourself (creates billable resources; read the cost notes first):
1. Install Terraform and sign in to AWS with SSO or `aws configure` (never put keys in files).
2. `cd infrastructure/terraform`, `terraform init`, `terraform plan -out=tfplan`, read it, `terraform apply tfplan`.
3. Attach the `local_dev_policy_arn` output to a user or role you control (commands in the Terraform README).
4. Put `terraform output -raw backend_environment` into `backend/.env`, start the API and the worker, and sign in.
5. When finished: delete your datasets in the app, then `terraform destroy` (use `-var force_destroy=true` for a throwaway bucket) and check the S3 and SQS consoles.

Full instructions: [infrastructure/terraform/README.md](../infrastructure/terraform/README.md). Select the compute runtimes only after measuring memory, execution duration, package size and expected workload, and confirming all service charges.

Select exact runtimes only after measuring memory, execution duration, package size and expected workload, and confirming all service charges.

## 4. Configuration
Environment variables per environment; local values in an untracked `.env`; `.env.example` lists names only. `SECRET_KEY` (at least 32 random characters) is **required whenever `ENVIRONMENT` is not `local`**: the API refuses to start without it. Locally it may be omitted, which gives a random per-process key, so sign-ins reset when the API restarts. Create accounts with `python -m app.cli create-user <name>` (inside the backend container when using Docker Compose); there is no public sign-up. Cloud mode adds `STORAGE_MODE` (`local` or `s3`), `S3_BUCKET`, `AWS_REGION`, `S3_PRESIGN_EXPIRES_SECONDS`, `S3_ADDRESSING_STYLE` (`virtual` for AWS, `path` for S3-compatible emulators such as LocalStack or MinIO), `JOB_MODE` (`db` or `sqs`), `SQS_QUEUE_URL` and `SQS_WAIT_SECONDS`; no AWS keys are ever configured, the standard AWS credential chain is used. Keep `JOB_TIMEOUT_SECONDS` equal to the Terraform variable `job_timeout_seconds` (the queue's visibility timeout). Rate limits and the reaper are tuned with `PREDICT_RATE_LIMIT_PER_MINUTE`, `LOGIN_RATE_LIMIT_PER_MINUTE`, `JOB_TIMEOUT_SECONDS` and `REAPER_INTERVAL_SECONDS`. In AWS use IAM roles and temporary credentials; add a managed secrets service only if necessary and budget-checked.

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
