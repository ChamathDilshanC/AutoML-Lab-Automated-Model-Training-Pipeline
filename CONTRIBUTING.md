# Contributing to AutoML Lab

Thanks for your interest. The project is at the **M1 scaffold** stage: only the health endpoint and a UI shell exist. The most useful contributions today are review of the documents in [docs/](docs/README.md) and work on the next milestones in the [roadmap](docs/ROADMAP.md).

Sole listed maintainer: **ChamathDilshanC** ([@ChamathDilshanC](https://github.com/ChamathDilshanC)). See [CONTRIBUTORS.md](CONTRIBUTORS.md).

Coding agents must also follow [AGENTS.md](AGENTS.md).

## 1. Setup and prerequisites
Python 3.11+ and Node 20.9+ (developed with Node 24). Install and run commands are in [AGENTS.md § 5](AGENTS.md#5-commands) and the [README](README.md). The planned stack is Python (FastAPI, scikit-learn), Next.js, and optional AWS services. Do not add commands to docs that you have not run.

## 2. Workflow
1. Open or find an issue describing the change.
2. Branch from `main`: `docs/<topic>`, `feat/<topic>` or `fix/<topic>`.
3. Make focused changes; stage explicit paths.
4. Commit with a conventional prefix (`docs:`, `feat:`, `fix:`, `test:`, `chore:`).
5. Push your branch and open a pull request into `main`.
6. Address review comments; the maintainer merges.

## 3. Code style
Backend: Ruff (lint and format) and mypy. Frontend: ESLint and TypeScript. Typed, small, readable modules; the ML engine in `backend/automl/` must stay free of AWS and web-framework imports.

## 4. Testing requirements
New behaviour needs tests, using deterministic fixtures and fixed seeds. ML changes must keep the no-leakage and reproducibility tests passing. See [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md).

## 5. Pull request checklist
- [ ] Linked issue or requirement ID (for example `FR-021`)
- [ ] Tests added/updated and passing (state which you ran)
- [ ] Docs updated (PRD, API spec, schema, design system as relevant)
- [ ] No secrets, `.env` files, real datasets or Terraform state in the diff
- [ ] No change that creates AWS resources or cost without prior agreement
- [ ] Scope limited to the described change

## 6. Reporting issues
Open an issue with: what you expected, what happened, steps to reproduce, and environment. Do not paste secrets or private data. For security problems, follow [docs/SECURITY.md § 10](docs/SECURITY.md#10-reporting-a-vulnerability) instead of opening a public issue.

## 7. Documentation and changelog
Keep status labels (Implemented / Proposed / Assumption / Open) accurate. A changelog format will be chosen with the first release (**TBD**).

## 8. Sensitive data
Never commit credentials, tokens, personal data or proprietary datasets. Use small public or synthetic data for fixtures.
