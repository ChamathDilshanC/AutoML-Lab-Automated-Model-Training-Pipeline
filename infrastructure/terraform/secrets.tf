# The two secret values the containers need, as SSM SecureString parameters. They are passed to the
# containers by reference (App Runner and ECS read them at start), never as plain environment
# variables, so they do not appear in the service or task definition.

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
