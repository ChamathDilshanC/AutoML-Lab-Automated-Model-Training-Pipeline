# ADR 0011 - Cost controls and idle compute

- **Status:** Accepted and implemented
- **Date:** 2026-10-30

## Analysis

The RDS `db.t4g.micro` is an always-on private instance and remains the dominant fixed charge
(roughly $12/month at the commonly published US East price before credits). The single SQS
interface endpoint is roughly $0.01 per endpoint-hour plus data (about $7.30/month), while the
worker is already 0..1 and costs only while it runs. Lambda is request/GB-second billed and is
normally inside its monthly free allowance for this demo. S3, SQS requests, ECR storage and
14-day logs are usage based.

RDS stop/start was rejected because RDS automatically restarts a stopped instance after seven
days and a private Lambda would need a new wake-up path, producing a fragile 503 window for every
first request. Aurora Serverless v2 auto-pause and moving metadata to an external free database
would require a migration, internet egress, and a new production dependency. The private RDS
choice is therefore retained until a measured migration can be made without weakening the
database network boundary.

## Decision

The worker remains queue-driven with a five-minute scale-in and is scheduled on Fargate Spot,
where an interruption is safe because SQS visibility timeout and the existing reaper/redelivery
path retry the job. The task is one small task at a time. Temporary S3 objects tagged
`lifecycle=temporary` expire after seven days, and API/worker logs retain 14 days. The budget
alert remains a guard rail. No stateful resource is destroyed or stopped automatically.

The SQS endpoint and private RDS are intentionally always present: removing either would require
making the database or queue public or adding a NAT gateway, both of which cost more or weaken the
boundary. All new cost controls are behind Terraform variables and can be rolled back.
