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
  description = "Lambda timeout for PR diff processing and Gemini review generation. Must exceed the Gemini client timeout (45s) plus GEMINI_RETRY_BUDGET_SECONDS (45s)."
  type        = number
  default     = 120
}

variable "gemini_model" {
  description = "Gemini model id used for reviews. Pin an explicit version — free-tier quota is metered per model, and a `-latest` alias silently moves the reviewer onto whatever bucket Google repoints it to."
  type        = string
  default     = "gemini-3.5-flash"
  validation {
    condition     = !endswith(var.gemini_model, "-latest")
    error_message = "gemini_model must be a pinned model id, not a -latest alias."
  }
}

variable "gemini_fallback_models" {
  description = "Models tried, in order, once the primary model's quota is exhausted. Each is its own free-tier bucket."
  type        = list(string)
  default     = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
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
