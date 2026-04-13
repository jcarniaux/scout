output "resumes_bucket_name" {
  description = "S3 bucket name for user resume uploads"
  value       = aws_s3_bucket.resumes.bucket
}

output "resumes_bucket_arn" {
  description = "S3 bucket ARN for user resume uploads"
  value       = aws_s3_bucket.resumes.arn
}

output "resume_parser_lambda_name" {
  description = "Resume parser Lambda function name"
  value       = aws_lambda_function.resume_parser.function_name
}
