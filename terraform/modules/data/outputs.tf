output "dynamodb_jobs_table_name" {
  description = "DynamoDB jobs table name"
  value       = aws_dynamodb_table.jobs.name
}

output "dynamodb_jobs_table_arn" {
  description = "DynamoDB jobs table ARN"
  value       = aws_dynamodb_table.jobs.arn
}

output "dynamodb_user_status_table_name" {
  description = "DynamoDB user status table name"
  value       = aws_dynamodb_table.user_status.name
}

output "dynamodb_user_status_table_arn" {
  description = "DynamoDB user status table ARN"
  value       = aws_dynamodb_table.user_status.arn
}

output "dynamodb_users_table_name" {
  description = "DynamoDB users table name"
  value       = aws_dynamodb_table.users.name
}

output "dynamodb_users_table_arn" {
  description = "DynamoDB users table ARN"
  value       = aws_dynamodb_table.users.arn
}

output "dynamodb_glassdoor_cache_table_name" {
  description = "DynamoDB Glassdoor cache table name"
  value       = aws_dynamodb_table.glassdoor_cache.name
}

output "dynamodb_glassdoor_cache_table_arn" {
  description = "DynamoDB Glassdoor cache table ARN"
  value       = aws_dynamodb_table.glassdoor_cache.arn
}
