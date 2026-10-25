# The worker starts when there is work and stops when there is none (docs/WORKER_AUTOSCALING.md,
# docs/ADR/0008). Created only when enable_compute and enable_worker_autoscaling are both true.
#
#   queue has a message waiting or being processed  ->  alarm "queue-has-work"  ->  1 task
#   nothing waiting and nothing in flight for worker_scale_in_idle_minutes  ->  alarm "queue-idle"  ->  0 tasks
#
# A job's message stays in flight until the job has finished (worker/jobs.py, process_message), so
# the queue never looks empty while a job runs, and scale-in cannot stop a running job. A job that
# outlives job_timeout_seconds is failed by the reaper anyway, and its message then reappears, which
# also keeps the worker up until it has been dealt with.
#
# Application Auto Scaling acts through its service-linked role
# (AWSServiceRoleForApplicationAutoScaling_ECSService, AWS-managed: ecs:DescribeServices,
# ecs:UpdateService and the CloudWatch alarm calls it needs). AWS creates it on the first apply;
# Terraform does not manage it, and no other IAM is needed.

locals {
  worker_autoscaling = var.enable_compute && var.enable_worker_autoscaling

  # Messages waiting plus messages being processed. ApproximateNumberOfMessagesNotVisible is only
  # reported while something is in flight, so a missing value means 0 (FILL).
  queue_outstanding_metrics = {
    visible  = "ApproximateNumberOfMessagesVisible"
    inflight = "ApproximateNumberOfMessagesNotVisible"
  }
  queue_outstanding_expression = "FILL(visible, 0) + FILL(inflight, 0)"
}

resource "aws_appautoscaling_target" "worker" {
  count = local.worker_autoscaling ? 1 : 0

  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker[0].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 1
}

resource "aws_appautoscaling_policy" "worker_start" {
  count = local.worker_autoscaling ? 1 : 0

  name               = "${var.name_prefix}-worker-start"
  policy_type        = "StepScaling"
  service_namespace  = aws_appautoscaling_target.worker[0].service_namespace
  resource_id        = aws_appautoscaling_target.worker[0].resource_id
  scalable_dimension = aws_appautoscaling_target.worker[0].scalable_dimension

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    # Any amount above the alarm's threshold of 0: run one task.
    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "worker_stop" {
  count = local.worker_autoscaling ? 1 : 0

  name               = "${var.name_prefix}-worker-stop"
  policy_type        = "StepScaling"
  service_namespace  = aws_appautoscaling_target.worker[0].service_namespace
  resource_id        = aws_appautoscaling_target.worker[0].resource_id
  scalable_dimension = aws_appautoscaling_target.worker[0].scalable_dimension

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    # At or below the alarm's threshold of 0: run no task.
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_queue_has_work" {
  count = local.worker_autoscaling ? 1 : 0

  alarm_name          = "${var.name_prefix}-worker-queue-has-work"
  alarm_description   = "An experiment is waiting or being processed: start the worker (docs/WORKER_AUTOSCALING.md)."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_start[0].arn]

  metric_query {
    id          = "outstanding"
    label       = "Experiment messages waiting or in flight"
    expression  = local.queue_outstanding_expression
    return_data = true
  }

  dynamic "metric_query" {
    for_each = local.queue_outstanding_metrics
    content {
      id = metric_query.key
      metric {
        namespace   = "AWS/SQS"
        metric_name = metric_query.value
        dimensions  = { QueueName = aws_sqs_queue.experiments.name }
        period      = 60
        stat        = "Maximum"
      }
    }
  }
}

# Missing data counts as "not idle": if the metrics ever stop, the worker stays up (it costs a few
# cents an hour) rather than risk stopping a job.
resource "aws_cloudwatch_metric_alarm" "worker_queue_idle" {
  count = local.worker_autoscaling ? 1 : 0

  alarm_name          = "${var.name_prefix}-worker-queue-idle"
  alarm_description   = "No experiment waiting or in flight for ${var.worker_scale_in_idle_minutes} minutes: stop the worker (docs/WORKER_AUTOSCALING.md)."
  comparison_operator = "LessThanOrEqualToThreshold"
  threshold           = 0
  evaluation_periods  = var.worker_scale_in_idle_minutes
  datapoints_to_alarm = var.worker_scale_in_idle_minutes
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_stop[0].arn]

  metric_query {
    id          = "outstanding"
    label       = "Experiment messages waiting or in flight"
    expression  = local.queue_outstanding_expression
    return_data = true
  }

  dynamic "metric_query" {
    for_each = local.queue_outstanding_metrics
    content {
      id = metric_query.key
      metric {
        namespace   = "AWS/SQS"
        metric_name = metric_query.value
        dimensions  = { QueueName = aws_sqs_queue.experiments.name }
        period      = 60
        stat        = "Maximum"
      }
    }
  }
}
