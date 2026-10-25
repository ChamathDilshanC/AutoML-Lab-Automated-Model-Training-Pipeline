# Deployment and Cost Control

> **Status:** Local mode, CI, cloud mode (M6) and the AWS deployment (M8) are **implemented** as code. The base layer (`enable_compute = false`: network, database, bucket, queues, registry, IAM, budget) has been applied to one AWS account by the maintainer; the API on Lambda, the worker service and the Amplify frontend have **not** been applied, and the deployment pipeline has never run. AWS cost **cannot be guaranteed to be $0 or under $10**; Free Tier eligibility, limits and prices depend on the account and change, so check current terms before enabling any resource. See [ADR 0006](ADR/0006-aws-deployment.md) and [ADR 0007](ADR/0007-lambda-api-and-amplify-frontend.md).

Related: [Architecture § 14](ARCHITECTURE.md#14-deployment-topology) · [Security](SECURITY.md) · [Testing](TESTING_STRATEGY.md) · [Roadmap](ROADMAP.md)

## 1. Environments
| Environment | Purpose | State |
|---|---|---|
| Local | Day-to-day development and full workflow validation (SQLite, local files, `docker compose`) | Implemented |
| CI | Lint, tests (SQLite and PostgreSQL), Docker build, Terraform and workflow checks on every PR | Implemented |
| AWS production | Frontend on Amplify Hosting (or Vercel); API on Lambda behind a Function URL; worker on ECS Fargate; RDS PostgreSQL; S3; SQS | Implemented as code; base layer applied, compute and frontend **not applied** |

## 2. Option A — Local-first
- Next.js frontend, FastAPI backend, SQLite metadata, a local Python worker, a local artifact directory.
- Docker Compose for repeatable setup.
- Validates the entire workflow before any cloud dependency or spend.
- Run commands: see [AGENTS.md § 5](../AGENTS.md#5-commands).

## 3. Option B — AWS (M6 and M8)
```
Browser ──► Amplify Hosting (Next.js)
   │               │ HTTPS, bearer token
   │               ▼
   │      Lambda Function URL: API ─────► RDS PostgreSQL (private)
   │         │  │   (private subnets)          ▲
   │         │  └──► SQS queue ──► ECS Fargate: worker
   └─ presigned PUT ─► S3 ◄───────────────────┘ (datasets, models)
```
What exists, all in `infrastructure/terraform/`:

| File | Creates |
|---|---|
| `main.tf`, `queue.tf`, `iam.tf` (M6) | Private S3 bucket, SQS queue and dead-letter queue, least-privilege IAM policies for the API and the worker |
| `network.tf` | VPC, two public and two private subnets, **no NAT gateway**, S3 gateway endpoint, SQS interface endpoint |
| `database.tf` | RDS PostgreSQL `db.t4g.micro` (private, encrypted, TLS required, deletion protection, 1 day of backups, the most the AWS Free plan allows; set `db_backup_retention_days` higher on a paid plan) and the security groups |
| `secrets.tf` | Generated database password and token-signing key as SSM SecureString parameters (the worker reads them by reference; the Lambda API gets the values as encrypted environment variables, [ADR 0007](ADR/0007-lambda-api-and-amplify-frontend.md)) |
| `ecr.tf` | The image repository (scan on push, last 20 images kept) |
| `api.tf` | The API's Lambda function (container image, private subnets, the `api` security group), its public Function URL and the two permissions it needs, a log group, and the API runtime role (M6 API policy, VPC access, pulling its own image) |
| `frontend.tf` | Amplify Hosting app and branch, built from `frontend/` on every push, with `NEXT_PUBLIC_API_BASE_URL` set to the API's URL |
| `worker.tf` | ECS cluster, log group, task definition (command `worker`), service, execution role and worker runtime role (M6 worker policy attached) |
| `cicd.tf` | GitHub OIDC provider and the deploy role |
| `budget.tf` | AWS Budget with email alerts |

The Lambda function, its Function URL and the ECS service are created only when `enable_compute = true`; with `false`, the base infrastructure (network, database, bucket, queues, registry, IAM, budget) is applied on its own. The Amplify app and branch are created only when `enable_frontend = true`. App Runner is no longer used: AWS closed it to new customers on 30 April 2026, which is what `SubscriptionRequiredException` meant ([ADR 0007](ADR/0007-lambda-api-and-amplify-frontend.md)).

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
   docker build --provenance=false -t "$REPO:latest" ../../backend   # Lambda needs a single-manifest image
   docker push "$REPO:latest"
   ```
3. **Create the services.** Set `enable_compute = true` in `terraform.tfvars` (and, when you want training to run, `worker_desired_count = 1`), then `terraform plan` and `terraform apply`. The API applies the database migrations when a Lambda instance starts, so the first request (for example `curl "$(terraform output -raw api_url)/health"`) can take several seconds. `terraform output api_url` prints the API's URL.
4. **Create the first user** (there is no public sign-up). The database is private, so the CLI has to run inside the VPC. Set `enable_ecs_exec = true` and `worker_desired_count = 1`, `terraform apply`, then open a shell in the running worker (needs the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) for the AWS CLI) and run the CLI there:
   ```bash
   TASK=$(aws ecs list-tasks --cluster <cluster> --service-name <worker-service> --query 'taskArns[0]' --output text)
   aws ecs execute-command --cluster <cluster> --task "$TASK" --container worker --interactive \
     --command "python -m app.cli create-user <name>"
   ```
   It asks for the password twice. Set `enable_ecs_exec = false` and apply again afterwards. (Not yet tried against real AWS.)
5. **Connect the frontend.** Either:
   - **Amplify Hosting.** Create a GitHub personal access token that can read the repository, then `export TF_VAR_amplify_github_token=<token>` (never put it in a file), set `enable_frontend = true` and `terraform apply`. Amplify connects through its GitHub App; install it on the repository if the console asks. Terraform does not start a build: run `aws amplify start-job --app-id "$(terraform output -raw amplify_app_id)" --branch-name main --job-type RELEASE` (and again whenever `api_url` changes, because the URL is built into the bundle). The Amplify origin (`terraform output frontend_url`) is added to the API's and the bucket's CORS automatically. Amplify documents Next.js support only up to version 15 and lists streaming as unsupported, and this app is on Next.js 16, so check the build log and the pages before relying on it.
   - **Vercel.** Import the repository with the root directory `frontend` and set `NEXT_PUBLIC_API_BASE_URL` to the `api_url` output. Then put the Vercel origin (for example `https://your-project.vercel.app`, no trailing slash) in `frontend_origins` and `terraform apply` again; this sets the API's CORS and the bucket's CORS.
6. **Turn on automatic deploys.** In GitHub, create the environment `production` (add required reviewers if you want a manual approval), then add the repository variables printed by `terraform output github_variables` (including `DEPLOY_ENABLED=true`). From then on every push to `main` builds, pushes and rolls out.

### Cost and how to stop it
Whether any of this is free depends on your account and on current AWS terms; the Free Tier does not cover everything here. The hourly-billed parts are the RDS instance (Free Tier hours apply only to eligible accounts and only for a limited period), the SQS interface endpoint, and a running worker task; S3, SQS requests, ECR storage and logs are billed by use. The API on Lambda is billed per request and per GB-second of running time; Lambda's always-free allowance (1 million requests and 400,000 GB-seconds a month, about 55 hours of running time at 2 GB) applies on every plan, so a lightly used API should cost nothing. The Function URL is public, so heavy traffic would be billed. Amplify bills build minutes, storage, data transfer and server-side rendering by use (a few cents per build). **Left running, this stack should be expected to cost more than 10 USD a month.** The budget is an alert, not a cap.

Ways to cut spend, cheapest first:
- Stop the worker: `worker_desired_count = 0` and apply (experiments stay `QUEUED`; nothing is lost). Quick, no apply: `aws ecs update-service --cluster <cluster> --service <service> --desired-count 0`.
- Stop the API: `aws lambda put-function-concurrency --function-name <name> --reserved-concurrent-executions 0` (every request is then refused; `delete-function-concurrency` undoes it).
- Stop frontend builds: turn off auto-build on the Amplify branch, or set `enable_frontend = false` and apply to delete the app.
- Stop the database: `aws rds stop-db-instance --db-instance-identifier <id>` (RDS restarts it by itself after seven days).
- Remove everything: see "Teardown".

### Teardown
1. In the app, delete your datasets (this deletes their models), or set `force_destroy = true`.
2. Set `db_deletion_protection = false` and `db_skip_final_snapshot = true` (only if you do not need the data) and `terraform apply`.
3. `terraform destroy`. Then check the RDS, Lambda, Amplify, ECS, VPC (endpoints and network interfaces: Lambda's can take some minutes to go), S3, SQS, ECR and SSM consoles, and the Budgets page, for anything left. Remove a Vercel project separately.

## 4. Configuration
Environment variables per environment; local values in an untracked `.env`; `.env.example` lists names only. `SECRET_KEY` (at least 32 random characters) is **required whenever `ENVIRONMENT` is not `local`**: the API refuses to start without it. Locally it may be omitted, which gives a random per-process key, so sign-ins reset when the API restarts. Create accounts with `python -m app.cli create-user <name>` (inside the backend container when using Docker Compose); there is no public sign-up. Cloud mode adds `STORAGE_MODE` (`local` or `s3`), `S3_BUCKET`, `AWS_REGION`, `S3_PRESIGN_EXPIRES_SECONDS`, `S3_ADDRESSING_STYLE` (`virtual` for AWS, `path` for S3-compatible emulators such as LocalStack or MinIO), `JOB_MODE` (`db` or `sqs`), `SQS_QUEUE_URL` and `SQS_WAIT_SECONDS`; no AWS keys are ever configured, the standard AWS credential chain is used. Keep `JOB_TIMEOUT_SECONDS` equal to the Terraform variable `job_timeout_seconds` (the queue's visibility timeout). Rate limits and the reaper are tuned with `PREDICT_RATE_LIMIT_PER_MINUTE`, `LOGIN_RATE_LIMIT_PER_MINUTE`, `JOB_TIMEOUT_SECONDS` and `REAPER_INTERVAL_SECONDS`. In AWS the containers use IAM roles and temporary credentials. Production adds `ENVIRONMENT=production` (anything but local requires PostgreSQL and a SECRET_KEY), `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_SSLMODE` and `DB_PASSWORD` (or a `DATABASE_URL`), `RUN_MIGRATIONS` (the API container runs migrations unless this is `false`), `MIGRATION_WAIT_SECONDS`, `CORS_ORIGINS` (a JSON list such as `["https://your-project.vercel.app"]`) and `TRUSTED_PROXY_HOPS`. Terraform sets all of them. `DB_PASSWORD` and `SECRET_KEY` reach the worker as references to SSM parameters; the API on Lambda cannot reach Parameter Store from the private subnets, so it receives the same values as encrypted Lambda environment variables, readable by anyone allowed `lambda:GetFunction*` ([ADR 0007](ADR/0007-lambda-api-and-amplify-frontend.md)). On Lambda, `PORT`, `AWS_LWA_READINESS_CHECK_PATH` and `AWS_LWA_ASYNC_INIT` configure the Lambda Web Adapter, and Lambda sets `AWS_REGION` itself. Outside `local`, SQLite is refused.

## 5. CI/CD
**CI** (`.github/workflows/ci.yml`, every pull request and push to `main`): backend lint, format, types and tests on SQLite; the same tests against a PostgreSQL 16 service container; the Docker image is built, imported, run as a non-root user, checked to refuse SQLite in production and to answer `/health`; frontend lint, type check and build; Terraform `fmt`, `init -backend=false` and `validate`; `actionlint` on every workflow.

**Deploy** (`.github/workflows/deploy.yml`, push to `main` or by hand): runs only when the repository variable `DEPLOY_ENABLED` is `true` and, if you added reviewers, after approval of the `production` environment. It assumes the deploy role through GitHub OIDC (no AWS keys anywhere), builds the image (without a provenance attestation, which Lambda would reject), smoke-tests it, pushes the commit-SHA tag and `latest` to ECR, points the Lambda function at the commit-SHA image and waits for the update, forces a new ECS deployment of the worker, waits for it to be stable, and finally requests `/health` on the Function URL. It narrows the output of every Lambda call that returns the function's configuration, which includes the secret environment variables. The frontend is not part of this workflow: Amplify builds it from the repository by itself. Not yet run.

Not done: dependency and image vulnerability gates (ECR scans on push, but the result does not block a deploy), ML-specific CI tests beyond the existing suite, and running Terraform from the pipeline (infrastructure changes are applied by a person).

## 6. Release and rollback
Model versions are immutable; rollback of a model means pointing consumers at a previous approved version. Application rollback: every deploy also pushes an image tagged with the commit SHA. Re-run the deploy workflow from the earlier commit, or point the function back by hand (`aws lambda update-function-code --function-name <name> --image-uri <repo>:<previous-sha> --query LastUpdateStatus`) and force a new worker deployment. Database migrations are forward-only; a rollback to code older than the current schema is safe only if that code tolerates the newer schema (the first migration is the only one so far).

## 7. Health checks
`GET /health` for liveness, used by the Lambda Web Adapter's readiness check when an instance starts and by the deploy workflow's smoke test. It does not check the database. Readiness checks (database, storage reachability) are **Open**.

## 8. Cost-control plan
- Build and test locally first; use small public/sample datasets and enforce upload/training limits.
- No GPU instances. No NAT gateway (the network is designed around its absence). One small single-AZ database. The worker defaults to **zero** tasks.
- An AWS Budget emails at 80 % and 100 % of actual and 100 % of forecast spend against 10 USD a month (they are alerts, **not** a hard cap).
- S3 lifecycle rules clean up abandoned multipart uploads; ECR keeps 20 images; worker and API logs are kept 14 days.
- Stop or tear down when idle (see "Cost and how to stop it" and "Teardown" above). After `terraform destroy`, confirm what remains.
- Test workflows must not create long-lived AWS resources: tests use mocks, and CI never has AWS credentials.

## 9. Open questions
- Free Tier / Free Plan eligibility of the actual account, and the real monthly cost of the running stack.
- Whether the Lambda Function URL appends exactly one `X-Forwarded-For` entry (the sign-in limiter assumes it; ADR 0006 § 9, ADR 0007).
- Whether Amplify Hosting builds and serves this Next.js 16 app correctly (Amplify documents versions 12 to 15).
- Cold-start time of the API on Lambda (imports and the migration check run on every new instance).
- Where the Terraform state lives: it contains the generated database password and signing key, so use an encrypted, access-controlled remote backend (never commit state).
- A scripted way to create the first user inside the VPC.
- Readiness checks, CloudWatch alarms and dashboards.
