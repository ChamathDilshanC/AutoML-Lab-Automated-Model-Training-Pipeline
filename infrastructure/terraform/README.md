# AWS infrastructure for AutoML Lab (Terraform)

Two layers, both in this folder: the **cloud-mode resources** (M6: bucket, queue, IAM policies) and the **deployment resources** (M8: network, PostgreSQL, container registry, the API on Lambda, Fargate worker, Amplify frontend, GitHub deploy role, budget alert). The deployment layer has its own guide with the apply order, costs and teardown: **[docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md)**. Read it before `terraform apply`; the Lambda function and the ECS service are created only when `enable_compute = true`, after the first image has been pushed, and the Amplify app only when `enable_frontend = true`. It has been applied to one AWS account and the API is live on Lambda ([DEPLOYMENT.md § Current deployment](../../docs/DEPLOYMENT.md#current-deployment)).

## Cloud-mode resources (M6)

Creates the AWS resources for **cloud mode** (`STORAGE_MODE=s3`, `JOB_MODE=sqs`; see
[ADR 0005](../../docs/ADR/0005-s3-storage-and-sqs-job-queue.md)):

| Resource | Purpose |
|---|---|
| S3 bucket | Private store for uploaded datasets (`datasets/…`) and trained models (`models/…`). Public access blocked, SSE-S3 encryption, TLS-only policy, CORS for your frontend origin, incomplete multipart uploads cleaned up after a day |
| SQS standard queue + dead-letter queue | Hands experiments to the worker. Long polling, encryption, redrive to the dead-letter queue after 3 deliveries |
| Three IAM **policies** | `api`, `worker` and `local-dev` (both together). Policies only: **no IAM user and no access key is created**, because keys in Terraform state are secrets |

| *(M8)* VPC, RDS, ECR, Lambda, ECS, Amplify, OIDC role, budget | See [docs/DEPLOYMENT.md § 3](../../docs/DEPLOYMENT.md) for the file-by-file list |

Nothing here is created by running the application or its tests. Local mode (the default) needs no
AWS account at all.

> **Cost.** The M8 resources (database, the SQS endpoint, a running worker) are billed by the hour and are likely to exceed 10 USD a month if left on; the worker is off by default. The Lambda API and Amplify are billed per use. See [DEPLOYMENT.md](../../docs/DEPLOYMENT.md#cost-and-how-to-stop-it). These resources are billed per use and may or may not be covered by your account's free
> tier or free plan. Check the current AWS pricing and your account's terms first, set an AWS
> Budget alert, and destroy the stack when you are done. Alerts are not a spending cap.

## Prerequisites
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.6 or newer.
- AWS credentials for an identity allowed to create these resources, configured through the
  standard AWS chain, for example `aws configure sso` then `aws sso login`, or `aws configure`.
  Never put keys in `.tf` or `.tfvars` files.

## Create
```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars   # set github_repository and budget_alert_email (required)
terraform init
terraform plan -out=tfplan     # read it: it should only add resources
terraform apply tfplan
```
`init` creates `.terraform.lock.hcl`, which pins provider versions; it is not committed yet (CI resolves the newest allowed versions). Do not commit `terraform.tfvars`, `tfplan` or any `*.tfstate` file (already git-ignored).

**The state holds secrets.** Terraform generates the database password and the token-signing key, so both are in the state file. Keep state in an encrypted, access-controlled remote backend (for example a private, versioned, encrypted S3 bucket) rather than on a shared disk; this repository does not configure a backend.

The bucket name defaults to `automl-lab-<account id>-<region>`. Set `bucket_name` to choose your
own (3 to 63 lower-case letters, digits and hyphens).

## Give the application an identity
The app and the worker use the standard AWS credential chain; nothing is configured in the code.
For local development, attach the combined policy to a user or role you manage:

```bash
POLICY_ARN=$(terraform output -raw local_dev_policy_arn)
aws iam attach-user-policy --user-name <your-dev-user> --policy-arn "$POLICY_ARN"
aws sso login            # or export that user's credentials in your shell; do not commit them
```
In a real deployment give the API runtime `api_policy_arn` and the worker runtime
`worker_policy_arn` as separate roles.

## Point the application at it
```bash
terraform output -raw backend_environment   # paste the lines into backend/.env
```
That sets `STORAGE_MODE=s3`, `JOB_MODE=sqs`, `AWS_REGION`, `S3_BUCKET` and `SQS_QUEUE_URL`. Then
start the API and the worker as usual (see the repository README). Keep `JOB_TIMEOUT_SECONDS` in
the backend equal to `job_timeout_seconds` here (default 1800); it is the queue's visibility
timeout.

If your frontend is not at `http://localhost:3000`, set `allowed_origins` so the browser may upload
to the bucket, and set `CORS_ORIGINS` in the backend to the same origin.

## Destroy
```bash
# The bucket must be empty. Delete your datasets in the app first, or for a throwaway stack:
terraform apply -var force_destroy=true     # lets destroy remove a non-empty bucket
terraform destroy
```
After `destroy`, check the S3 and SQS consoles to confirm nothing remains, and delete any IAM user
or credentials you created by hand.

## Checks
`terraform fmt -check`, `terraform init -backend=false` and `terraform validate` run in CI
(`.github/workflows/ci.yml`). `backend/tests/test_terraform.py` and `test_terraform_deployment.py`
check the security-relevant settings (public access blocked, encryption, private database,
database reachable only from the API and the worker, no NAT, exact OIDC trust, deploy role
scope, budget, compute off by default, no wildcard permissions) and
`backend/tests/test_aws.py` checks that the IAM policies match the calls the code actually makes.
None creates any AWS resource.
