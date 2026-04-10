variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "alert_email" {
  description = "Email address for alerts"
  type        = string
}

variable "crawler_lambda_names" {
  description = "List of crawler Lambda function names"
  type        = list(string)
}

variable "api_gateway_id" {
  description = "API Gateway ID"
  type        = string
}

variable "api_stage_name" {
  description = "API Gateway stage name"
  type        = string
}

variable "dlq_url" {
  description = "SQS DLQ URL for monitoring"
  type        = string
}

variable "ses_verified_domain" {
  description = "SES verified domain"
  type        = string
}
