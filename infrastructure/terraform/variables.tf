variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "eu-west-1"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "automl-lab"
}

variable "bucket_name" {
  description = "Globally unique bucket name. Leave null to use <name_prefix>-<account id>-<region>."
  type        = string
  default     = null

  validation {
    condition     = var.bucket_name == null || can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Use 3 to 63 lower-case letters, digits and hyphens. Dots are not allowed: they break TLS for the virtual-hosted upload URLs."
  }
}

variable "allowed_origins" {
  description = "Browser origins allowed to upload to the bucket (CORS)."
  type        = list(string)
  default     = ["http://localhost:3000"]
}

variable "job_timeout_seconds" {
  description = "Keep equal to the application's JOB_TIMEOUT_SECONDS. It is used as the queue's visibility timeout so a job that is still running is not delivered again."
  type        = number
  default     = 1800
}

variable "max_receive_count" {
  description = "How many times a job message is delivered before it moves to the dead-letter queue."
  type        = number
  default     = 3
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a bucket that still holds objects. Only for throwaway environments."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags for every resource."
  type        = map(string)
  default     = {}
}

variable "frontend_origins" {
  description = "Browser origins of the deployed frontend, e.g. [\"https://automl-lab.vercel.app\"]. Allowed by the API's CORS and by the bucket's CORS."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for origin in var.frontend_origins : can(regex("^https?://[^/]+$", origin))])
    error_message = "Each origin is a scheme and host with no path and no trailing slash, e.g. https://automl-lab.vercel.app."
  }
}

variable "vpc_cidr" {
  description = "Address range of the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "db_engine_major_version" {
  description = "PostgreSQL major version. RDS picks the current minor version and upgrades minors itself."
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.micro is the Free Tier class when the account is eligible."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Database storage in GiB (the Free Tier allowance is 20)."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Name of the application database."
  type        = string
  default     = "automl"
}

variable "db_username" {
  description = "Database user the application signs in as."
  type        = string
  default     = "automl"
}

variable "db_backup_retention_days" {
  description = "Days of automated backups to keep. 0 turns backups off."
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Refuse to delete the database. Set to false (and apply) before terraform destroy."
  type        = bool
  default     = true
}

variable "db_skip_final_snapshot" {
  description = "Skip the snapshot taken when the database is deleted. Keep false unless the data is disposable."
  type        = bool
  default     = false
}

variable "enable_compute" {
  description = "Create the App Runner service and the ECS worker service. Leave false for the first apply: both need an image in ECR, which exists only after the first push (README.md, Apply order)."
  type        = bool
  default     = false
}

variable "api_cpu" {
  description = "App Runner vCPU units (256, 512, 1024, 2048 or 4096)."
  type        = string
  default     = "1024"
}

variable "api_memory" {
  description = "App Runner memory in MiB (2048 is the least for 1024 CPU units)."
  type        = string
  default     = "2048"
}

variable "worker_cpu" {
  description = "Fargate CPU units for the worker."
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Fargate memory in MiB for the worker."
  type        = number
  default     = 2048
}

variable "worker_desired_count" {
  description = "How many worker tasks run. 0 means none: experiments stay QUEUED until you set 1."
  type        = number
  default     = 0

  validation {
    condition     = var.worker_desired_count >= 0 && var.worker_desired_count <= 1
    error_message = "Use 0 or 1. More than one worker is not needed or tested at this scale."
  }
}

variable "enable_ecs_exec" {
  description = "Allow `aws ecs execute-command` into the worker task (needs the Session Manager plugin). For admin tasks such as creating the first user; turn it off afterwards."
  type        = bool
  default     = false
}

variable "trusted_proxy_hops" {
  description = "Proxies in front of the API that append to X-Forwarded-For (App Runner is one). Used for the per-client sign-in limit."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "How long worker logs are kept."
  type        = number
  default     = 14
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the owner/name form, e.g. ChamathDilshanC/AutoML-Lab-Automated-Model-Training-Pipeline."
  }
}

variable "github_environment" {
  description = "Name of the GitHub environment whose jobs may deploy. Protect it with required reviewers."
  type        = string
  default     = "production"
}

variable "create_github_oidc_provider" {
  description = "Create the account's GitHub OIDC provider. An account can have only one: set false if it already exists."
  type        = bool
  default     = true
}

variable "budget_alert_email" {
  description = "Address that receives the cost alerts."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.budget_alert_email))
    error_message = "Enter a valid email address."
  }
}

variable "budget_limit_usd" {
  description = "Monthly cost, in USD, above which alerts are sent. An alert only: nothing is stopped."
  type        = number
  default     = 10
}
