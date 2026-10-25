# Worker autoscaling: the worker starts and stops by itself

> **Status:** Implemented as code (`infrastructure/terraform/worker_autoscaling.tf`, [ADR 0008](ADR/0008-worker-autoscaling-from-the-queue.md)). **Not yet applied** to AWS: the timings below come from AWS documentation and the configuration, not from measurement. Update this page after the first real test.

Related: [DEPLOYMENT.md](DEPLOYMENT.md) · [ADR 0005 (S3 and SQS)](ADR/0005-s3-storage-and-sqs-job-queue.md) · [ADR 0008](ADR/0008-worker-autoscaling-from-the-queue.md)

## 1. What this does
The training worker is an ECS Fargate task. It costs money for every minute it runs, so it should run only while there is something to train. With autoscaling on:

- You click **Run experiment**. A few minutes later the worker starts by itself, trains, and saves the model.
- About five minutes after the last job has finished, the worker stops by itself.
- You never run `aws ecs update-service` by hand.

It is on by default (`enable_worker_autoscaling = true`) whenever the compute layer is on (`enable_compute = true`).

## 2. How it works

```
 You click "Run experiment"
        │
        ▼
 API (Lambda) ── saves the experiment as QUEUED, sends {"experiment_id": …} ──►  SQS experiments queue
                                                                                      │
              SQS reports two numbers to CloudWatch every minute:                     │
              messages waiting (Visible) + messages being worked on (NotVisible)  ◄───┘
                                                                                      │
        ┌──────────────── waiting + in flight > 0  (one 1-minute check) ──────────────┤
        ▼                                                                             │
 alarm "automl-lab-worker-queue-has-work"                                             │
        │  (ALARM)                                                                    │
        ▼                                                                             │
 Application Auto Scaling: worker desired count = 1                                   │
        │                                                                             │
        ▼                                                                             │
 ECS starts one Fargate task (about 1–2 minutes)                                      │
        │                                                                             │
        ▼                                                                             │
 Worker receives the message ──► experiment RUNNING ──► trains ──► model saved to S3, │
        │                                              results in RDS: SUCCEEDED      │
        ▼                                                                             │
 Worker deletes the message  (only now: the message was "in flight" the whole time)  │
        │                                                                             │
        └──────────── waiting + in flight = 0  for 5 minutes in a row ────────────────┘
                                   │
                                   ▼
                 alarm "automl-lab-worker-queue-idle"  (ALARM)
                                   │
                                   ▼
             Application Auto Scaling: worker desired count = 0  ──►  task stops, billing stops
```

| Part | Name in AWS | Setting |
|---|---|---|
| Scalable target | ECS service `automl-lab-worker` in `automl-lab-cluster` | minimum 0, maximum 1 task |
| "Has work" alarm | `automl-lab-worker-queue-has-work` | `FILL(visible,0) + FILL(inflight,0) > 0` for 1 of 1 one-minute periods → start policy |
| "Idle" alarm | `automl-lab-worker-queue-idle` | the same sum `<= 0` for 5 of 5 one-minute periods (`worker_scale_in_idle_minutes`) → stop policy |
| Start policy | `automl-lab-worker-start` | step scaling, set the count to exactly 1 |
| Stop policy | `automl-lab-worker-stop` | step scaling, set the count to exactly 0 |

### Why a running job is never stopped
1. The worker **deletes a job's message only after the job has finished** (succeeded or failed). Until then the message is *in flight*, which counts in `ApproximateNumberOfMessagesNotVisible`. So while a job runs, "waiting + in flight" is at least 1 and the idle alarm cannot fire. A test (`backend/tests/test_aws.py::test_the_message_stays_in_flight_until_training_has_finished`) fails if this ever changes.
2. The idle alarm needs **every one** of the last 5 one-minute values to be 0, not just some of them.
3. If CloudWatch has **no data**, the idle alarm treats that as "not idle": the worker stays up (a few cents an hour) rather than risk stopping a job.
4. Terraform ignores the service's task count (`lifecycle { ignore_changes = [desired_count] }`), so `terraform apply` never resets it in the middle of a job.

### Do the timeouts fit together?
Yes. One variable, `job_timeout_seconds` (1800 s = 30 minutes), sets both the queue's **visibility timeout** (how long a received message stays hidden) and the worker's `JOB_TIMEOUT_SECONDS` (when the reaper marks a `RUNNING` experiment as failed). A test checks they stay equal.

- A job shorter than 30 minutes keeps its message in flight for its whole run: the worker stays up.
- A job longer than 30 minutes is failed by the reaper at 30 minutes, and its message reappears in the queue (waiting). That also keeps the worker up until the message has been dealt with, so nothing is cut off silently. If your training really needs longer, raise `job_timeout_seconds` (it changes both values together).
- If a job's message is received 3 times without being deleted (for example the database was down each time), SQS moves it to the dead-letter queue. The dead-letter queue does not count, so it does not keep the worker running.

### What it needs (IAM)
Nothing new to write by hand. Application Auto Scaling uses its AWS-managed service-linked role `AWSServiceRoleForApplicationAutoScaling_ECSService` (it may only describe and update ECS services and manage its own CloudWatch alarm links). AWS creates it automatically on the first apply. It does not appear in the Terraform plan, and Terraform does not manage it. The worker's own roles and the GitHub deploy role are unchanged.

## 3. Expected timings
| Step | Typical time |
|---|---|
| Click → message in the queue | under a second |
| Message in the queue → "has work" alarm fires | 1–3 minutes (SQS publishes its metrics once a minute, and they arrive a little late) |
| … if the queue had no traffic for several hours | can be noticeably longer (up to roughly 15 minutes) while SQS resumes its metrics |
| Alarm → Fargate task running (image pull, start) | 1–2 minutes |
| Experiment shows **Running** in the UI | **about 3–5 minutes after the click** |
| Training `iris.csv` with all algorithms | well under a minute |
| Job finished → worker stopped | about 6–8 minutes (5 idle minutes, metric delay, then about 30 s to stop) |

Several experiments queued close together share one worker start: the worker takes them one after another and stops after the last.

## 4. Cost
Prices for us-east-1, on demand; check current AWS pricing.

| Item | Cost |
|---|---|
| Worker task (1 vCPU, 2 GB Fargate, plus its public IPv4 address) | about **$0.055 per hour, only while it runs** |
| One experiment like iris (start + training + 5 idle minutes before stopping) | about 8–10 running minutes ≈ **$0.01** |
| Two CloudWatch alarms (each adds up two SQS metrics, so 4 "alarm metrics") | $0.10 each = **$0.40 a month**; the always-free tier includes 10 alarm metrics, so likely $0 |
| SQS requests, logs | within the free tier at this scale |

| Usage | Estimated monthly cost |
|---|---|
| 20 experiments | about $0.20 (+ $0.40 alarms if outside the free tier) |
| 100 experiments | about $1.00 (+ $0.40) |
| 300 experiments | about $3.00 (+ $0.40) |
| Worker accidentally left running all month (compare) | about $40 |

The old setup (worker started by hand and forgotten) is what the last row protects against. The monthly AWS Budget alert (10 USD) still applies.

## 5. Turn it on
You need Terraform, the AWS CLI signed in to your account (`aws sts get-caller-identity`), and `enable_compute = true` already applied.

```powershell
Set-Location "C:\Users\chamm\Desktop\AutoML Lab — Automated Model Training Pipeline\infrastructure\terraform"
git pull
terraform init
terraform plan -out tfplan
```

**What the plan should show** (with `enable_compute = true` and nothing else changed by hand):

```
  # aws_appautoscaling_policy.worker_start[0] will be created
  # aws_appautoscaling_policy.worker_stop[0] will be created
  # aws_appautoscaling_target.worker[0] will be created
  # aws_cloudwatch_metric_alarm.worker_queue_has_work[0] will be created
  # aws_cloudwatch_metric_alarm.worker_queue_idle[0] will be created

Plan: 5 to add, 0 to change, 0 to destroy.
```

If it shows anything to **destroy**, or changes you did not expect (for example on `aws_ecs_service.worker[0]`), stop and read them: something was changed by hand since the last apply. Then:

```powershell
terraform apply tfplan
Remove-Item tfplan        # a saved plan can contain secret values
```

Check it worked:

```powershell
$env:AWS_DEFAULT_REGION = "us-east-1"
aws application-autoscaling describe-scalable-targets --service-namespace ecs --resource-ids service/automl-lab-cluster/automl-lab-worker --query "ScalableTargets[0].[MinCapacity,MaxCapacity]" --output text
aws cloudwatch describe-alarms --alarm-names automl-lab-worker-queue-has-work automl-lab-worker-queue-idle --query "MetricAlarms[].[AlarmName,StateValue]" --output table
```

Expect `0  1`. The alarms start as `INSUFFICIENT_DATA` for a minute or two. With an empty queue, "has-work" then becomes `OK` and "idle" becomes `ALARM` (which simply keeps the worker at 0).

## 6. Test it with iris.csv
### Make the file
From the repository root (the backend's Python environment has scikit-learn):

```powershell
python -c "from sklearn.datasets import load_iris; load_iris(as_frame=True).frame.to_csv('iris.csv', index=False)"
```

It has 150 rows: four measurement columns and a `target` column (0, 1 or 2). Do not commit it.

### Run an experiment
1. Open the frontend (https://automl-lab-ui.vercel.app) and sign in.
2. **Upload dataset** (top bar) → **Choose CSV file** → pick `iris.csv` → wait for the data-quality report.
3. **Create an experiment** → Target column `target`, task **Classification**, keep the default metric and algorithms → **Run experiment**. Note the time.
4. The experiment shows **Queued**. Wait: after about 3–5 minutes it should change to **Running**, then **Succeeded** shortly after, with a leaderboard.

### Watch it happen
Set these once per PowerShell window:

```powershell
$env:AWS_DEFAULT_REGION = "us-east-1"
$Cluster = "automl-lab-cluster"
$Service = "automl-lab-worker"
$Queue   = terraform -chdir="C:\Users\chamm\Desktop\AutoML Lab — Automated Model Training Pipeline\infrastructure\terraform" output -raw queue_url
```

| What | Command |
|---|---|
| Messages waiting / in flight | `aws sqs get-queue-attributes --queue-url $Queue --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes` |
| Alarm states | `aws cloudwatch describe-alarms --alarm-names automl-lab-worker-queue-has-work automl-lab-worker-queue-idle --query "MetricAlarms[].[AlarmName,StateValue]" --output table` |
| What the autoscaler did | `aws application-autoscaling describe-scaling-activities --service-namespace ecs --resource-id service/$Cluster/$Service --max-items 5 --query "ScalingActivities[].[StartTime,StatusCode,Description]" --output table` |
| Tasks wanted / running | `aws ecs describe-services --cluster $Cluster --services $Service --query "services[0].[desiredCount,runningCount,pendingCount]" --output text` |
| Worker logs, live | `aws logs tail /ecs/automl-lab-worker --follow --since 30m` |

In the **ECS console**: Amazon ECS → **Clusters** → `automl-lab-cluster` → **Services** → `automl-lab-worker` → **Tasks** tab. A task appears as *Provisioning* → *Pending* → *Running*, and disappears after it stops. The **Events** tab lists each change of the desired count.

In the logs you should see, in this order:

```
... INFO worker Worker started; long-polling the SQS queue
... INFO worker Claimed experiment ex_...
... INFO worker Finished experiment ex_...: SUCCEEDED
... INFO worker Worker stopped                 (about 6–8 minutes later, when it is scaled in)
```

## 7. Check the worker is back to 0
About 6–8 minutes after the experiment succeeded:

```powershell
aws ecs describe-services --cluster $Cluster --services $Service --query "services[0].[desiredCount,runningCount]" --output text
```

Expect `0  0`. The "idle" alarm is `ALARM` and the scaling activities show a "Setting desired count to 0" entry. In the console, the service's **Tasks** tab is empty.

## 8. Manual override
The alarms keep re-applying their decision while they stay in `ALARM`. So to override them, switch an alarm's actions off first, then set the count. Switching actions back on hands control back to autoscaling.

**Keep the worker running** (for example to watch it or debug):

```powershell
aws cloudwatch disable-alarm-actions --alarm-names automl-lab-worker-queue-idle
aws ecs update-service --cluster $Cluster --service $Service --desired-count 1 --query "service.desiredCount"
```

**Keep the worker off** (pause training; experiments wait as Queued):

```powershell
aws cloudwatch disable-alarm-actions --alarm-names automl-lab-worker-queue-has-work
aws ecs update-service --cluster $Cluster --service $Service --desired-count 0 --query "service.desiredCount"
```

**Hand control back to autoscaling:**

```powershell
aws cloudwatch enable-alarm-actions --alarm-names automl-lab-worker-queue-has-work automl-lab-worker-queue-idle
```

In the console the same steps are: **CloudWatch** → **Alarms** → select the alarm → **Actions** → **Disable actions** (or **Enable actions**); then **ECS** → `automl-lab-cluster` → `automl-lab-worker` → **Update service** → **Desired tasks**.

Disabled alarm actions are a change Terraform knows about: the next `terraform plan` shows `actions_enabled` going back to `true` on that alarm, and applying it hands control back too.

## 9. Troubleshooting
### The experiment stays "Queued"
1. Wait at least 5 minutes, or about 15 if nothing had used the queue for hours (section 3).
2. Is the message in the queue? Run the queue command from section 6. `ApproximateNumberOfMessages` should be 1. If it is 0 and nothing is in flight, the API did not send it: check that the API runs with `JOB_MODE=sqs`.
3. Did the "has work" alarm fire? Check the alarm states. If it says `INSUFFICIENT_DATA` or `OK`, see the next section.
4. Did the autoscaler act? Run the scaling-activities command. A `Failed` entry tells you why.
5. Did ECS try to start a task? `aws ecs describe-services --cluster $Cluster --services $Service --query "services[0].events[:5].message"`. If tasks start and stop, see "The task fails to start".
6. Is autoscaling there at all? `terraform state list | Select-String "appautoscaling|metric_alarm"` should list 5 resources.

### The alarm does not fire
- `INSUFFICIENT_DATA` for a long time: SQS has not published metrics yet. Open **CloudWatch** → **Metrics** → **SQS** → **Queue Metrics** → `automl-lab-experiments-queue` → `ApproximateNumberOfMessagesVisible` and check that recent points exist.
- Actions switched off? `aws cloudwatch describe-alarms --alarm-names automl-lab-worker-queue-has-work --query "MetricAlarms[0].ActionsEnabled"` must be `True` (section 8).
- What did it do? `aws cloudwatch describe-alarm-history --alarm-name automl-lab-worker-queue-has-work --max-items 5 --query "AlarmHistoryItems[].[Timestamp,HistorySummary]" --output table`

### The task fails to start
Find the reason:

```powershell
$Task = aws ecs list-tasks --cluster $Cluster --service-name $Service --desired-status STOPPED --query "taskArns[0]" --output text
aws ecs describe-tasks --cluster $Cluster --tasks $Task --query "tasks[0].[stoppedReason,containers[0].reason,containers[0].exitCode]" --output text
```

| Reason contains | Meaning and fix |
|---|---|
| `CannotPullContainerError` | No image tagged `latest` in ECR, or no route to ECR. Push the image (DEPLOYMENT.md, "First image"). |
| `ResourceInitializationError` … `secrets` / `ssm` | The task could not read its two SSM parameters. Check the worker execution role's `read-secrets` policy and that the parameters exist. |
| Exit code 1 | Read the logs (`aws logs tail /ecs/automl-lab-worker --since 1h`). A `TimeoutError` about the schema after about 5 minutes (`MIGRATION_WAIT_SECONDS`) means the database migrations never ran: request the API's `/health` once (the API applies them when it starts), then queue the experiment again. |

### The worker stops too early
It should not stop during a job (section 2). If it does:
- Did the job run longer than `job_timeout_seconds` (30 minutes)? Then the reaper failed it on purpose. Raise `job_timeout_seconds` if your training needs longer.
- Is `worker_scale_in_idle_minutes` still 5 (or higher)? Raise it if experiments are often queued a few minutes apart and you would rather keep the worker warm between them.
- Check the worker logs for "Could not delete a handled queue message" or exceptions.

### The worker stays on longer than expected
- A job that crashed the worker (for example out of memory) leaves its message in flight for up to 30 minutes. The worker stays up until the message reappears, is dropped (the experiment is no longer queued), and the queue is empty again. This costs about $0.03.
- The "idle" alarm's actions are disabled (section 8), or it is in `INSUFFICIENT_DATA`.
- A deploy (`deploy.yml`) forces a new worker deployment. If it runs while a job is training, that job is interrupted and retried after the visibility timeout. Avoid deploying while an experiment is running.

### Messages in the dead-letter queue
A message lands there after 3 deliveries without being deleted, usually because the database could not be reached each time. The experiment then stays **Queued**.

```powershell
$Dlq = terraform -chdir="C:\Users\chamm\Desktop\AutoML Lab — Automated Model Training Pipeline\infrastructure\terraform" output -raw dead_letter_queue_url
aws sqs get-queue-attributes --queue-url $Dlq --attribute-names ApproximateNumberOfMessages --query Attributes
```

Messages contain only an experiment ID. Once the cause is fixed, move them back to the experiments queue (the worker will pick them up and start by itself):

```powershell
$DlqArn = aws sqs get-queue-attributes --queue-url $Dlq --attribute-names QueueArn --query Attributes.QueueArn --output text
aws sqs start-message-move-task --source-arn $DlqArn
```

## 10. Cost notes and turning it off
- The worker bills only while a task runs. The alarms cost about $0.40 a month, or nothing within the free tier.
- To turn autoscaling **off**, set `enable_worker_autoscaling = false` in `terraform.tfvars` and apply. The plan shows the 5 resources being destroyed. The worker keeps whatever task count it had at that moment (Terraform ignores the count), so set it yourself afterwards. Check that it is 0 so nothing keeps billing:

  ```powershell
  aws ecs update-service --cluster automl-lab-cluster --service automl-lab-worker --desired-count 0 --query "service.desiredCount"
  ```

- With autoscaling off you start and stop the worker by hand with the same command (`--desired-count 1` / `0`). `worker_desired_count` in Terraform only sets the count when the service is first created.
- To change how long the worker waits before stopping, set `worker_scale_in_idle_minutes` (2 to 60) and apply.
