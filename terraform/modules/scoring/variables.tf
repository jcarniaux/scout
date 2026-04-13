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

variable "dynamodb_users_table_name" {
  description = "DynamoDB users table name"
  type        = string
}

variable "dynamodb_users_table_arn" {
  description = "DynamoDB users table ARN"
  type        = string
}

variable "shared_layer_arn" {
  description = "ARN of the shared Lambda Layer"
  type        = string
}

variable "dynamodb_jobs_table_name" {
  description = "DynamoDB jobs table name (read by job_scorer)"
  type        = string
}

variable "dynamodb_jobs_table_arn" {
  description = "DynamoDB jobs table ARN"
  type        = string
}

variable "dynamodb_job_scores_table_name" {
  description = "DynamoDB job scores table name"
  type        = string
}

variable "dynamodb_job_scores_table_arn" {
  description = "DynamoDB job scores table ARN"
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for AI job scoring. Use the cross-region inference profile ID (e.g. us.anthropic.claude-sonnet-4-6) for Claude 4-series models — these don't require a Marketplace subscription."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}
