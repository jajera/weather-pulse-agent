variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Project name prefix for resources"
  type        = string
  default     = "weather-pulse"
}

variable "environment" {
  description = "Environment tag"
  type        = string
  default     = "prod"
}

variable "email_subscription" {
  description = "Email address subscribed to the SNS digest topic"
  type        = string
}

variable "s3_bucket_name" {
  description = "S3 bucket name for reports and raw archives (globally unique)"
  type        = string
}
