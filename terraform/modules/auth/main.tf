resource "random_string" "cognito_domain_suffix" {
  length  = 8
  special = false
  upper   = false # Cognito domains must be lowercase only
  numeric = true
  lower   = true
}

# Cognito User Pool
resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-user-pool-${var.environment}"

  # Username attributes - use email as username
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy: min 12 chars, uppercase, lowercase, numbers, symbols
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  # MFA configuration - "ON" means required for all users (valid: OFF | ON | OPTIONAL)
  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  # User attribute schema
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  # Email configuration
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # Account recovery settings
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Name = "${var.project_name}-user-pool"
  }
}

# Cognito User Pool Domain for hosted UI
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-auth-${random_string.cognito_domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# Cognito User Pool Client for SPA
resource "aws_cognito_user_pool_client" "spa" {
  name            = "${var.project_name}-spa-client"
  user_pool_id    = aws_cognito_user_pool.main.id
  generate_secret = false # No client secret for SPA
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  # Token validity
  access_token_validity  = 1  # hours
  id_token_validity      = 1  # hours
  refresh_token_validity = 30 # days
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Prevent user existence errors (security best practice)
  # Note: aws_cognito_user_pool_client does not support tags
  prevent_user_existence_errors = "ENABLED"
}
