output "api_gateway_id" {
  description = "API Gateway ID"
  value       = aws_api_gateway_rest_api.main.id
}

output "api_gateway_url" {
  description = "API Gateway base URL"
  value       = aws_api_gateway_stage.v1.invoke_url
}

output "api_stage_name" {
  description = "API Gateway stage name"
  value       = aws_api_gateway_stage.v1.stage_name
}
