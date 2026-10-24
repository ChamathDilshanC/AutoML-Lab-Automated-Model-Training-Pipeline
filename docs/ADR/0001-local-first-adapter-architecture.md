# ADR 0001 — Local-first, adapter-based architecture

- **Status:** Accepted (owner-stated principle in the original architecture brief); not yet implemented
- **Date:** 2026-10-24

## Context
The project must be inexpensive to develop, testable, and able to run on AWS later. AWS Free Tier / Free Plan eligibility and limits can change, and cost cannot be guaranteed to be $0. Some AWS services (for example Lambda) have limits that may not suit model training.

## Decision
1. Develop and validate the full workflow locally first (Next.js, FastAPI, SQLite, local worker, local artifacts, Docker Compose).
2. Keep the ML engine (`backend/automl/`) independent of AWS and of the web framework.
3. Access storage, job orchestration and monitoring through adapters: local implementations for development and cloud implementations (S3, queue/orchestration, CloudWatch) for deployment.
4. Choose cloud runtimes only after measuring memory, duration, package size and cost.

## Consequences
- **Positive:** fast offline tests, no cloud dependency to develop, portable core, lower cost risk.
- **Negative:** adapter interfaces must be designed and maintained; behaviour differences between local and cloud adapters need integration testing (milestone M6).

## Related
[Architecture § 4](../ARCHITECTURE.md#4-core-architectural-principle) · [Deployment](../DEPLOYMENT.md)
