# Placeholder zip file for Lambda functions
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"
  source {
    content  = "# Placeholder - deployed via CI/CD"
    filename = "lambda_function.py"
  }
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-api-logs"
  }
}

# REST API
resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-api"
  description = "Scout API Gateway"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name = "${var.project_name}-api"
  }
}

# Cognito Authorizer
resource "aws_api_gateway_authorizer" "cognito" {
  name          = "${var.project_name}-authorizer"
  type          = "COGNITO_USER_POOLS"
  provider_arns = [var.cognito_user_pool_arn]
  rest_api_id   = aws_api_gateway_rest_api.main.id

  identity_source = "method.request.header.Authorization"
}

# IAM role for Lambda execution
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-api-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access policy for Lambda
resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "${var.project_name}-lambda-dynamodb-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          var.dynamodb_jobs_table_arn,
          "${var.dynamodb_jobs_table_arn}/index/*",
          var.dynamodb_user_status_table_arn,
          "${var.dynamodb_user_status_table_arn}/index/*",
          var.dynamodb_users_table_arn
        ]
      }
    ]
  })
}

# GET /jobs - List jobs
resource "aws_lambda_function" "get_jobs" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-api-get-jobs"
  role          = aws_iam_role.lambda_role.arn
  handler       = "api.get_jobs.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      JOBS_TABLE        = var.dynamodb_jobs_table_name
      USER_STATUS_TABLE = var.dynamodb_user_status_table_name
      USERS_TABLE       = var.dynamodb_users_table_name
      SITE_URL          = "https://${var.subdomain}.${var.domain_name}"
    }
  }

  tags = {
    Name = "${var.project_name}-api-get-jobs"
  }
}

# NOTE: GET /jobs/{jobId} reuses the get_jobs Lambda — the handler
# inspects pathParameters to decide between list and detail modes.

# PATCH /jobs/{jobId}/status - Update job status
resource "aws_lambda_function" "patch_job_status" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-api-update-status"
  role          = aws_iam_role.lambda_role.arn
  handler       = "api.update_status.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      USER_STATUS_TABLE = var.dynamodb_user_status_table_name
    }
  }

  tags = {
    Name = "${var.project_name}-api-update-status"
  }
}

# GET /user/settings - Get user settings
resource "aws_lambda_function" "get_user_settings" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-api-user-settings"
  role          = aws_iam_role.lambda_role.arn
  handler       = "api.user_settings.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      USERS_TABLE = var.dynamodb_users_table_name
    }
  }

  tags = {
    Name = "${var.project_name}-api-user-settings"
  }
}

# NOTE: PUT /user/settings reuses the get_user_settings Lambda — the handler
# inspects httpMethod to decide between GET and PUT modes.

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "api_invoke_get_jobs" {
  statement_id  = "AllowAPIInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_jobs.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_invoke_get_job_detail" {
  statement_id  = "AllowAPIInvokeJobDetail"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_jobs.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_invoke_patch_job_status" {
  statement_id  = "AllowAPIInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.patch_job_status.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_invoke_get_user_settings" {
  statement_id  = "AllowAPIInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_user_settings.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_invoke_put_user_settings" {
  statement_id  = "AllowAPIInvokePutSettings"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_user_settings.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# API Resources and Methods

# GET /jobs
resource "aws_api_gateway_resource" "jobs" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "jobs"
}

resource "aws_api_gateway_method" "get_jobs" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.jobs.id
  http_method      = "GET"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

resource "aws_api_gateway_integration" "get_jobs" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.jobs.id
  http_method      = aws_api_gateway_method.get_jobs.http_method
  type             = "AWS_PROXY"
  integration_http_method = "POST"
  uri              = aws_lambda_function.get_jobs.invoke_arn
}

# GET /jobs/{jobId}
resource "aws_api_gateway_resource" "job_detail" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.jobs.id
  path_part   = "{jobId}"
}

resource "aws_api_gateway_method" "get_job_detail" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.job_detail.id
  http_method      = "GET"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
    "method.request.path.jobId"            = true
  }
}

resource "aws_api_gateway_integration" "get_job_detail" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.job_detail.id
  http_method      = aws_api_gateway_method.get_job_detail.http_method
  type             = "AWS_PROXY"
  integration_http_method = "POST"
  uri              = aws_lambda_function.get_jobs.invoke_arn
}

# PATCH /jobs/{jobId}/status
resource "aws_api_gateway_resource" "job_status" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.job_detail.id
  path_part   = "status"
}

resource "aws_api_gateway_method" "patch_job_status" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.job_status.id
  http_method      = "PATCH"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
    "method.request.path.jobId"            = true
  }
}

resource "aws_api_gateway_integration" "patch_job_status" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.job_status.id
  http_method      = aws_api_gateway_method.patch_job_status.http_method
  type             = "AWS_PROXY"
  integration_http_method = "POST"
  uri              = aws_lambda_function.patch_job_status.invoke_arn
}

# GET /user/settings
resource "aws_api_gateway_resource" "user" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "user"
}

resource "aws_api_gateway_resource" "user_settings" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.user.id
  path_part   = "settings"
}

resource "aws_api_gateway_method" "get_user_settings" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.user_settings.id
  http_method      = "GET"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

resource "aws_api_gateway_integration" "get_user_settings" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.user_settings.id
  http_method      = aws_api_gateway_method.get_user_settings.http_method
  type             = "AWS_PROXY"
  integration_http_method = "POST"
  uri              = aws_lambda_function.get_user_settings.invoke_arn
}

# PUT /user/settings
resource "aws_api_gateway_method" "put_user_settings" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.user_settings.id
  http_method      = "PUT"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

resource "aws_api_gateway_integration" "put_user_settings" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.user_settings.id
  http_method      = aws_api_gateway_method.put_user_settings.http_method
  type             = "AWS_PROXY"
  integration_http_method = "POST"
  uri              = aws_lambda_function.get_user_settings.invoke_arn
}

# CORS support via OPTIONS methods
resource "aws_api_gateway_method" "jobs_options" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.jobs.id
  http_method      = "OPTIONS"
  authorization    = "NONE"
}

resource "aws_api_gateway_integration" "jobs_options" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.jobs.id
  http_method      = aws_api_gateway_method.jobs_options.http_method
  type             = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

# method_response must exist before integration_response — declare it first
resource "aws_api_gateway_method_response" "jobs_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.jobs.id
  http_method = aws_api_gateway_method.jobs_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
  depends_on = [aws_api_gateway_method.jobs_options]
}

resource "aws_api_gateway_integration_response" "jobs_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.jobs.id
  http_method = aws_api_gateway_method.jobs_options.http_method
  status_code = aws_api_gateway_method_response.jobs_options.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS,POST,PUT,PATCH,DELETE'"
    "method.response.header.Access-Control-Allow-Origin"  = "'https://scout.carniaux.io'"
  }
  depends_on = [
    aws_api_gateway_integration.jobs_options,
    aws_api_gateway_method_response.jobs_options,
  ]
}

# Add CORS headers to other methods
resource "aws_api_gateway_method_response" "get_jobs" {
  rest_api_id      = aws_api_gateway_rest_api.main.id
  resource_id      = aws_api_gateway_resource.jobs.id
  http_method      = aws_api_gateway_method.get_jobs.http_method
  status_code      = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin" = true
  }
}

resource "aws_api_gateway_integration_response" "get_jobs" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.jobs.id
  http_method = aws_api_gateway_method.get_jobs.http_method
  status_code = aws_api_gateway_method_response.get_jobs.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin" = "'https://scout.carniaux.io'"
  }
  depends_on = [
    aws_api_gateway_integration.get_jobs,
    aws_api_gateway_method_response.get_jobs,
  ]
}

# API Gateway Stage
resource "aws_api_gateway_stage" "v1" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = "v1"

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      integrationLatency = "$context.integration.latency"
      error          = "$context.error.message"
      errorType      = "$context.error.messageString"
    })
  }

  tags = {
    Name = "${var.project_name}-v1-stage"
  }
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  depends_on = [
    aws_api_gateway_integration.get_jobs,
    aws_api_gateway_integration.get_job_detail,
    aws_api_gateway_integration.patch_job_status,
    aws_api_gateway_integration.get_user_settings,
    aws_api_gateway_integration.put_user_settings,
    aws_api_gateway_integration.jobs_options,
    aws_api_gateway_integration_response.get_jobs,
    aws_api_gateway_integration_response.jobs_options,
    aws_api_gateway_method_response.get_jobs,
    aws_api_gateway_method_response.jobs_options,
  ]
}
