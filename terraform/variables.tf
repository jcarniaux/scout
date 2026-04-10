variable "project_name" {
  description = "Project name"
  type        = string
  default     = "scout"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Root domain name"
  type        = string
  default     = "carniaux.io"
}

variable "subdomain" {
  description = "Subdomain for the app"
  type        = string
  default     = "scout"
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms"
  type        = string
}

variable "ses_verified_domain" {
  description = "SES verified domain for sending emails"
  type        = string
  default     = "carniaux.io"
}

variable "job_retention_days" {
  description = "Number of days to retain job records (TTL)"
  type        = number
  default     = 60
}

variable "crawl_schedule" {
  description = "EventBridge cron schedule for crawl (02:00 EST = 07:00 UTC)"
  type        = string
  default     = "cron(0 7 * * ? *)"
}

variable "daily_report_schedule" {
  description = "EventBridge cron schedule for daily report (07:00 EST = 12:00 UTC)"
  type        = string
  default     = "cron(0 12 * * ? *)"
}

variable "weekly_report_schedule" {
  description = "EventBridge cron schedule for weekly report (Sat 08:00 EST = 13:00 UTC)"
  type        = string
  default     = "cron(0 13 ? * SAT *)"
}
