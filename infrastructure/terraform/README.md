# AWS infrastructure for AutoML Lab (Terraform)

Creates the AWS resources for **cloud mode** (`STORAGE_MODE=s3`, `JOB_MODE=sqs`; see
[ADR 0005](../../docs/ADR/0005-s3-storage-and-sqs-job-queue.md)):

| Resource | Purpose |
|---|---|
| S3 bucket | Private store for uploaded datasets (`datasets/…`) and trained models (`models/…`). Public access blocked, SSE-S3 encryption, TLS-only policy, CORS for your frontend origin, incomplete multipart uploads cleaned up after a day |
| SQS standard queue + dead-letter queue | Hands experiments to the worker. Long polling, encryption, redrive to the dead-letter queue after 3 deliveries |
| Three IAM **policies** | `api`, `worker` and `local-dev` (both together). Policies only: **no IAM user and no access key is created**, because keys in Terraform state are secrets |

Nothing here is created by running the application or its tests. Local mode (the default) needs no
AWS account at all.

> **Cost.** These resources are billed per use and may or may not be covered by your account's free
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
cp terraform.tfvars.example terraform.tfvars   # optional: change region or allowed origins
terraform init
terraform plan -out=tfplan     # read it: it should only add resources
terraform apply tfplan
```
Commit the `.terraform.lock.hcl` file that `init` creates, so everyone uses the same provider
version. Do not commit `terraform.tfvars`, `tfplan` or any `*.tfstate` file (already git-ignored).

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
(`.github/workflows/ci.yml`). `backend/tests/test_terraform.py` also checks the security-relevant
settings (public access blocked, encryption, no wildcard permissions) and
`backend/tests/test_aws.py` checks that the IAM policies match the calls the code actually makes.
Neither creates any AWS resource.
