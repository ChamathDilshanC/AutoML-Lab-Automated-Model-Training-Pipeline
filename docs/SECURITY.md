# Security

> **Status:** **Proposed** security design for a system that does not exist yet. These are requirements the implementation must meet, not descriptions of implemented controls.

Related: [Architecture](ARCHITECTURE.md) · [API spec](API_SPEC.md) · [PRD NFRs](PRD.md#10-non-functional-requirements) · [ADR 0002](ADR/0002-trusted-joblib-artifacts.md)

## 1. Assets and trust boundaries
| Asset | Why it matters |
|---|---|
| User datasets | May contain sensitive data; always treated as untrusted input *and* confidential |
| Model artifacts (`.joblib`) | Deserialising them can execute code |
| Credentials (AWS, auth tokens) | Full account or user compromise |
| Metadata and audit records | Integrity of ownership and provenance |

Trust boundaries: browser ↔ API · API ↔ storage · API ↔ worker · worker ↔ artifact store · prediction client ↔ API.

## 2. Threats and controls
| Threat | Control |
|---|---|
| Malformed or oversized CSV (parser abuse, resource exhaustion) | Allowlisted type, real-size check on the stored object, row/column limits, parsing timeouts, never trust declared size |
| CSV/formula injection when data or reports are exported | Escape cells starting with `=`, `+`, `-`, `@` in any CSV/spreadsheet export |
| Path or key tampering | Server generates storage keys from IDs; filenames sanitised and used for display only |
| Unauthorised access to another user's data (IDOR) | Ownership check on every dataset/experiment/model route; foreign IDs return `404` |
| Malicious model artifact | Load only artifacts written by trusted pipeline code; restrict write access to model storage; pin dependencies; never accept uploaded models |
| Code execution through configuration | Algorithm allowlist; no dynamic import from user input or dataset content |
| Presigned URL abuse | Short expiry, single object key, method-scoped, issued only after authorisation and validation |
| Credential leakage | No keys in code, frontend, or git; IAM roles/temporary credentials in AWS; secret scanning in CI |
| Excessive prediction traffic | Request-size and batch limits, rate limiting, authentication before public exposure |
| Information disclosure through errors/logs | Generic error messages with request IDs; logs exclude secrets, tokens and raw records |
| Supply-chain issues | Lockfiles, dependency and container scanning in CI |
| Privilege creep in CI/CD | GitHub OIDC with a narrowly scoped IAM role instead of long-lived keys, where supported |

## 3. Authentication and authorisation
- **Implemented (M7):** local accounts, scrypt password hashes and JWT bearer tokens ([ADR 0004](ADR/0004-local-accounts-and-bearer-tokens.md)). Details and limits are in § 15.
- Ownership checks are enforced in the repositories (every lookup filters by the caller's user ID) behind a router-level authentication dependency.
- The identity provider for a cloud deployment is **Open** (cost and eligibility to be checked before selecting any AWS-managed option). Prediction credentials are the same user tokens; a separate API-key scheme for machine clients is **Open**.

## 4. Storage security
Private buckets with Block Public Access; encryption at rest; TLS only; prefix-scoped permissions; lifecycle expiration of temporary uploads and old artifacts; no secrets or sensitive data in object names.

## 5. IAM (cloud mode, Proposed)
Separate roles per runtime: **API**, **worker**, **deployment automation**. Each is limited to the S3 actions and prefixes it needs (for example the API cannot write `models/`, only the worker can). Role details are defined when infrastructure code is written.

## 6. API hardening
Input validation on every route, request size limits, secure CORS (explicit origins), rate limiting, safe error responses, security headers on the frontend.

## 7. Logging and privacy
Structured logs with request IDs. Never log secrets, access tokens or dataset rows. Define data retention and deletion; deleting a dataset removes its source file and derived artifacts subject to documented rules.

## 8. Secret handling
Local: untracked `.env`; commit only `.env.example` with variable names. `.gitignore` already excludes `.env` files, keys and Terraform state. Never paste secret values into issues, PRs or docs.

## 9. Security testing
Upload-abuse cases, unauthorised-object-access tests, dependency scanning and secret scanning, as listed in [TESTING_STRATEGY.md](TESTING_STRATEGY.md).

## 10. Reporting a vulnerability
Private reporting channel **TBD** (recommend enabling GitHub private vulnerability reporting once the repository is public). Until then contact the maintainer, [ChamathDilshanC](https://github.com/ChamathDilshanC), directly rather than opening a public issue.

## 11. Open questions
Auth provider; API credential model; rate-limit values; retention windows; whether to add a malware scan on uploads.

## 12. Implemented so far (M2)
- Client filenames are sanitised for display only; storage keys are built from server-generated IDs.
- The local storage adapter rejects keys that resolve outside its root, writes through a temporary file, and removes partial files when the size cap is hit.
- Upload size is capped at write time (`MAX_UPLOAD_BYTES`) and, when `Content-Length` is declared, refused up front. A chunked upload without `Content-Length` is still parsed before the cap applies; a stricter limit would need a streaming parser or a reverse proxy.
- Errors use one envelope with a request ID, never include stack traces, paths or cell values, and validation details name fields only.
- Dataset reads are scoped to the owner and return `404` for foreign IDs. The owner is a fixed placeholder until authentication exists (M7), so this is not yet real access control.
- Not implemented at that point: authentication, rate limiting, retention and deletion (added in M7, § 15) and malware scanning (still open).

## 13. Implemented so far (M4)
- Experiment configuration is validated against the stored schema and the algorithm allowlist; algorithm names are looked up in a table and never imported or evaluated.
- Training runs in a separate worker process, never in a request. The worker records fixed, generic messages for unexpected failures and failed algorithms, because library error text can quote data; the full error goes to the worker log only.
- Experiment reads are owner-scoped and return `404` for other owners' IDs (the owner is still a placeholder until M7).
- `Idempotency-Key` prevents duplicate queued jobs from double submits. It is not a security control.
- **Not implemented:** per-job CPU, memory or wall-clock limits. `JOB_TIMEOUT_SECONDS` only marks a `RUNNING` job `FAILED` after the fact; it cannot stop a training call that is stuck. A malicious or huge dataset can therefore still tie up the worker within the upload limits. Real limits need process isolation (for example a subprocess per job with resource limits), which is open work.

## 14. Implemented so far (M5)
- Artifacts are written only by the worker through `register_model`. Each has a SHA-256 stored in the database that is checked before every `joblib.load`; a mismatch or a missing file returns a generic error and nothing is deserialised ([ADR 0002](ADR/0002-trusted-joblib-artifacts.md)). Tests prove that a tampered artifact never reaches `joblib.load` and that, across repeated predictions with hostile-looking strings, `joblib.load` runs once and only on the artifact.
- Prediction input is JSON checked field by field (exact field set, types, string length, finite numbers, batch size). Error details name fields and rows, never values.
- A model must be explicitly approved (`{"confirm": true}`) before it serves predictions. Approval cannot be undone yet.
- A model trained with another scikit-learn version is refused rather than loaded.
- Which version answered each request is logged with the request ID and row count, never the input values.
- The model's feature schema lists the string values seen in training for columns with at most 50 distinct values, so the form can offer them. That is the owner's own data, shown only to the owner, but it means a categorical column's values are exposed through `GET /api/v1/models`. Columns with more distinct values list none.
- **Not implemented at that point:** authentication, rate limiting on `/predict`, revoking approval and removing a deleted dataset's models (all added in M7, § 15). Still open: a prediction-specific request-size limit (the general upload body limit applies) and deleting a single model.

## 15. Implemented so far (M7)
**Accounts and passwords.** No public sign-up; an operator creates accounts with `python -m app.cli create-user`. Passwords are 12 to 128 characters, hashed with scrypt and a per-user salt, and compared in constant time. An unknown username costs the same work as a wrong password and gets the same answer, so sign-in does not reveal which usernames exist.

**Tokens.** HS256 JWTs signed with `SECRET_KEY` (at least 32 characters, mandatory unless `ENVIRONMENT` is `local`; the app refuses to start without it elsewhere). The algorithm is pinned, `exp`, `iat` and `sub` are required, tokens last 60 minutes, and the user is loaded on every request so a disabled or deleted account loses access immediately. Tests forge expired, wrong-key, `alg: none`, wrong-algorithm, claim-less and tampered tokens; all are rejected.

**Every route is protected, and a test proves it.** All `/api/v1` routes except sign-in sit behind one router-level dependency, and a test walks the OpenAPI document and calls each one without a token (14 operations today). Breaking the protection of one router was confirmed to fail that test.

**Ownership (IDOR).** Repositories filter by the caller's user ID. For every route, another user's ID returns the same `404`, with the same body and headers apart from the request ID, as an ID that does not exist. Tests cover all ten ways of touching a dataset, experiment or model by ID, and that failed attempts change nothing.

**Abuse limits.** Sign-in: 10 attempts per minute per client address. Predictions: 60 per minute per user. Both are in-memory token buckets (`429` with `Retry-After`), checked before the request body is processed. Because the buckets live in one process, several API processes multiply the limits, and behind a reverse proxy all clients appear to share its address (forwarded headers are not trusted).

**Deletion and revocation.** Deleting a dataset removes its experiments, runs, models and files, refuses while an experiment is running, and evicts cached pipelines. Revoking is immediate and permanent, because approval is read from the database on every prediction. Both, and approval, are written to `audit_events` together with sign-ins and account creation.

**Headers.** Every response carries `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`; API responses are `Cache-Control: no-store`. CORS allows only the configured origins, the methods `GET`, `POST` and `DELETE`, and the headers `Content-Type`, `Authorization` and `Idempotency-Key`.

**Abandoned jobs.** A `RUNNING` experiment older than `JOB_TIMEOUT_SECONDS` (default 30 minutes) is marked `FAILED`. The API runs this check in the background every `REAPER_INTERVAL_SECONDS` (default 60) and the worker runs it on every poll, so it works even if the worker has died. Finishing is conditional on the experiment still being `RUNNING`, so a worker that finishes late cannot overwrite the reaper's verdict, and it skips saving a model in that case.

**Browser.** The token is kept in `sessionStorage` (cleared when the tab closes). A `401` from any call clears it and sends the user to `/login`. The `next` redirect is restricted to paths on this site.

**Known gaps (not implemented).**
- No server-side logout or token revocation: a stolen token works until it expires. Disabling the user is the emergency stop.
- `sessionStorage` is readable by any script on the page, so an XSS bug would expose the token. A httpOnly cookie plus CSRF protection would be stronger.
- No password reset or change, MFA, or account lockout (only the sign-in rate limit).
- No TLS: it must be terminated by whatever hosts the app. `SECRET_KEY`, user accounts and the database file are the operator's to protect.
- The reaper marks a stuck job `FAILED` but cannot stop the training call itself, so a stuck job can still occupy the worker. Per-job CPU, memory and wall-clock limits need process isolation.
- Audit events are write-only: nothing reads them, there is no retention policy, and a sign-in failure stores the attempted username.
- Deleting a dataset removes files after the database commit; a failure there leaves unreachable files rather than failing the request.
- Single models cannot be deleted on their own; deleting the dataset removes them.

## 16. Implemented so far (M6, cloud mode)
Everything below applies only with `STORAGE_MODE=s3` or `JOB_MODE=sqs`; local mode is unchanged. None of it has run against a real AWS account (see [ADR 0005](ADR/0005-s3-storage-and-sqs-job-queue.md)).

- **No AWS credentials in the code, the frontend or the repository.** The backend uses the standard AWS credential chain; Terraform creates IAM policies only, never users or access keys.
- **Direct uploads without handing out credentials.** The browser receives a presigned `PUT` URL valid for 300 seconds, for one key, with the content type and exact length signed. The bearer token is never sent to it (checked in a real browser). The declared size is capped before a URL is issued, and validation independently re-checks the stored size and deletes a mismatching object.
- **Least privilege per runtime.** The API can send job messages but not receive them; the worker can receive and delete them but not send; the worker can only read datasets, and write and delete models. No wildcard action or resource. A test records every AWS call of a full run and fails if one is not granted, or if a policy grants more than the code can use.
- **Bucket and queue.** Block Public Access, owner-enforced ownership, encryption at rest, TLS-only policies, CORS limited to the configured origin and to `PUT`, `GET`, `HEAD` and `Content-Type`. Versioning is off, so deletion is real.
- **Queue messages are untrusted hints.** A message holds only an experiment ID, strictly shape-checked; the configuration comes from the database, so a forged message cannot change what runs. A message for an unknown, running or finished experiment is dropped. Bad messages are deleted, not retried. If the database fails, the message is kept and later dead-lettered.
- **Provider errors never leak.** Storage failures are reported with fixed messages (they can contain bucket and key names); queue failures return a generic `503`.
- **Prefix deletion cannot over-reach.** Deleting `models/md_1` does not touch `models/md_10`, because the prefix always ends in a slash (tested).

**Not verified or not done**
- Real S3 enforcement of the signed `Content-Length`, real CORS behaviour, IAM evaluation, and `terraform apply` have not been exercised.
- The sign-in and prediction rate limits are still in memory per process.
- Unvalidated uploads (a registered dataset whose file never arrives) leave a database row until the user deletes it; there is no expiry job.
- No bucket versioning, replication, access logging, or CloudTrail data events; no CloudWatch alarms.
- The IAM policies do not restrict by source IP or VPC endpoint.
