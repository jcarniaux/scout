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
  description = "Bedrock model ID for AI job scoring"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}
