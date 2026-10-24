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
- Use a maintained authentication solution; the specific provider is **Open** (cost and eligibility to be checked before selecting any AWS-managed option).
- Ownership checks are enforced in the service layer, not only the route layer.
- Prediction API credentials (user token vs API key) are **Open**.

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
