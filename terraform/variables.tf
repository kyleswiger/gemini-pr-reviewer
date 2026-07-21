variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used to name created AWS resources."
  type        = string
  default     = "gemini-pr-reviewer"
}

variable "ssm_parameter_prefix" {
  description = "SSM Parameter Store path under which secrets live (no trailing slash)."
  type        = string
  default     = "/gemini-pr-reviewer"
}

variable "lambda_runtime" {
  description = "Python runtime for the Lambda function."
  type        = string
  default     = "python3.12"
}

variable "lambda_architecture" {
  description = "Lambda CPU architecture."
  type        = string
  default     = "x86_64"
  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "lambda_architecture must be either x86_64 or arm64."
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout for PR diff processing and Gemini review generation."
  type        = number
  default     = 60
}

variable "lambda_memory_mb" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 512
}

variable "log_retention_days" {
  description = "Retention (in days) for the Lambda's CloudWatch log group."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    Project   = "gemini-pr-reviewer"
    ManagedBy = "Terraform"
  }
}
