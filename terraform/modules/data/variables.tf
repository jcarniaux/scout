variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment"
  type        = string
}

variable "job_retention_days" {
  description = "Number of days to retain job records (TTL)"
  type        = number
  default     = 60
}
