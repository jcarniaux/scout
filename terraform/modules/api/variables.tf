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

variable "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN"
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

variable "dynamodb_users_table_name" {
  description = "DynamoDB users table name"
  type        = string
}

variable "dynamodb_users_table_arn" {
  description = "DynamoDB users table ARN"
  type        = string
}

variable "domain_name" {
  description = "Domain name"
  type        = string
}

variable "subdomain" {
  description = "Subdomain"
  type        = string
}

variable "shared_layer_arn" {
  description = "ARN of the shared Lambda Layer (db, models, response utils)"
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

variable "resumes_bucket_name" {
  description = "S3 bucket name for resume uploads"
  type        = string
}

variable "resumes_bucket_arn" {
  description = "S3 bucket ARN for resume uploads"
  type        = string
}

variable "job_scorer_function_name" {
  description = "Job scorer Lambda function name — injected into user_settings env so it can invoke scoring async"
  type        = string
}

variable "job_scorer_function_arn" {
  description = "Job scorer Lambda function ARN — used to scope the InvokeFunction IAM permission"
  type        = string
}
