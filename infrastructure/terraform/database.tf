# PostgreSQL on RDS. Private subnets, no public address, encrypted, TLS required, and only the
# API and the worker security groups can reach it (docs/ADR/0006).
#
# The password is generated here and stored as an SSM SecureString (secrets.tf). That puts it in
# the Terraform state, so the state must be kept private (see infrastructure/terraform/README.md).
# RDS's own managed master password was not used because Secrets Manager rotates it on a schedule,
# and a container that received the old value in an environment variable would then fail to sign
# in until it was restarted.

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-database"
  description = "PostgreSQL: reachable from the API and the worker only."
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-database" }
}

resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api"
  description = "API (App Runner VPC connector). No inbound traffic."
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-api" }
}

resource "aws_security_group" "worker" {
  name        = "${var.name_prefix}-worker"
  description = "Training worker (Fargate). No inbound traffic."
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-worker" }
}

resource "aws_vpc_security_group_ingress_rule" "database_from_api" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from the API"
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "database_from_worker" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from the worker"
  referenced_security_group_id = aws_security_group.worker.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# The API sits in private subnets: it may reach the database, the SQS endpoint and S3 (the gateway
# endpoint is addressed by prefix list).
resource "aws_vpc_security_group_egress_rule" "api_to_database" {
  security_group_id            = aws_security_group.api.id
  description                  = "PostgreSQL"
  referenced_security_group_id = aws_security_group.database.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "api_to_endpoints" {
  security_group_id            = aws_security_group.api.id
  description                  = "HTTPS to the SQS interface endpoint"
  referenced_security_group_id = aws_security_group.endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_vpc_security_group_egress_rule" "api_to_s3" {
  security_group_id = aws_security_group.api.id
  description       = "HTTPS to S3 through the gateway endpoint"
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "worker_to_database" {
  security_group_id            = aws_security_group.worker.id
  description                  = "PostgreSQL"
  referenced_security_group_id = aws_security_group.database.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# The worker has a public IP and no NAT, so it needs the internet for ECR, SQS, S3 and logs.
resource "aws_vpc_security_group_egress_rule" "worker_https" {
  security_group_id = aws_security_group.worker.id
  description       = "HTTPS to AWS APIs and the image registry"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_db_parameter_group" "main" {
  name_prefix = "${var.name_prefix}-pg-"
  family      = "postgres${var.db_engine_major_version}"
  description = "AutoML Lab PostgreSQL: connections must use TLS."

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = var.db_engine_major_version
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  parameter_group_name   = aws_db_parameter_group.main.name
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = var.db_backup_retention_days
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  deletion_protection        = var.db_deletion_protection
  skip_final_snapshot        = var.db_skip_final_snapshot
  final_snapshot_identifier  = var.db_skip_final_snapshot ? null : "${var.name_prefix}-db-final"

  performance_insights_enabled = false
  apply_immediately            = false
}
