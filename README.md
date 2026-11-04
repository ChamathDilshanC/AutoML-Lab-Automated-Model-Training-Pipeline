# AutoML Lab — Automated Model Training Pipeline

Automated model training, evaluation, model selection and inference for tabular CSV datasets.

Upload a CSV, choose a target column and task (classification or regression), and run a reproducible pipeline that validates the data, trains a set of candidate scikit-learn models, ranks them by your chosen metric, and stores the winning model as a versioned artifact with a prediction API.

**Live:** frontend https://automl-lab-ui.vercel.app · API https://qr2bs6hofh2mxilfqoz5uk2f5i0janut.lambda-url.us-east-1.on.aws (`/health`). Sign-in is required and there is no public sign-up: an operator creates accounts. Details: [docs/DEPLOYMENT.md § Current deployment](docs/DEPLOYMENT.md#current-deployment).

## Demo video

[![Watch the demo on Google Drive](https://img.shields.io/badge/Watch_the_demo-Google_Drive-4285F4?style=for-the-badge&logo=googledrive&logoColor=white)](https://drive.google.com/file/d/1cF0IblAVNfv7WfIVx_Bkj4nipiHXnqfo/view?usp=drive_link)

A 73-second product tour with sound: an animated intro, then the real app from CSV upload to an approved model and a prediction. The scores in it come from a held-out test set on a small synthetic customer-churn dataset and are not a guarantee.

- Video file in the repository: [promo-video/final-with-intro.mp4](promo-video/final-with-intro.mp4)
- Animated title cards: [demo-video/06-intro-outro.html](demo-video/06-intro-outro.html) (download and open in a browser; press `1` to `4` to play a card)
- Scrolling product page used in the intro: [demo-video/07-landing-scroll-page.html](demo-video/07-landing-scroll-page.html) (download and open in a browser; the Auto-scroll button scrolls it)

## How it works

[![AutoML Lab AWS architecture: Next.js frontend on Vercel (Amplify optional), FastAPI on AWS Lambda behind a Function URL, RDS PostgreSQL, S3 and SQS, an ECS Fargate worker started and stopped by CloudWatch alarms and Application Auto Scaling, an operator creating users through a one-off ECS Exec task, and GitHub Actions deploying through OIDC, in a VPC in us-east-1](docs/architecture.png)](docs/architecture.svg)

*Click the diagram for the scalable SVG version.*

1. **Frontend.** The Next.js app runs on **Vercel**, which redeploys it on every push. (AWS Amplify Hosting is defined in Terraform as an option, off by default.)
2. **API.** The browser calls the **FastAPI** service, which runs as a container image on **AWS Lambda** (through the Lambda Web Adapter) behind a public HTTPS Function URL. The function sits in private subnets with no internet route; every `/api/v1` route needs a bearer token.
3. **Upload.** The API hands the browser a short-lived presigned URL and the CSV goes straight to a private **S3** bucket. The API then validates it and stores the data-quality report in **RDS PostgreSQL**.
4. **Run experiment.** The API records the experiment as `QUEUED` and puts its ID on an **SQS** queue (with a dead-letter queue).
5. **Worker.** Two **CloudWatch** alarms watch the queue. When there is work, **Application Auto Scaling** starts one **ECS Fargate** worker task. The worker trains the allowlisted scikit-learn models, saves the winner to S3 and the results to RDS. About 5 minutes after the queue is empty it is stopped again ([docs/WORKER_AUTOSCALING.md](docs/WORKER_AUTOSCALING.md)).
6. **Predict.** Approved models serve predictions through the API.
7. **Deploy.** GitHub Actions assumes an IAM role through **OIDC** (no stored AWS keys), pushes the image to **ECR** and rolls out the Lambda API and the worker.
8. **Accounts.** An operator creates users with `python -m app.cli create-user` inside a one-off ECS Exec task ([DEPLOYMENT.md, step 4](docs/DEPLOYMENT.md#apply-order-three-steps-because-the-services-need-an-image-that-does-not-exist-yet)).

Local mode needs none of the AWS parts: SQLite, a local folder for files, and a worker that polls the database.

## Tech stack
| Area | Technologies |
|---|---|
| **Frontend** | ![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white) ![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black) ![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white) ![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js-24-5FA04E?logo=nodedotjs&logoColor=white) |
| **Backend** | ![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white) ![Uvicorn](https://img.shields.io/badge/Uvicorn-2C3E50) ![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=pydantic&logoColor=white) ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white) ![Alembic](https://img.shields.io/badge/Alembic-6BA81E) ![PyJWT](https://img.shields.io/badge/PyJWT-000000?logo=jsonwebtokens&logoColor=white) ![boto3](https://img.shields.io/badge/boto3-232F3E) |
| **Machine learning** | ![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?logo=scikitlearn&logoColor=white) ![pandas](https://img.shields.io/badge/pandas-150458?logo=pandas&logoColor=white) ![joblib](https://img.shields.io/badge/joblib-4B5563) |
| **Database, storage, queue** | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white) ![Amazon RDS](https://img.shields.io/badge/Amazon_RDS-527FFF) ![Amazon S3](https://img.shields.io/badge/Amazon_S3-569A31) ![Amazon SQS](https://img.shields.io/badge/Amazon_SQS-FF4F8B) ![SQLite (local)](https://img.shields.io/badge/SQLite-local-003B57?logo=sqlite&logoColor=white) |
| **Infrastructure (AWS)** | ![AWS Lambda](https://img.shields.io/badge/AWS_Lambda-FF9900) ![ECS Fargate](https://img.shields.io/badge/ECS_Fargate-FF9900) ![Amazon ECR](https://img.shields.io/badge/Amazon_ECR-FF9900) ![Amazon VPC](https://img.shields.io/badge/Amazon_VPC-8C4FFF) ![IAM](https://img.shields.io/badge/IAM-DD344C) ![SSM Parameter Store](https://img.shields.io/badge/SSM_Parameter_Store-DD344C) ![CloudWatch](https://img.shields.io/badge/CloudWatch-E7157B) ![Application Auto Scaling](https://img.shields.io/badge/Application_Auto_Scaling-E7157B) ![AWS Budgets](https://img.shields.io/badge/AWS_Budgets-7AA116) |
| **Infrastructure as code, containers** | ![Terraform](https://img.shields.io/badge/Terraform-844FBA?logo=terraform&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white) |
| **CI/CD and hosting** | ![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=githubactions&logoColor=white) ![Vercel](https://img.shields.io/badge/Vercel-000000?logo=vercel&logoColor=white) |
| **Quality** | ![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white) ![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black) ![mypy](https://img.shields.io/badge/mypy-2A6DB2) ![moto](https://img.shields.io/badge/moto-AWS_mocks-232F3E) ![ESLint](https://img.shields.io/badge/ESLint-4B32C3?logo=eslint&logoColor=white) ![actionlint](https://img.shields.io/badge/actionlint-2088FF) |

### Technology icons

These icons use the [theSVG CDN](https://thesvg.org/docs), so they need no install, build step or JavaScript:

<p>
  <img src="https://thesvg.org/icons/nextjs/default.svg" width="32" height="32" alt="Next.js" />
  <img src="https://thesvg.org/icons/python/default.svg" width="32" height="32" alt="Python" />
  <img src="https://thesvg.org/icons/fastapi/default.svg" width="32" height="32" alt="FastAPI" />
  <img src="https://thesvg.org/icons/scikit-learn/default.svg" width="32" height="32" alt="scikit-learn" />
  <img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/aws-amazon-simple-storage-service/default.svg" width="32" height="32" alt="Amazon S3" />
  <img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/aws-aws-lambda/default.svg" width="32" height="32" alt="AWS Lambda" />
  <img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/aws-amazon-eventbridge/default.svg" width="32" height="32" alt="Amazon EventBridge" />
  <img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/aws-amazon-cloudwatch/default.svg" width="32" height="32" alt="Amazon CloudWatch" />
  <img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/aws-amazon-cognito/default.svg" width="32" height="32" alt="Amazon Cognito" />
</p>

## AWS components
- **Network:** one VPC (`10.20.0.0/16`) with two public and two private subnets across two availability zones, an internet gateway, **no NAT gateway**, an S3 gateway endpoint and an SQS interface endpoint.
- **API:** a Lambda function (container image, 2 GB) in the private subnets with the `api` security group, behind a public Function URL. The database password and the token-signing key reach it as encrypted environment variables ([ADR 0007](docs/ADR/0007-lambda-api-and-amplify-frontend.md)).
- **Worker:** an ECS Fargate service in the public subnets with a public IP (so no NAT gateway is needed) and no inbound traffic. It runs 0 or 1 task, driven by the queue ([ADR 0008](docs/ADR/0008-worker-autoscaling-from-the-queue.md)), and reads the two secrets from SSM Parameter Store when it starts.
- **Data:** RDS PostgreSQL (`db.t4g.micro`, encrypted, TLS required) in the private subnets, reachable only from the API and worker security groups. One private, encrypted S3 bucket for datasets and models. An SQS queue with a dead-letter queue for experiment jobs. One ECR repository (`automl-lab-backend`) for the image both the API and the worker run.
- **Frontend:** Vercel (root directory `frontend`, `NEXT_PUBLIC_API_BASE_URL` set to the Function URL). Amplify Hosting is optional (`enable_frontend`, default `false`, [ADR 0009](docs/ADR/0009-frontend-on-vercel.md)).
- **Switches:** the API and the worker exist only with `enable_compute = true`; worker autoscaling with `enable_worker_autoscaling` (default `true`); Amplify with `enable_frontend`.
- **Cost:** see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#cost-and-how-to-stop-it). The AWS Budget is an alert, not a cap.

The diagram is generated by [docs/architecture/generate_architecture.py](docs/architecture/generate_architecture.py) (`python docs/architecture/generate_architecture.py`, needs matplotlib; writes the PNG and the SVG). Edit the script when the Terraform changes.

## Status
Milestones M1 to M8 are implemented:

- **Product:** upload a CSV, review its data-quality report, configure an experiment, watch a separate worker train and rank the candidate models, then approve the winner and get predictions in the browser or over the API.
- **Security:** sign-in with per-user ownership, dataset deletion, model revocation and rate limiting (M7).
- **Cloud mode and deployment:** S3 direct uploads, the SQS queue (M6), and the AWS deployment (M8). They are applied to one AWS account: the API is live on Lambda and the frontend on Vercel.
- **Worker autoscaling:** on `main`, and takes effect with the next `terraform apply`.
- **Not yet verified on AWS:** an end-to-end training run on the AWS worker.

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
[PRD](docs/PRD.md) · [Architecture](docs/ARCHITECTURE.md) · [Deployment](docs/DEPLOYMENT.md) · [Worker autoscaling](docs/WORKER_AUTOSCALING.md) · [Security](docs/SECURITY.md) · [Design system](docs/DESIGN_SYSTEM.md) · [Roadmap](docs/ROADMAP.md) · [Infrastructure](infrastructure/terraform/README.md)

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) · Agent guide: [AGENTS.md](AGENTS.md) · Maintainer: [@ChamathDilshanC](https://github.com/ChamathDilshanC)
