# AutoML Lab — Automated Model Training Pipeline

Automated model training, evaluation, model selection and inference for tabular CSV datasets.

Upload a CSV, choose a target column and task (classification or regression), and run a reproducible pipeline that validates the data, trains a set of candidate scikit-learn models, ranks them by your chosen metric, and stores the winning model as a versioned artifact with a prediction API.

**Planned stack:** Next.js, Python, FastAPI, scikit-learn, with optional Amazon S3, AWS Lambda, Amazon EventBridge, Amazon CloudWatch and IAM. The project is local-first: AWS is used only where account eligibility and limits allow, and zero cost is not guaranteed.

## Status
Milestones M1 to M5 are in place: upload a CSV, review its data-quality report, configure an experiment, watch a separate worker train the candidate models and rank them on a leaderboard, then approve the winning model and get predictions from it in the browser or over the API. Sign-in with per-user ownership, dataset deletion, model revocation and rate limiting (M7) are in place; hosting and deployment are not. Cloud mode (S3 with direct uploads and an SQS queue, defined in Terraform) is implemented but has never been run against a real AWS account; it is off by default. See the [roadmap](docs/ROADMAP.md) and [infrastructure/terraform/README.md](infrastructure/terraform/README.md).

## Quick start (local)
```bash
# Backend (Python 3.11+)
cd backend
pip install -e ".[dev]"
python -m app.cli create-user alice   # asks for a password (12+ characters); no public sign-up
uvicorn app.main:app --reload      # http://localhost:8000/health

# Worker (second terminal; runs queued experiments)
cd backend
python -m worker.main

# Frontend (Node 20.9+; developed with Node 24)
cd frontend
npm ci
npm run dev                        # http://localhost:3000
```
Copy `.env.example` to `.env` only if you need to override defaults; the variable names are listed there. Set `SECRET_KEY` (32+ random characters) to keep sign-ins across API restarts; it is required whenever `ENVIRONMENT` is not `local`. Then sign in at http://localhost:3000. `docker compose up` is also defined but has not been tested yet.

## Documentation
Start at the [documentation index](docs/README.md):
[PRD](docs/PRD.md) · [Architecture](docs/ARCHITECTURE.md) · [Design system](docs/DESIGN_SYSTEM.md) · [Roadmap](docs/ROADMAP.md) · [Security](docs/SECURITY.md)

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) · Agent guide: [AGENTS.md](AGENTS.md) · Maintainer: [@ChamathDilshanC](https://github.com/ChamathDilshanC)
