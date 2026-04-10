output "sqs_queue_url" {
  description = "SQS queue URL"
  value       = aws_sqs_queue.raw_jobs.url
}

output "dlq_url" {
  description = "SQS DLQ URL"
  value       = aws_sqs_queue.raw_jobs_dlq.url
}

output "step_functions_state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = aws_sfn_state_machine.crawl.arn
}

output "crawler_lambda_names" {
  description = "List of crawler Lambda function names"
  value = [
    aws_lambda_function.crawler_linkedin.function_name,
    aws_lambda_function.crawler_indeed.function_name,
    aws_lambda_function.crawler_glassdoor.function_name,
    aws_lambda_function.crawler_ziprecruiter.function_name,
    aws_lambda_function.crawler_dice.function_name
  ]
}
