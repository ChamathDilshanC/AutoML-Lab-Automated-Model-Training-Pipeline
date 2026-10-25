variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-1"
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
  description = "Extra browser origins of a deployed frontend, e.g. [\"https://automl-lab.vercel.app\"]. Allowed by the API's CORS and by the bucket's CORS. The Amplify branch's origin is added automatically when enable_frontend is true."
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

variable "availability_zones" {
  description = "Two availability zones for the subnets. Leave null to use <region>a and <region>b. Set it when your account does not have those zones, for example [\"us-east-1a\", \"us-east-1c\"]."
  type        = list(string)
  default     = null

  validation {
    condition     = var.availability_zones == null || (length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2)
    error_message = "Give exactly two different zones from the chosen region, e.g. [\"us-east-1a\", \"us-east-1b\"]."
  }
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
  description = "Days of automated backups to keep. 0 turns backups off. Accounts on the AWS Free plan are limited to 1 day (higher values fail with FreeTierRestrictionError); raise it once the account is on a paid plan."
  type        = number
  default     = 1
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
  description = "Create the compute layer: the API's Lambda function and Function URL, and the ECS worker service. Leave false for the first apply: both need an image in ECR, which exists only after the first push (docs/DEPLOYMENT.md, Apply order)."
  type        = bool
  default     = false
}

variable "api_memory_mb" {
  description = "Memory of the API's Lambda function in MiB; Lambda gives CPU in proportion. Models of up to 200 MB are loaded into memory, so keep at least 2048."
  type        = number
  default     = 2048

  validation {
    condition     = var.api_memory_mb >= 128 && var.api_memory_mb <= 10240
    error_message = "Lambda allows 128 to 10240 MiB."
  }
}

variable "api_timeout_seconds" {
  description = "Longest an API request may run on Lambda, in seconds. Validating a dataset or loading a model on a cold start takes the longest."
  type        = number
  default     = 60

  validation {
    condition     = var.api_timeout_seconds >= 1 && var.api_timeout_seconds <= 900
    error_message = "Lambda allows 1 to 900 seconds."
  }
}

variable "enable_frontend" {
  description = "Create the Amplify Hosting app and branch for the frontend (frontend.tf). Needs amplify_github_token on the apply that creates them."
  type        = bool
  default     = false
}

variable "amplify_github_token" {
  description = "GitHub personal access token Amplify uses once to connect the repository through the Amplify GitHub App. Pass it as the TF_VAR_amplify_github_token environment variable, never in a file. Only the apply that creates the app needs it; it is kept in the Terraform state."
  type        = string
  default     = null
  sensitive   = true
}

variable "amplify_branch" {
  description = "Git branch that Amplify builds and serves."
  type        = string
  default     = "main"
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
  description = "Worker tasks when the service is first created. Terraform ignores it afterwards: with enable_worker_autoscaling the queue decides, otherwise change the count by hand (docs/WORKER_AUTOSCALING.md)."
  type        = number
  default     = 0

  validation {
    condition     = var.worker_desired_count >= 0 && var.worker_desired_count <= 1
    error_message = "Use 0 or 1. More than one worker is not needed or tested at this scale."
  }
}

variable "enable_worker_autoscaling" {
  description = "Start the worker (0 -> 1 task) when the experiments queue has work and stop it once the queue has been idle for worker_scale_in_idle_minutes (worker_autoscaling.tf). Needs enable_compute."
  type        = bool
  default     = true
}

variable "worker_scale_in_idle_minutes" {
  description = "Minutes with no experiment waiting and none in flight before the worker is stopped."
  type        = number
  default     = 5

  validation {
    condition     = var.worker_scale_in_idle_minutes >= 2 && var.worker_scale_in_idle_minutes <= 60 && floor(var.worker_scale_in_idle_minutes) == var.worker_scale_in_idle_minutes
    error_message = "Use a whole number of minutes from 2 to 60."
  }
}

variable "trusted_proxy_hops" {
  description = "Proxies in front of the API that append to X-Forwarded-For (the Lambda Function URL is one). Used for the per-client sign-in limit."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "How long worker and API logs are kept, in days."
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

variable "enable_ecs_exec" {
  description = "Enable ECS Exec for debugging container tasks."
  type        = bool
  default     = false
}