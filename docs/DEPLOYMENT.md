# Deployment and Cost Control

> **Status:** Local mode, CI, cloud mode (M6) and the AWS deployment (M8) are **implemented** as code. **Nothing has been applied to a real AWS account** and the deployment pipeline has never run. AWS cost **cannot be guaranteed to be $0 or under $10**; Free Tier eligibility, limits and prices depend on the account and change, so check current terms before enabling any resource. See [ADR 0006](ADR/0006-aws-deployment.md).

Related: [Architecture § 14](ARCHITECTURE.md#14-deployment-topology) · [Security](SECURITY.md) · [Testing](TESTING_STRATEGY.md) · [Roadmap](ROADMAP.md)

## 1. Environments
| Environment | Purpose | State |
|---|---|---|
| Local | Day-to-day development and full workflow validation (SQLite, local files, `docker compose`) | Implemented |
| CI | Lint, tests (SQLite and PostgreSQL), Docker build, Terraform and workflow checks on every PR | Implemented |
| AWS production | Frontend on Vercel; API on App Runner; worker on ECS Fargate; RDS PostgreSQL; S3; SQS | Implemented as code, **not applied** |

## 2. Option A — Local-first
- Next.js frontend, FastAPI backend, SQLite metadata, a local Python worker, a local artifact directory.
- Docker Compose for repeatable setup.
- Validates the entire workflow before any cloud dependency or spend.
- Run commands: see [AGENTS.md § 5](../AGENTS.md#5-commands).

## 3. Option B — AWS (M6 and M8)
```
Browser ──► Vercel (Next.js)
   │               │ HTTPS, bearer token
   │               ▼
   │      App Runner: API ──────────────► RDS PostgreSQL (private)
   │         │  │                              ▲
   │         │  └──► SQS queue ──► ECS Fargate: worker
   └─ presigned PUT ─► S3 ◄───────────────────┘ (datasets, models)
```
What exists, all in `infrastructure/terraform/`:

| File | Creates |
|---|---|
| `main.tf`, `queue.tf`, `iam.tf` (M6) | Private S3 bucket, SQS queue and dead-letter queue, least-privilege IAM policies for the API and the worker |
| `network.tf` | VPC, two public and two private subnets, **no NAT gateway**, S3 gateway endpoint, SQS interface endpoint |
| `database.tf` | RDS PostgreSQL `db.t4g.micro` (private, encrypted, TLS required, deletion protection, 1 day of backups, the most the AWS Free plan allows; set `db_backup_retention_days` higher on a paid plan) and the security groups |
| `secrets.tf` | Generated database password and token-signing key as SSM SecureString parameters |
| `ecr.tf` | The image repository (scan on push, last 20 images kept) |
| `api.tf` | App Runner service, VPC connector, the image-pull role and the API runtime role (M6 API policy attached) |
| `worker.tf` | ECS cluster, log group, task definition (command `worker`), service, execution role and worker runtime role (M6 worker policy attached) |
| `cicd.tf` | GitHub OIDC provider and the deploy role |
| `budget.tf` | AWS Budget with email alerts |

The App Runner service and the ECS service are created only when `enable_compute = true`.

### Apply order (three steps, because the services need an image that does not exist yet)
You need: an AWS account you control, Terraform 1.6 or newer, the AWS CLI, Docker, and credentials from `aws sso login` or `aws configure` (never keys in files). Read [Cost and how to stop it](#cost-and-how-to-stop-it) first.

1. **Base infrastructure.**
   ```bash
   cd infrastructure/terraform
   cp terraform.tfvars.example terraform.tfvars    # set region, github_repository and budget_alert_email
   terraform init
   terraform plan -out=tfplan                      # read it
   terraform apply tfplan
   ```
   The subnets use the zones `<region>a` and `<region>b` without looking them up (some organizations deny that lookup); set `availability_zones` if your account has other zones. RDS takes several minutes. Confirm the budget's subscription email if AWS sends one.
2. **First image.** Push it by hand (the services in step 3 cannot start without it; later images are pushed by the pipeline):
   ```bash
   REPO=$(terraform output -raw ecr_repository_url)
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin "${REPO%%/*}"
   docker build -t "$REPO:latest" ../../backend
   docker push "$REPO:latest"
   ```
3. **Create the services.** Set `enable_compute = true` in `terraform.tfvars` (and, when you want training to run, `worker_desired_count = 1`), then `terraform plan` and `terraform apply`. The API container applies the database migrations when it starts. `terraform output api_url` prints the API's URL.
4. **Create the first user** (there is no public sign-up). The database is private, so the CLI has to run inside the VPC. Set `enable_ecs_exec = true` and `worker_desired_count = 1`, `terraform apply`, then open a shell in the running worker (needs the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) for the AWS CLI) and run the CLI there:
   ```bash
   TASK=$(aws ecs list-tasks --cluster <cluster> --service-name <worker-service> --query 'taskArns[0]' --output text)
   aws ecs execute-command --cluster <cluster> --task "$TASK" --container worker --interactive \
     --command "python -m app.cli create-user <name>"
   ```
   It asks for the password twice. Set `enable_ecs_exec = false` and apply again afterwards. (Not yet tried against real AWS.)
5. **Connect the frontend.** In Vercel, import the repository with the root directory `frontend` and set `NEXT_PUBLIC_API_BASE_URL` to the `api_url` output. Then put the Vercel origin (for example `https://your-project.vercel.app`, no trailing slash) in `frontend_origins` and `terraform apply` again; this sets the API's CORS and the bucket's CORS.
6. **Turn on automatic deploys.** In GitHub, create the environment `production` (add required reviewers if you want a manual approval), then add the repository variables printed by `terraform output github_variables` (including `DEPLOY_ENABLED=true`). From then on every push to `main` builds, pushes and rolls out.

### Cost and how to stop it
Whether any of this is free depends on your account and on current AWS terms; the Free Tier does not cover everything here. The hourly-billed parts are the RDS instance (Free Tier hours apply only to eligible accounts and only for a limited period), the App Runner instance, the SQS interface endpoint, and a running worker task; S3, SQS requests, ECR storage and logs are billed by use. **Left running, this stack should be expected to cost more than 10 USD a month.** The budget is an alert, not a cap.

Ways to cut spend, cheapest first:
- Stop the worker: `worker_desired_count = 0` and apply (experiments stay `QUEUED`; nothing is lost). Quick, no apply: `aws ecs update-service --cluster <cluster> --service <service> --desired-count 0`.
- Pause the API: `aws apprunner pause-service --service-arn <arn>` (and `resume-service` later).
- Stop the database: `aws rds stop-db-instance --db-instance-identifier <id>` (RDS restarts it by itself after seven days).
- Remove everything: see "Teardown".

### Teardown
1. In the app, delete your datasets (this deletes their models), or set `force_destroy = true`.
2. Set `db_deletion_protection = false` and `db_skip_final_snapshot = true` (only if you do not need the data) and `terraform apply`.
3. `terraform destroy`. Then check the RDS, App Runner, ECS, VPC (endpoints), S3, SQS, ECR and SSM consoles, and the Budgets page, for anything left. Remove the Vercel project separately.

## 4. Configuration
Environment variables per environment; local values in an untracked `.env`; `.env.example` lists names only. `SECRET_KEY` (at least 32 random characters) is **required whenever `ENVIRONMENT` is not `local`**: the API refuses to start without it. Locally it may be omitted, which gives a random per-process key, so sign-ins reset when the API restarts. Create accounts with `python -m app.cli create-user <name>` (inside the backend container when using Docker Compose); there is no public sign-up. Cloud mode adds `STORAGE_MODE` (`local` or `s3`), `S3_BUCKET`, `AWS_REGION`, `S3_PRESIGN_EXPIRES_SECONDS`, `S3_ADDRESSING_STYLE` (`virtual` for AWS, `path` for S3-compatible emulators such as LocalStack or MinIO), `JOB_MODE` (`db` or `sqs`), `SQS_QUEUE_URL` and `SQS_WAIT_SECONDS`; no AWS keys are ever configured, the standard AWS credential chain is used. Keep `JOB_TIMEOUT_SECONDS` equal to the Terraform variable `job_timeout_seconds` (the queue's visibility timeout). Rate limits and the reaper are tuned with `PREDICT_RATE_LIMIT_PER_MINUTE`, `LOGIN_RATE_LIMIT_PER_MINUTE`, `JOB_TIMEOUT_SECONDS` and `REAPER_INTERVAL_SECONDS`. In AWS the containers use IAM roles and temporary credentials. Production adds `ENVIRONMENT=production` (anything but local requires PostgreSQL and a SECRET_KEY), `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_SSLMODE` and `DB_PASSWORD` (or a `DATABASE_URL`), `RUN_MIGRATIONS` (the API container runs migrations unless this is `false`), `MIGRATION_WAIT_SECONDS`, `CORS_ORIGINS` (a JSON list such as `["https://your-project.vercel.app"]`) and `TRUSTED_PROXY_HOPS`. Terraform sets all of them; `DB_PASSWORD` and `SECRET_KEY` are passed to the containers as references to SSM parameters, never as plain values. Outside `local`, SQLite is refused.

## 5. CI/CD
**CI** (`.github/workflows/ci.yml`, every pull request and push to `main`): backend lint, format, types and tests on SQLite; the same tests against a PostgreSQL 16 service container; the Docker image is built, imported, run as a non-root user, checked to refuse SQLite in production and to answer `/health`; frontend lint, type check and build; Terraform `fmt`, `init -backend=false` and `validate`; `actionlint` on every workflow.

**Deploy** (`.github/workflows/deploy.yml`, push to `main` or by hand): runs only when the repository variable `DEPLOY_ENABLED` is `true` and, if you added reviewers, after approval of the `production` environment. It assumes the deploy role through GitHub OIDC (no AWS keys anywhere), builds the image, smoke-tests it, pushes the commit-SHA tag and `latest` to ECR, starts an App Runner deployment and waits for it, forces a new ECS deployment of the worker, waits for it to be stable, and finally requests `/health`. Not yet run.

Not done: dependency and image vulnerability gates (ECR scans on push, but the result does not block a deploy), ML-specific CI tests beyond the existing suite, and running Terraform from the pipeline (infrastructure changes are applied by a person).

## 6. Release and rollback
Model versions are immutable; rollback of a model means pointing consumers at a previous approved version. Application rollback: every deploy also pushes an image tagged with the commit SHA. Re-tag the previous SHA as `latest` (`aws ecr batch-get-image` then `put-image`, or re-run the deploy workflow from the earlier commit) and start a new deployment. Database migrations are forward-only; a rollback to code older than the current schema is safe only if that code tolerates the newer schema (the first migration is the only one so far).

## 7. Health checks
`GET /health` for liveness, used by App Runner's health check and by the deploy workflow's smoke test. It does not check the database. Readiness checks (database, storage reachability) are **Open**.

## 8. Cost-control plan
- Build and test locally first; use small public/sample datasets and enforce upload/training limits.
- No GPU instances. No NAT gateway (the network is designed around its absence). One small single-AZ database. The worker defaults to **zero** tasks.
- An AWS Budget emails at 80 % and 100 % of actual and 100 % of forecast spend against 10 USD a month (they are alerts, **not** a hard cap).
- S3 lifecycle rules clean up abandoned multipart uploads; ECR keeps 20 images; worker logs are kept 14 days.
- Stop or tear down when idle (see "Cost and how to stop it" and "Teardown" above). After `terraform destroy`, confirm what remains.
- Test workflows must not create long-lived AWS resources: tests use mocks, and CI never has AWS credentials.

## 9. Open questions
- Free Tier / Free Plan eligibility of the actual account, and the real monthly cost of the running stack.
- Whether App Runner appends exactly one `X-Forwarded-For` entry (the sign-in limiter assumes it; ADR 0006 § 9).
- Where the Terraform state lives: it contains the generated database password and signing key, so use an encrypted, access-controlled remote backend (never commit state).
- A scripted way to create the first user inside the VPC.
- Readiness checks, CloudWatch alarms and dashboards, and an API-side log retention setting.
