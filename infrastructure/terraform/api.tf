# The API on AWS Lambda, from the same ECR image as the worker, behind a public Function URL
# (docs/ADR/0007). The function and its URL are created only when enable_compute is true, because
# Lambda needs an image in ECR to create the function (docs/DEPLOYMENT.md, "Apply order"). The IAM
# role and the log group are always created.
#
# The function runs in the private subnets with the existing "api" security group, so it reaches
# the database, S3 (gateway endpoint) and SQS (interface endpoint) exactly as before. There is no
# NAT and no SSM endpoint, so it cannot read Parameter Store itself: the two secrets are passed as
# Lambda environment variables (encrypted at rest; readable by anyone allowed lambda:GetFunction*).

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
  # front of it (the Function URL's one), used to find the real client address for the sign-in
  # limiter.
  api_environment = {
    CORS_ORIGINS           = jsonencode(local.frontend_origins)
    TRUSTED_PROXY_HOPS     = tostring(var.trusted_proxy_hops)
    PASSWORD_LOGIN_ENABLED = "false"
    DAILY_EXPERIMENT_LIMIT = tostring(var.daily_experiment_limit)
  }

  supabase_environment = {
    SUPABASE_URL           = var.supabase_url
    SUPABASE_JWT_SECRET    = var.supabase_jwt_secret
    SUPABASE_JWKS          = var.supabase_jwks
    SUPABASE_JWT_ALGORITHM = var.supabase_jwt_algorithm
  }

  # The worker (ECS) reads these by reference when its task starts.
  app_secrets = {
    DB_PASSWORD = aws_ssm_parameter.db_password.arn
    SECRET_KEY  = aws_ssm_parameter.jwt_secret.arn
  }

  lambda_environment = merge(
    # Lambda sets AWS_REGION itself and refuses a function that sets it.
    { for name, value in local.app_environment : name => value if name != "AWS_REGION" },
    local.api_environment,
    { for name, value in local.supabase_environment : name => value if value != null },
    {
      # The Lambda Web Adapter (backend/Dockerfile) forwards each request to uvicorn on PORT once
      # /health answers. Start-up (imports, migrations) can exceed Lambda's 10 s init limit, so the
      # adapter finishes initialising asynchronously instead of being restarted.
      PORT                         = "8000"
      AWS_LWA_READINESS_CHECK_PATH = "/health"
      AWS_LWA_ASYNC_INIT           = "true"
      # The same generated values that secrets.tf stores in Parameter Store for the worker.
      DB_PASSWORD = random_password.db.result
      SECRET_KEY  = random_password.jwt_secret.result
    },
  )

  api_function_name = "${var.name_prefix}-api"
  api_url           = var.enable_compute ? trimsuffix(aws_lambda_function_url.api[0].function_url, "/") : null
}

# The running API's identity: the M6 API policy, network interfaces in the VPC, logs, and pulling
# its own image.
resource "aws_iam_role" "api" {
  name = "${var.name_prefix}-api-runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "api" {
  role       = aws_iam_role.api.name
  policy_arn = aws_iam_policy.api.arn
}

resource "aws_iam_role_policy_attachment" "api_vpc_access" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "api_image_pull" {
  statement {
    sid       = "PullOwnImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.backend.arn]
  }
}

resource "aws_iam_role_policy" "api_image_pull" {
  name   = "pull-image"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_image_pull.json
}

# Created here rather than by Lambda so that the logs expire.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  count = var.enable_compute ? 1 : 0

  function_name = local.api_function_name
  description   = "AutoML Lab API (FastAPI behind the Lambda Web Adapter)."
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:latest"
  architectures = ["x86_64"]
  memory_size   = var.api_memory_mb
  timeout       = var.api_timeout_seconds

  image_config {
    command = ["api"]
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.api.id]
  }

  environment {
    variables = local.lambda_environment
  }

  lifecycle {
    # The deploy workflow rolls out each new image by commit tag. Terraform only creates the
    # function, so a later apply does not roll the API back to whatever "latest" points at.
    ignore_changes = [image_uri]
  }

  depends_on = [
    aws_iam_role_policy_attachment.api,
    aws_iam_role_policy_attachment.api_vpc_access,
    aws_iam_role_policy.api_image_pull,
    aws_cloudwatch_log_group.api,
    aws_vpc_endpoint.sqs,
  ]
}

# Public HTTPS address. Sign-in is enforced by the application on every /api/v1 route, so the URL
# itself needs no IAM authentication. CORS is left to the application (no cors block here), so
# preflight requests reach FastAPI and the two never send conflicting headers.
resource "aws_lambda_function_url" "api" {
  count = var.enable_compute ? 1 : 0

  function_name      = aws_lambda_function.api[0].function_name
  authorization_type = "NONE"
}

# Since October 2025 a public Function URL needs both statements. The second is limited to calls
# that come through the URL, so nobody can call the Invoke API on the function directly.
resource "aws_lambda_permission" "api_url" {
  count = var.enable_compute ? 1 : 0

  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api[0].function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "api_url_invoke" {
  count = var.enable_compute ? 1 : 0

  statement_id             = "PublicFunctionUrlInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api[0].function_name
  principal                = "*"
  invoked_via_function_url = true
}
