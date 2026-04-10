output "ses_domain_identity_arn" {
  description = "SES domain identity ARN"
  value       = aws_ses_domain_identity.main.arn
}

output "ses_verification_token" {
  description = "SES domain verification token"
  value       = aws_ses_domain_identity.main.verification_token
  sensitive   = true
}
