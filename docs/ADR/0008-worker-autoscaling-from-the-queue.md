# ADR 0008 — The worker scales between 0 and 1 task with the experiments queue

- **Status:** Accepted. Supersedes the worker-count part of [ADR 0006](0006-aws-deployment.md) § 7 ("the worker starts stopped" and is started by hand). Implemented as code; **not applied** to AWS.
- **Date:** 2026-10-26

## Context
The worker is an ECS Fargate service that costs about $0.055 an hour while a task runs (1 vCPU, 2 GB, plus a public IPv4 address). Until now its task count was set by hand: experiments stayed `QUEUED` until someone ran `aws ecs update-service --desired-count 1`, and a forgotten worker would cost about $40 a month. Every experiment already puts a message on the SQS queue (ADR 0005), so the queue says when there is work.

## Decision
- **Application Auto Scaling** manages the worker service's desired count, minimum 0 and maximum 1 (`worker_autoscaling.tf`, behind `enable_compute` and the new `enable_worker_autoscaling`, default `true`).
- **Two CloudWatch alarms** watch `FILL(ApproximateNumberOfMessagesVisible, 0) + FILL(ApproximateNumberOfMessagesNotVisible, 0)` on the experiments queue, at a 60-second period with the `Maximum` statistic. `NotVisible` is reported only while something is in flight, hence `FILL`.
  - **"Has work":** above 0 for one period → a step-scaling policy sets the count to exactly 1.
  - **"Idle":** at or below 0 for every one of the last `worker_scale_in_idle_minutes` periods (default 5) → a step-scaling policy sets the count to exactly 0. Missing data counts as not idle.
- **Terraform ignores `desired_count`** on the service (`lifecycle.ignore_changes`), so an apply never resets the count while a job runs. `worker_desired_count` only sets the count when the service is created.
- Application Auto Scaling acts through its AWS-managed service-linked role, created by AWS on the first apply. No custom IAM is added.

Step scaling on the queue's own metrics was chosen over ECS's queue-based target tracking because the latter divides by `RunningTaskCount`, which needs Container Insights (billed) and has no value at 0 tasks.

## Why a running job is not stopped
The worker deletes a job's message only after the job has finished (`worker/jobs.py`, `process_message`), so the message counts as in flight for the whole job and the idle alarm cannot fire. A test fails if the message is ever deleted before the job runs. The queue's visibility timeout and the worker's `JOB_TIMEOUT_SECONDS` are both `job_timeout_seconds` (1800 s, tested): a job that outlives it is failed by the reaper, and its message reappears and keeps the worker up until it has been dropped.

## Consequences
- The first job after an idle period waits for SQS metrics (about 1–3 minutes, longer if the queue had no traffic for hours) plus a Fargate start (about 1–2 minutes). The worker stays up about 6–8 minutes after the last job.
- Cost: about $0.01 per short experiment, plus about $0.40 a month for 4 alarm metrics (inside the always-free 10 alarm metrics on most accounts).
- To override the alarms, their actions must be disabled first, because an alarm keeps re-invoking its Auto Scaling action every minute while it stays in `ALARM` (docs/WORKER_AUTOSCALING.md § 8).
- A deploy (`deploy.yml`) forces a new worker deployment. During a job this interrupts it; the job is retried after the visibility timeout.

## What is verified
- `terraform fmt` and `terraform validate` pass.
- Static tests:
  - the 0–1 target and both step policies
  - both alarms on the visible + in-flight sum, missing data never scaling in, and every idle period required
  - `ignore_changes` on the desired count
  - the visibility timeout equal to `JOB_TIMEOUT_SECONDS`
- A behavioural test (moto) that the message is still in flight while the job runs.
- The missing-data rule, `ignore_changes`, and delete-after-job were each confirmed by breaking them on purpose.

## What is not verified
Anything on AWS: the alarms' timing, the service-linked role creation, the real start and stop times.
