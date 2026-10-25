# The training worker on ECS Fargate, started from the same image as the API with the "worker"
# command. The service exists only when enable_compute is true and is created with
# worker_desired_count tasks (default 0, so nothing bills for compute until there is work). With
# enable_worker_autoscaling it then starts and stops by itself with the experiments queue
# (worker_autoscaling.tf, docs/WORKER_AUTOSCALING.md).

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days
}

# ECS itself uses this role to pull the image, write logs and read the two secrets.
resource "aws_iam_role" "worker_execution" {
  name = "${var.name_prefix}-worker-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "worker_execution" {
  role       = aws_iam_role.worker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "worker_execution_secrets" {
  name   = "read-secrets"
  role   = aws_iam_role.worker_execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

# The running worker's identity: the M6 worker policy and nothing else.
resource "aws_iam_role" "worker" {
  name = "${var.name_prefix}-worker-runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "worker" {
  role       = aws_iam_role.worker.name
  policy_arn = aws_iam_policy.worker.arn
}

# Off by default. Turn it on (enable_ecs_exec) only while you need a shell inside the VPC, for
# example to create the first user with the CLI, then turn it off again (DEPLOYMENT.md).
data "aws_iam_policy_document" "ecs_exec" {
  statement {
    sid = "EcsExecChannels"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker_exec" {
  count = var.enable_ecs_exec ? 1 : 0

  name   = "ecs-exec"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.ecs_exec.json
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.worker_execution.arn
  task_role_arn            = aws_iam_role.worker.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true
      command   = ["worker"]

      environment = [for name, value in local.app_environment : { name = name, value = value }]
      secrets     = [for name, arn in local.app_secrets : { name = name, valueFrom = arn }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  count = var.enable_compute ? 1 : 0

  name            = "${var.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  enable_execute_command = var.enable_ecs_exec

  # A deploy stops the old task before starting the new one, so two workers never run at once.
  # Job claims are atomic, so a second worker would be safe, but it would double the compute bill.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = true
  }

  lifecycle {
    # After creation the task count belongs to Application Auto Scaling (worker_autoscaling.tf) or
    # to whoever changes it by hand; an apply must not reset it while a job is running.
    ignore_changes = [desired_count]
  }

  depends_on = [
    aws_iam_role_policy_attachment.worker_execution,
    aws_iam_role_policy_attachment.worker,
  ]
}
