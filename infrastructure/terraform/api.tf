# The API on AWS App Runner. Every App Runner resource (the VPC connector and the service) is
# created only when enable_compute is true: the service needs an image in ECR to start
# (docs/DEPLOYMENT.md, "Apply order"), and an account that App Runner has not yet activated rejects
# every App Runner call with SubscriptionRequiredException. The two IAM roles below are plain IAM
# and are always created, so the deploy role and the base layer do not depend on App Runner.

locals {
  # Non-secret settings shared by the API and the worker.
  app_environment = {
    ENVIRONMENT         = "production"
    DB_HOST             = aws_db_instance.main.address
    DB_PORT             = tostring(aws_db_instance.main.port)
    DB_NAME             = var.db_name
    DB_USER             = var.db_username
    DB_SSLMODE          = "require"
    STORAGE_MODE        = "s3"
    JOB_MODE            = "sqs"
    AWS_REGION          = var.region
    S3_BUCKET           = aws_s3_bucket.artifacts.bucket
    SQS_QUEUE_URL       = aws_sqs_queue.experiments.id
    JOB_TIMEOUT_SECONDS = tostring(var.job_timeout_seconds)
  }

  # API-only settings: the browser origins allowed to call the API, and how many proxies sit in
  # front of it (App Runner's one), used to find the real client address for the sign-in limiter.
  api_environment = {
    CORS_ORIGINS       = jsonencode(var.frontend_origins)
    TRUSTED_PROXY_HOPS = tostring(var.trusted_proxy_hops)
  }

  app_secrets = {
    DB_PASSWORD = aws_ssm_parameter.db_password.arn
    SECRET_KEY  = aws_ssm_parameter.jwt_secret.arn
  }
}

# App Runner pulls the image with this role.
resource "aws_iam_role" "apprunner_access" {
  name = "${var.name_prefix}-apprunner-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "apprunner_access" {
  role       = aws_iam_role.apprunner_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# The running application's identity: the M6 API policy (S3 objects, SQS send) and permission to
# read its two secrets. App Runner also uses this role to resolve the secrets at start.
resource "aws_iam_role" "api" {
  name = "${var.name_prefix}-api-runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "api" {
  role       = aws_iam_role.api.name
  policy_arn = aws_iam_policy.api.arn
}

resource "aws_iam_role_policy" "api_secrets" {
  name   = "read-secrets"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

# Same count as the service, so the service's aws_apprunner_vpc_connector.api[0] always exists
# whenever the service does.
resource "aws_apprunner_vpc_connector" "api" {
  count = var.enable_compute ? 1 : 0

  vpc_connector_name = "${var.name_prefix}-api"
  subnets            = aws_subnet.private[*].id
  security_groups    = [aws_security_group.api.id]
}

resource "aws_apprunner_service" "api" {
  count = var.enable_compute ? 1 : 0

  service_name = "${var.name_prefix}-api"

  source_configuration {
    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_access.arn
    }

    image_repository {
      image_identifier      = "${aws_ecr_repository.backend.repository_url}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port                          = "8000"
        runtime_environment_variables = merge(local.app_environment, local.api_environment)
        runtime_environment_secrets   = local.app_secrets
      }
    }
  }

  instance_configuration {
    cpu               = var.api_cpu
    memory            = var.api_memory
    instance_role_arn = aws_iam_role.api.arn
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.api[0].arn
    }

    ingress_configuration {
      is_publicly_accessible = true
    }
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  depends_on = [
    aws_iam_role_policy_attachment.apprunner_access,
    aws_iam_role_policy_attachment.api,
    aws_vpc_endpoint.sqs,
  ]
}
