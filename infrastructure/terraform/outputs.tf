output "bucket_name" {
  description = "Name of the private artifacts bucket."
  value       = aws_s3_bucket.artifacts.bucket
}

output "queue_url" {
  description = "URL of the experiments queue."
  value       = aws_sqs_queue.experiments.id
}

output "dead_letter_queue_url" {
  description = "URL of the dead-letter queue. Messages that failed repeatedly end up here."
  value       = aws_sqs_queue.dead_letter.id
}

output "api_policy_arn" {
  description = "IAM policy for the API runtime."
  value       = aws_iam_policy.api.arn
}

output "worker_policy_arn" {
  description = "IAM policy for the worker runtime."
  value       = aws_iam_policy.worker.arn
}

output "local_dev_policy_arn" {
  description = "IAM policy for running the API and the worker together as one local identity."
  value       = aws_iam_policy.local_dev.arn
}

output "backend_environment" {
  description = "Variables to put in the backend's .env (names only matter; there are no secrets here)."
  value       = <<-EOT
    STORAGE_MODE=s3
    JOB_MODE=sqs
    AWS_REGION=${var.region}
    S3_BUCKET=${aws_s3_bucket.artifacts.bucket}
    SQS_QUEUE_URL=${aws_sqs_queue.experiments.id}
  EOT
}
