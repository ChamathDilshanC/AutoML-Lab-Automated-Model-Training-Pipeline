# The two secret values the application needs, as SSM SecureString parameters. The worker gets them
# by reference (ECS reads them when the task starts), so they do not appear in its task definition.
# The API on Lambda cannot reach Parameter Store from the private subnets (no NAT, no SSM
# endpoint), so it receives the same values as encrypted environment variables instead (api.tf,
# docs/ADR/0007).

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_ssm_parameter" "db_password" {
  name        = "/${var.name_prefix}/db-password"
  description = "PostgreSQL password for the AutoML Lab application user."
  type        = "SecureString"
  value       = random_password.db.result
}

resource "aws_ssm_parameter" "jwt_secret" {
  name        = "/${var.name_prefix}/jwt-secret"
  description = "Signing key for AutoML Lab sign-in tokens (SECRET_KEY)."
  type        = "SecureString"
  value       = random_password.jwt_secret.result
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    sid       = "ReadOwnSecrets"
    actions   = ["ssm:GetParameters"]
    resources = [aws_ssm_parameter.db_password.arn, aws_ssm_parameter.jwt_secret.arn]
  }
}
