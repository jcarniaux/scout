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

variable "crawl_schedule" {
  description = "EventBridge cron schedule for crawl"
  type        = string
}

variable "dynamodb_jobs_table_name" {
  description = "DynamoDB jobs table name"
  type        = string
}

variable "dynamodb_jobs_table_arn" {
  description = "DynamoDB jobs table ARN"
  type        = string
}

variable "dynamodb_user_status_table_name" {
  description = "DynamoDB user status table name"
  type        = string
}

variable "dynamodb_user_status_table_arn" {
  description = "DynamoDB user status table ARN"
  type        = string
}

variable "dynamodb_glassdoor_cache_table_name" {
  description = "DynamoDB Glassdoor cache table name"
  type        = string
}

variable "dynamodb_glassdoor_cache_table_arn" {
  description = "DynamoDB Glassdoor cache table ARN"
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
  description = "ARN of the shared Lambda Layer (db, models, crawler_utils, etc.)"
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
