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

variable "ses_verified_domain" {
  description = "SES verified domain"
  type        = string
}

variable "daily_report_schedule" {
  description = "EventBridge cron schedule for daily report"
  type        = string
}

variable "weekly_report_schedule" {
  description = "EventBridge cron schedule for weekly report"
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

variable "dynamodb_users_table_name" {
  description = "DynamoDB users table name"
  type        = string
}

variable "dynamodb_users_table_arn" {
  description = "DynamoDB users table ARN"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
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

variable "domain_name" {
  description = "Root domain name"
  type        = string
}

variable "subdomain" {
  description = "Subdomain for the app"
  type        = string
}
