# AutoML Lab — Automated Model Training Pipeline

Automated model training, evaluation, model selection and inference for tabular CSV datasets.

Upload a CSV, choose a target column and task (classification or regression), and run a reproducible pipeline that validates the data, trains a set of candidate scikit-learn models, ranks them by your chosen metric, and stores the winning model as a versioned artifact with a prediction API.

**Planned stack:** Next.js, Python, FastAPI, scikit-learn, with optional Amazon S3, AWS Lambda, Amazon EventBridge, Amazon CloudWatch and IAM. The project is local-first: AWS is used only where account eligibility and limits allow, and zero cost is not guaranteed.

## Status
Planning phase. The repository currently contains documentation only; no application code has been written yet.

## Documentation
Start at the [documentation index](docs/README.md):
[PRD](docs/PRD.md) · [Architecture](docs/ARCHITECTURE.md) · [Design system](docs/DESIGN_SYSTEM.md) · [Roadmap](docs/ROADMAP.md) · [Security](docs/SECURITY.md)

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) · Agent guide: [AGENTS.md](AGENTS.md) · Maintainer: [@ChamathDilshanC](https://github.com/ChamathDilshanC)
