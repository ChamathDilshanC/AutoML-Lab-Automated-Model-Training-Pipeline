# ADR 0005 — S3 storage, presigned uploads and an SQS job queue

- **Status:** Accepted (implemented in M6). Never run against a real AWS account: see "What is verified".
- **Date:** 2026-10-24

## Context
M6 adds cloud mode next to the local mode ([ADR 0001](0001-local-first-adapter-architecture.md)). Local authentication stays ([ADR 0004](0004-local-accounts-and-bearer-tokens.md)): the backend owns identity, holds the AWS permissions, and hands the browser only short-lived, single-purpose URLs. Infrastructure is code (Terraform) so the setup is reviewable and repeatable.

## Decisions

### 1. Two switches, local by default
`STORAGE_MODE=local|s3` and `JOB_MODE=db|sqs` are independent. The defaults need no AWS account, so development and the test suite never touch AWS. Both are chosen when the process starts; a bad combination (for example `s3` without `S3_BUCKET`) stops the start-up with a clear error.

### 2. One upload flow for both modes: register, upload, validate
`POST /api/v1/datasets` takes only metadata (`filename`, `size_bytes`) and returns an **upload target**. The browser sends the bytes there, then calls `validate`. In S3 mode the target is a presigned URL, so the file never passes through the API. In local mode it is `PUT /api/v1/datasets/{id}/content` on the API. The frontend has a single code path.

The presigned `PUT` is limited as tightly as the method allows:
- it is valid for 300 seconds (`S3_PRESIGN_EXPIRES_SECONDS`) and for one key;
- `Content-Type` **and exact `Content-Length`** are part of the signature, so S3 itself rejects a different type or size. The declared size is checked against `MAX_UPLOAD_BYTES` before any URL is issued. (A presigned `POST` could express a size *range* instead, but the exact size is known up front and is stricter.)
- validation re-checks the stored object's size and deletes a mismatching one, so the limit does not depend on one mechanism;
- URLs use regional virtual-hosted addressing. With the global endpoint S3 answers a PUT to a bucket in another region with a redirect that a browser cannot follow.

The bearer token is sent to this API only, never to a presigned URL.

### 3. A standard SQS queue (not FIFO), with a dead-letter queue
The brief allowed either. A **standard** queue fits because:
- delivery is at-least-once, and that is safe here: the message carries only the experiment ID and the worker's claim is a conditional database update, so a duplicate or redelivered message finds the experiment already running or finished and is dropped;
- FIFO's strengths, ordering and de-duplication, are not needed (jobs are independent). Giving each job its own message group would remove the ordering anyway, and one shared group would force jobs to run one at a time;
- FIFO also has lower throughput limits and a slightly higher price.

The queue uses long polling (20 s), SSE, and a visibility timeout equal to `JOB_TIMEOUT_SECONDS` so a job that is still running is not handed to a second worker. After three deliveries a message moves to a dead-letter queue (14 days of retention).

### 4. Message handling rules (`worker/jobs.py: process_message`)
The database is the source of truth; the message is a hint. The worker deletes a message explicitly, and only when it has been dealt with:

| Outcome | Meaning | Message |
|---|---|---|
| `done` | claimed, run, result recorded (success or failure) | deleted |
| `skipped` | not claimable: already running, finished, reaped or deleted | deleted |
| `discarded` | not one of our messages (bad JSON, wrong ID shape) | deleted |
| `retry` | the database failed before anything was claimed | **kept**, redelivered after the visibility timeout, dead-lettered if it keeps failing |

The API hands a job to the queue after committing the experiment. If sending fails, the experiment is deleted again and the request returns `503` with `Retry-After`, because otherwise it would sit `QUEUED` forever. The idempotency key is freed, so repeating the request works. A replayed request with the same key sends no second message.

### 5. IAM: one policy per runtime, scoped to prefixes, no wildcards
The brief asked for a policy with only `s3:PutObject`, `s3:GetObject` and the three SQS actions. That is not enough for what the application actually does, and least privilege means exactly what the code uses, so the policies are:

| Runtime | S3 | SQS |
|---|---|---|
| API | `GetObject`, `PutObject`, `DeleteObject`, `AbortMultipartUpload` on `datasets/*` and `models/*`; `ListBucket` limited to those prefixes | `SendMessage` |
| Worker | `GetObject` on `datasets/*`; `PutObject`, `DeleteObject`, `AbortMultipartUpload` on `models/*` | `ReceiveMessage`, `DeleteMessage` |

Why the extras: deleting a dataset needs `DeleteObject` and `ListBucket` (to find the objects under a folder); the API needs `PutObject` because a presigned upload is authorised as the identity that signed it; large uploads use multipart, which needs `AbortMultipartUpload`; and `HeadObject` is covered by `GetObject`. A third policy, `local-dev`, merges the two for one machine running both. A test records every AWS call made by a full cloud run and fails if a call is not covered by these lists or if a list grants more than the code can use.

No IAM user or access key is created by Terraform: keys in Terraform state are secrets. The application finds credentials through the standard AWS chain.

### 6. Bucket and queue hardening
Block Public Access, owner-enforced ownership, SSE-S3 encryption, a TLS-only policy on the bucket and on the queue, CORS limited to the configured origin(s) with `PUT`, `GET`, `HEAD` and the `Content-Type` header, and cleanup of incomplete multipart uploads after a day. Versioning is **off**: deleting a dataset should really delete it.

## What is verified
- The storage adapter, presigning, the queue and worker rules, and the IAM-to-code match are tested against `moto`, an in-process AWS mock.
- A real browser ran the whole flow against a local `moto` HTTP server: direct upload with CORS and no bearer token sent to storage, SQS pick-up, a model loaded from the bucket, cleanup after a failed upload, and an empty bucket after deletion.
- The Terraform is parsed and checked by tests, and `terraform fmt`, `init` and `validate` run in CI.
- **Not verified against real AWS:** `terraform apply`, whether real S3 enforces the signed `Content-Length` (documented behaviour of SigV4, but `moto` does not check signatures), real CORS preflight behaviour, IAM evaluation, and cost. The first real deployment should be treated as a test of all of these.

## Consequences
- **Positive:** the browser never sees AWS credentials; the app and worker scale independently; the code path is identical locally and in the cloud; permissions are reviewable and test-checked.
- **Negative:** two code paths for the byte transfer (API or S3) to keep in step; at-least-once delivery means the claim logic must stay idempotent; rate limits and reaping are still per process; no versioning means an accidental delete is not recoverable.
- **Open:** where the API and worker run (compute service), the cloud identity provider, CloudWatch dashboards and alarms, EventBridge, and a cost budget. Those belong to M8.

## Related
[Architecture § 6.4 and § 6.6](../ARCHITECTURE.md) · [Security § 16](../SECURITY.md) · [Deployment](../DEPLOYMENT.md) · [Terraform README](../../infrastructure/terraform/README.md)
