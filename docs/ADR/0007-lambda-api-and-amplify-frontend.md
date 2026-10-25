# ADR 0007 — The API on Lambda and the frontend on Amplify Hosting

- **Status:** Accepted. Supersedes [ADR 0006](0006-aws-deployment.md) § 1 for the API and the frontend, § 5 for how the API gets its secrets, and the App Runner parts of §§ 4, 6, 7 and 9. Implemented and applied: the API has been live on Lambda since 2026-10-26 (deployed by hand). Amplify has not been applied; the frontend runs on Vercel.
- **Date:** 2026-10-25

## Context
ADR 0006 put the API on AWS App Runner. AWS moved App Runner to maintenance on 30 April 2026: it is no longer available to new customers, and the owner's account (new, on the AWS Free plan) gets `SubscriptionRequiredException` from every App Runner call. The base layer (network, database, bucket, queues, registry, IAM, budget) is already applied. The replacement has to run on that account, cost as close to nothing as possible, and fit a network with private subnets, no NAT gateway, and VPC endpoints for S3 and SQS only.

## Options for the API
| | Cost (us-east-1, on demand) | Works for this app? |
|---|---|---|
| ECS Fargate service, public subnet, public IP, no load balancer | About 40 USD a month (1 vCPU, 2 GB, plus a public IPv4 address) | No: the address changes on every deployment and there is no TLS, so an HTTPS frontend cannot call it (mixed content). An Application Load Balancer fixes that for about 16 to 18 USD a month more |
| **Lambda container image with a Function URL** | **Nothing within Lambda's always-free allowance** (1 million requests and 400,000 GB-seconds a month, on every plan); beyond it, per request and per GB-second | Yes: a fixed HTTPS address, and it runs in the private subnets with the existing `api` security group, whose rules already allow the database, the SQS endpoint and S3 |
| One EC2 `t3.micro` running the image | About 13 USD a month (instance, 20 GB disk, public IPv4) | Partly: 1 GiB of memory is tight for pandas and scikit-learn with models of up to 200 MB, there is no TLS without a domain or CloudFront, and the instance has to be patched |

## Decisions

### 1. The API runs on Lambda behind a public Function URL
The same backend image runs as a Lambda function (`image_config.command = ["api"]`, 2048 MB, 60 s timeout) in the private subnets with the `api` security group. The **AWS Lambda Web Adapter** (`public.ecr.aws/awsguru/aws-lambda-adapter`, version 1.1.0, pinned by digest) is copied into `/opt/extensions`. On Lambda it turns each invocation into an HTTP request to the unchanged uvicorn server once `/health` answers; anywhere else the file is never run, so the worker and local Docker are unaffected. Start-up (imports, the migration check under its advisory lock) can exceed Lambda's 10-second init limit, so the adapter's asynchronous initialisation is on.

The Function URL uses auth type `NONE`: the application already requires a bearer token on every `/api/v1` route. Since October 2025 such a URL needs two resource-policy statements, `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`; the second is limited with `lambda:InvokedViaFunctionUrl`, so nobody can call the Invoke API directly. CORS stays in FastAPI; the URL has no CORS configuration of its own, so the two cannot send conflicting headers.

`TRUSTED_PROXY_HOPS` stays 1: the Function URL is the one proxy that appends to `X-Forwarded-For`. Like App Runner's behaviour before it, this is an assumption to confirm on the first deployment (ADR 0006 § 9).

### 2. The API's secrets are Lambda environment variables
App Runner read the two SSM parameters from outside the VPC. A function in the private subnets cannot reach Parameter Store: there is no NAT gateway and no SSM endpoint. An SSM interface endpoint (about 7.30 USD a month in one zone) plus a change to read the parameters at start-up was the alternative. The owner chose to pass the same generated values (`random_password`) as Lambda environment variables instead, at no cost.

They are encrypted at rest, but anyone allowed `lambda:GetFunction`, `GetFunctionConfiguration` or `UpdateFunctionCode` sees them in the function's configuration. In practice that adds no one: the GitHub deploy role could already push an image that reads them at run time, and an account administrator can read the SSM parameters anyway. The deploy workflow narrows the output of every call that returns the configuration so that they never reach the job log. The worker still reads both values by reference.

### 3. App Runner is removed
The App Runner service, VPC connector, image-pull role (`apprunner_access`) and its policy attachment are deleted from the code. The API runtime role keeps its name and the M6 API policy; it now trusts `lambda.amazonaws.com`, adds `AWSLambdaVPCAccessExecutionRole` and permission to pull its own image, and drops the Parameter Store read it no longer needs. The `api` security group keeps its description, which still names App Runner, because changing it would replace the group and the database rules that refer to it.

### 4. Deployments update the function's image
The deploy role swaps `apprunner:*` for `lambda:UpdateFunctionCode`, `lambda:GetFunctionConfiguration` and `lambda:GetFunctionUrlConfig` on the one function, and may read images in the one repository (Lambda checks this on update). The workflow builds without a provenance attestation (Lambda refuses a multi-manifest index), points the function at the commit-SHA image, waits for the update, and requests `/health` on the Function URL. Terraform ignores later changes to the function's image, so an apply never rolls the API back.

### 5. The frontend on Amplify Hosting, opt-in
`enable_frontend` (default `false`) creates an Amplify app (`WEB_COMPUTE`, connected to the GitHub repository through the Amplify GitHub App) and one branch (default `main`, auto-build on). The build spec builds `frontend/` with Node 24; `AMPLIFY_MONOREPO_APP_ROOT=frontend`. The branch gets `NEXT_PUBLIC_API_BASE_URL` set to the Function URL, and the branch's origin is added to the API's and the bucket's CORS. The GitHub token is a sensitive variable passed through `TF_VAR_amplify_github_token`; Amplify uses it once and does not keep it, but the Terraform state does. Terraform does not start a build.

Amplify documents server-side rendering for Next.js 12 to 15 and lists streaming as unsupported. This app is on Next.js 16 and streams with `<Suspense>`, so whether Amplify serves it correctly is **open** until the first build is checked. Vercel remains a supported alternative (`frontend_origins`).

## Consequences
- The API has no hourly cost; a public URL means heavy traffic would be billed past the free allowance (the budget alert still applies). A new account's Lambda concurrency limit can be as low as 10, so no reserved concurrency is set.
- Cold starts: the first request after an idle period waits for a new instance (imports and the migration check), likely several seconds.
- In-memory state is per instance: the sign-in and prediction rate limits apply per Lambda instance, and the API's reaper loop runs only while an instance is active. The worker still reaps abandoned jobs on every poll.
- Requests and responses are limited to 6 MB by Lambda. Dataset files go straight to S3 with a presigned URL in cloud mode, so the API never receives them.
- The next apply deletes two existing resources (the `apprunner_access` role and its policy attachment) and the API role's inline Parameter Store policy, and changes the API role's trust in place.
- The AWS provider must be 6.28 or newer (`invoked_via_function_url`).

## What is verified
- `terraform fmt` and `terraform validate` pass with the AWS provider 6.70.
- Static tests of the properties above (no App Runner resource left, every Lambda resource behind `enable_compute` and every Amplify resource behind `enable_frontend`, private subnets and the `api` security group, the URL public but direct invocation not, no reserved `AWS_REGION`, the role trusting only Lambda, the workflow never printing the configuration); the region and invocation checks were confirmed by breaking them on purpose.
- CI builds the image with the adapter and runs it as an ordinary container (non-root, `/health`).
- On AWS (2026-10-26): the function runs in the VPC and the adapter starts the image; `GET /health` on the Function URL answers 200, `/api/v1` routes answer 401 without a token, and a CORS preflight from the Vercel origin is allowed. Each new instance applies the migrations before it serves, so an answering instance has also reached RDS with the injected password.

## What is not verified
- Cold-start time, the Function URL's `X-Forwarded-For`, the deploy workflow, S3 uploads and SQS hand-off from the API, and the Amplify connection and build.
