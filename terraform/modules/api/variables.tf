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
