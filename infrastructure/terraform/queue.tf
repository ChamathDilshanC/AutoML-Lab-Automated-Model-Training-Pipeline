# Standard queue, not FIFO. See docs/ADR/0005: delivery is at-least-once and the worker's claim
# is idempotent, and FIFO would add ordering and de-duplication that nothing here needs while
# limiting throughput.

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name_prefix}-experiments-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "experiments" {
  name                       = "${var.name_prefix}-experiments-queue"
  visibility_timeout_seconds = var.job_timeout_seconds
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = var.max_receive_count
  })
}

data "aws_iam_policy_document" "queue_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.experiments.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "experiments" {
  queue_url = aws_sqs_queue.experiments.id
  policy    = data.aws_iam_policy_document.queue_tls_only.json
}
