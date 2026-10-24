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

output "ecr_repository_url" {
  description = "Where the backend image is pushed."
  value       = aws_ecr_repository.backend.repository_url
}

output "database_endpoint" {
  description = "Private address of the PostgreSQL instance (reachable only from inside the VPC)."
  value       = aws_db_instance.main.address
}

output "api_url" {
  description = "Public URL of the API once enable_compute is true. Use it as NEXT_PUBLIC_API_BASE_URL in Vercel."
  value       = var.enable_compute ? "https://${aws_apprunner_service.api[0].service_url}" : null
}

output "github_deploy_role_arn" {
  description = "Role for the AWS_DEPLOY_ROLE_ARN GitHub variable."
  value       = aws_iam_role.deploy.arn
}

output "github_variables" {
  description = "Values to set as GitHub repository variables for .github/workflows/deploy.yml."
  value       = <<-EOT
    AWS_REGION=${var.region}
    AWS_DEPLOY_ROLE_ARN=${aws_iam_role.deploy.arn}
    ECR_REPOSITORY=${aws_ecr_repository.backend.name}
    APP_RUNNER_SERVICE_ARN=${var.enable_compute ? aws_apprunner_service.api[0].arn : "(available after enable_compute = true)"}
    ECS_CLUSTER=${aws_ecs_cluster.main.name}
    ECS_WORKER_SERVICE=${var.name_prefix}-worker
    DEPLOY_ENABLED=true
  EOT
}
