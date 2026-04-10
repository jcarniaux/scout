output "cloudfront_distribution_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.frontend.cloudfront_distribution_domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.frontend.cloudfront_distribution_id
}

output "s3_bucket_name" {
  description = "S3 bucket name for frontend"
  value       = module.frontend.s3_bucket_name
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend (alias for CI/CD)"
  value       = module.frontend.s3_bucket_name
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.auth.cognito_user_pool_id
}

output "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN"
  value       = module.auth.cognito_user_pool_arn
}

output "cognito_client_id" {
  description = "Cognito Client ID for frontend"
  value       = module.auth.cognito_client_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID (alias for CI/CD)"
  value       = module.auth.cognito_client_id
}

output "cognito_domain" {
  description = "Cognito domain"
  value       = module.auth.cognito_domain
}

output "api_gateway_url" {
  description = "API Gateway base URL"
  value       = module.api.api_gateway_url
}

output "api_gateway_id" {
  description = "API Gateway ID"
  value       = module.api.api_gateway_id
}

output "dynamodb_jobs_table_name" {
  description = "DynamoDB jobs table name"
  value       = module.data.dynamodb_jobs_table_name
}

output "dynamodb_jobs_table_arn" {
  description = "DynamoDB jobs table ARN"
  value       = module.data.dynamodb_jobs_table_arn
}

output "dynamodb_user_status_table_name" {
  description = "DynamoDB user status table name"
  value       = module.data.dynamodb_user_status_table_name
}

output "dynamodb_users_table_name" {
  description = "DynamoDB users table name"
  value       = module.data.dynamodb_users_table_name
}

output "dynamodb_glassdoor_cache_table_name" {
  description = "DynamoDB Glassdoor cache table name"
  value       = module.data.dynamodb_glassdoor_cache_table_name
}

output "step_functions_state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = module.crawl.step_functions_state_machine_arn
}

output "sqs_queue_url" {
  description = "SQS queue URL for raw jobs"
  value       = module.crawl.sqs_queue_url
}

output "ses_domain_identity_arn" {
  description = "SES domain identity ARN"
  value       = module.email.ses_domain_identity_arn
}

output "sns_alert_topic_arn" {
  description = "SNS topic ARN for alerts"
  value       = module.monitoring.sns_alert_topic_arn
}

output "cloudwatch_dashboard_url" {
  description = "CloudWatch dashboard URL"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${module.monitoring.dashboard_name}"
}

output "app_url" {
  description = "Scout application URL"
  value       = "https://${var.subdomain}.${var.domain_name}"
}
