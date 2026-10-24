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
