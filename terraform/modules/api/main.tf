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

# Request validator — rejects requests with missing body on PATCH/PUT methods
# before they reach Lambda, saving invocation cost and cold start budget.
resource "aws_api_gateway_request_validator" "body" {
  name                        = "validate-body"
  rest_api_id                 = aws_api_gateway_rest_api.main.id
  validate_request_body       = true
  validate_request_parameters = true
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

# X-Ray tracing permissions
resource "aws_iam_role_policy_attachment" "lambda_xray" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
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

  tracing_config {
    mode = "Active"
  }

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

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      USER_STATUS_TABLE = var.dynamodb_user_status_table_name
      SITE_URL          = "https://${var.subdomain}.${var.domain_name}"
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

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      USERS_TABLE = var.dynamodb_users_table_name
      SITE_URL    = "https://${var.subdomain}.${var.domain_name}"
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
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.jobs.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

resource "aws_api_gateway_integration" "get_jobs" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.jobs.id
  http_method             = aws_api_gateway_method.get_jobs.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.get_jobs.invoke_arn
}

# GET /jobs/{jobId}
resource "aws_api_gateway_resource" "job_detail" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.jobs.id
  path_part   = "{jobId}"
}

resource "aws_api_gateway_method" "get_job_detail" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.job_detail.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
    "method.request.path.jobId"           = true
  }
}

resource "aws_api_gateway_integration" "get_job_detail" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.job_detail.id
  http_method             = aws_api_gateway_method.get_job_detail.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.get_jobs.invoke_arn
}

# PATCH /jobs/{jobId}/status
resource "aws_api_gateway_resource" "job_status" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.job_detail.id
  path_part   = "status"
}

resource "aws_api_gateway_method" "patch_job_status" {
  rest_api_id          = aws_api_gateway_rest_api.main.id
  resource_id          = aws_api_gateway_resource.job_status.id
  http_method          = "PATCH"
  authorization        = "COGNITO_USER_POOLS"
  authorizer_id        = aws_api_gateway_authorizer.cognito.id
  request_validator_id = aws_api_gateway_request_validator.body.id
  request_parameters = {
    "method.request.header.Authorization" = true
    "method.request.path.jobId"           = true
  }
}

resource "aws_api_gateway_integration" "patch_job_status" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.job_status.id
  http_method             = aws_api_gateway_method.patch_job_status.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.patch_job_status.invoke_arn
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
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.user_settings.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

resource "aws_api_gateway_integration" "get_user_settings" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.user_settings.id
  http_method             = aws_api_gateway_method.get_user_settings.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.get_user_settings.invoke_arn
}

# PUT /user/settings
resource "aws_api_gateway_method" "put_user_settings" {
  rest_api_id          = aws_api_gateway_rest_api.main.id
  resource_id          = aws_api_gateway_resource.user_settings.id
  http_method          = "PUT"
  authorization        = "COGNITO_USER_POOLS"
  authorizer_id        = aws_api_gateway_authorizer.cognito.id
  request_validator_id = aws_api_gateway_request_validator.body.id
  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

resource "aws_api_gateway_integration" "put_user_settings" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.user_settings.id
  http_method             = aws_api_gateway_method.put_user_settings.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.get_user_settings.invoke_arn
}

# ─── CORS helpers ─────────────────────────────────────────────────────────────
locals {
  cors_headers = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
  cors_methods = "'GET,OPTIONS,POST,PUT,PATCH,DELETE'"
  cors_origin  = "'https://${var.subdomain}.${var.domain_name}'"
}

# Method/integration responses for GET /jobs — kept to avoid destroy-order cycle
# with create_before_destroy on the deployment. AWS_PROXY ignores these at
# runtime (Lambda controls the response), but removing them forces a destroy
# that entangles the deposed deployment's cleanup through the stage reference.
resource "aws_api_gateway_method_response" "get_jobs" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.jobs.id
  http_method = aws_api_gateway_method.get_jobs.http_method
  status_code = "200"
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
    "method.response.header.Access-Control-Allow-Origin" = local.cors_origin
  }
  depends_on = [
    aws_api_gateway_integration.get_jobs,
    aws_api_gateway_method_response.get_jobs,
  ]
}

# ─── CORS OPTIONS handlers ────────────────────────────────────────────────────
# Every resource that receives cross-origin requests needs an un-authenticated
# OPTIONS method so the browser preflight succeeds before it sends the real
# request with an Authorization header.
#
# Resources that need CORS:
#   /jobs                  (GET)
#   /jobs/{jobId}          (GET)
#   /jobs/{jobId}/status   (PATCH)
#   /user/settings         (GET, PUT)

# Helper: reusable CORS MOCK integration block
# (Terraform doesn't support modules for sub-resources, so we repeat the
#  pattern for each resource — kept DRY via locals above.)

# /jobs OPTIONS
resource "aws_api_gateway_method" "jobs_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.jobs.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "jobs_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.jobs.id
  http_method = aws_api_gateway_method.jobs_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

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
    "method.response.header.Access-Control-Allow-Headers" = local.cors_headers
    "method.response.header.Access-Control-Allow-Methods" = local.cors_methods
    "method.response.header.Access-Control-Allow-Origin"  = local.cors_origin
  }
  depends_on = [
    aws_api_gateway_integration.jobs_options,
    aws_api_gateway_method_response.jobs_options,
  ]
}

# /jobs/{jobId} OPTIONS
resource "aws_api_gateway_method" "job_detail_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.job_detail.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "job_detail_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.job_detail.id
  http_method = aws_api_gateway_method.job_detail_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "job_detail_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.job_detail.id
  http_method = aws_api_gateway_method.job_detail_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
  depends_on = [aws_api_gateway_method.job_detail_options]
}

resource "aws_api_gateway_integration_response" "job_detail_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.job_detail.id
  http_method = aws_api_gateway_method.job_detail_options.http_method
  status_code = aws_api_gateway_method_response.job_detail_options.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = local.cors_headers
    "method.response.header.Access-Control-Allow-Methods" = local.cors_methods
    "method.response.header.Access-Control-Allow-Origin"  = local.cors_origin
  }
  depends_on = [
    aws_api_gateway_integration.job_detail_options,
    aws_api_gateway_method_response.job_detail_options,
  ]
}

# /jobs/{jobId}/status OPTIONS
resource "aws_api_gateway_method" "job_status_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.job_status.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "job_status_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.job_status.id
  http_method = aws_api_gateway_method.job_status_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "job_status_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.job_status.id
  http_method = aws_api_gateway_method.job_status_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
  depends_on = [aws_api_gateway_method.job_status_options]
}

resource "aws_api_gateway_integration_response" "job_status_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.job_status.id
  http_method = aws_api_gateway_method.job_status_options.http_method
  status_code = aws_api_gateway_method_response.job_status_options.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = local.cors_headers
    "method.response.header.Access-Control-Allow-Methods" = local.cors_methods
    "method.response.header.Access-Control-Allow-Origin"  = local.cors_origin
  }
  depends_on = [
    aws_api_gateway_integration.job_status_options,
    aws_api_gateway_method_response.job_status_options,
  ]
}

# /user/settings OPTIONS
resource "aws_api_gateway_method" "user_settings_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.user_settings.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "user_settings_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.user_settings.id
  http_method = aws_api_gateway_method.user_settings_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "user_settings_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.user_settings.id
  http_method = aws_api_gateway_method.user_settings_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
  depends_on = [aws_api_gateway_method.user_settings_options]
}

resource "aws_api_gateway_integration_response" "user_settings_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.user_settings.id
  http_method = aws_api_gateway_method.user_settings_options.http_method
  status_code = aws_api_gateway_method_response.user_settings_options.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = local.cors_headers
    "method.response.header.Access-Control-Allow-Methods" = local.cors_methods
    "method.response.header.Access-Control-Allow-Origin"  = local.cors_origin
  }
  depends_on = [
    aws_api_gateway_integration.user_settings_options,
    aws_api_gateway_method_response.user_settings_options,
  ]
}

# ─── API Gateway Deployment ───────────────────────────────────────────────────
# The triggers block forces a new deployment whenever any method, integration,
# authorizer, or CORS config changes. Without this, Terraform updates the REST
# API resources in place but the live stage continues serving the old snapshot.
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_authorizer.cognito.id,
      aws_api_gateway_authorizer.cognito.provider_arns,
      aws_api_gateway_integration.get_jobs.id,
      aws_api_gateway_integration.get_job_detail.id,
      aws_api_gateway_integration.patch_job_status.id,
      aws_api_gateway_integration.get_user_settings.id,
      aws_api_gateway_integration.put_user_settings.id,
      aws_api_gateway_integration.jobs_options.id,
      aws_api_gateway_integration.job_detail_options.id,
      aws_api_gateway_integration.job_status_options.id,
      aws_api_gateway_integration.user_settings_options.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.get_jobs,
    aws_api_gateway_integration.get_job_detail,
    aws_api_gateway_integration.patch_job_status,
    aws_api_gateway_integration.get_user_settings,
    aws_api_gateway_integration.put_user_settings,
    aws_api_gateway_integration.jobs_options,
    aws_api_gateway_integration.job_detail_options,
    aws_api_gateway_integration.job_status_options,
    aws_api_gateway_integration.user_settings_options,
    aws_api_gateway_integration_response.jobs_options,
    aws_api_gateway_integration_response.job_detail_options,
    aws_api_gateway_integration_response.job_status_options,
    aws_api_gateway_integration_response.user_settings_options,
  ]
}

# ─── API Gateway Stage ────────────────────────────────────────────────────────
resource "aws_api_gateway_stage" "v1" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = "v1"

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      resourcePath       = "$context.resourcePath"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      integrationLatency = "$context.integration.latency"
      error              = "$context.error.message"
      errorType          = "$context.error.messageString"
    })
  }

  tags = {
    Name = "${var.project_name}-v1-stage"
  }

  depends_on = [aws_api_gateway_deployment.main]
}

# ─── API Gateway Throttling ──────────────────────────────────────────────────
# Applies to all methods on the v1 stage.  Burst = 50 (concurrent), Rate = 100/s.
# For a handful of users this is generous; it exists to cap runaway bots/scripts
# and protect downstream Lambda concurrency + DynamoDB capacity.
resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.v1.stage_name
  method_path = "*/*"

  settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 100
    logging_level          = "ERROR"
    data_trace_enabled     = false
    metrics_enabled        = true
  }
}

# ─── Regional WAF for API Gateway ────────────────────────────────────────────
# The CloudFront WAF (in the frontend module) only protects the CDN.  Anyone
# who discovers the API Gateway invoke URL can hit it directly.  This regional
# WAFv2 WebACL attaches to the API stage to close that gap.
resource "aws_wafv2_web_acl" "api" {
  name  = "${var.project_name}-api-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules — Common Rule Set (SQLi, XSS, bad bots)
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 0

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-api-common-rules"
      sampled_requests_enabled   = true
    }
  }

  # Rate-limit: 300 requests per 5 min per IP
  rule {
    name     = "RateLimitRule"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 300
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-api-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-api-waf-metrics"
    sampled_requests_enabled   = true
  }

  tags = {
    Name = "${var.project_name}-api-waf"
  }
}

resource "aws_wafv2_web_acl_association" "api" {
  resource_arn = aws_api_gateway_stage.v1.arn
  web_acl_arn  = aws_wafv2_web_acl.api.arn
}
