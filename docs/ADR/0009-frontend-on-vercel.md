# ADR 0009 — The frontend stays on Vercel; Amplify Hosting is optional

- **Status:** Accepted. Records the deployed state and supersedes the framing of [ADR 0007](0007-lambda-api-and-amplify-frontend.md) § 5, which introduced Amplify Hosting with Vercel as the alternative. Applied: the frontend runs on Vercel.
- **Date:** 2026-10-26

## Context
ADR 0006 put the frontend on Vercel. ADR 0007 added Amplify Hosting to Terraform (`frontend.tf`, behind `enable_frontend`, default `false`) so the whole stack could live in AWS. In practice the frontend was deployed to Vercel (https://automl-lab-ui.vercel.app) and has stayed there:

- Vercel already builds every push and pull request. Its preview check runs in CI, and production redeploys from `main`.
- The app is on Next.js 16, which streams with `<Suspense>`. Amplify Hosting documents server-side rendering for Next.js 12 to 15 and lists streaming as unsupported.
- A Vercel project needs no AWS resources, no GitHub token in Terraform state, and no build minutes billed to the AWS account.

## Decision
- **Vercel is the frontend.** The Vercel project uses the repository's `frontend/` directory, and `NEXT_PUBLIC_API_BASE_URL` is set in its environment variables to the API's Lambda Function URL (`terraform output api_url`).
- **Terraform's `frontend_origins` lists the Vercel origin**, so it is allowed by the API's CORS and by the bucket's CORS (for presigned uploads).
- **Amplify Hosting stays in Terraform as an option**, off by default (`enable_frontend = false`). Nothing in the deployment depends on it, and the architecture diagram shows it dashed.

## Consequences
- Frontend deploys are outside GitHub Actions and Terraform: Vercel deploys on its own. Changing the API URL means updating the Vercel variable and redeploying.
- The Vercel project's settings (root directory, environment variables, domain) are configured in the Vercel dashboard and are not in this repository.
- Switching to Amplify later is `enable_frontend = true` plus a GitHub token on that apply (docs/DEPLOYMENT.md, step 5), after checking that a Next.js 16 build works there.
